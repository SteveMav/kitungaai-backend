from decimal import Decimal

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from api.models import Product
from apps.baskets.models import BasketCorrection, BasketLine, BasketSession, UncataloguedBasketLine
from apps.baskets.selectors import session_with_lines
from apps.devices.models import BasketDevice, CheckoutTerminal, DeviceCommand
from apps.realtime import publish_basket_event, publish_terminal_event

from .models import MatrixScanEvent, Sale, SaleLine, StockMovement


class DomainError(Exception):
    def __init__(self, code, http_status, **details):
        super().__init__(code)
        self.code = code
        self.http_status = http_status
        self.details = details


def scan_result_payload(scan, duplicate=False):
    return {
        "event_id": str(scan.event_id),
        "duplicate": duplicate,
        "result": scan.result.lower(),
        "session_id": str(scan.session_id) if scan.session_id else None,
        "version": scan.resulting_version,
    }


def _scan_quality_is_valid(payload):
    return (
        payload["frame_errors"] <= settings.KITUNGA_MAX_FRAME_ERRORS
        and payload["copy_disagreements"] <= settings.KITUNGA_MAX_COPY_DISAGREEMENTS
        and payload["cell_contrast"] >= Decimal(settings.KITUNGA_MIN_CELL_CONTRAST)
    )


@transaction.atomic
def select_basket_from_scan(terminal, payload):
    existing = MatrixScanEvent.objects.select_related("session").filter(
        terminal=terminal,
        event_id=payload["event_id"],
    ).first()
    if existing:
        return existing, True

    CheckoutTerminal.objects.filter(pk=terminal.pk).update(last_seen_at=timezone.now())
    initial_result = (
        MatrixScanEvent.Result.NO_OPEN_SESSION
        if _scan_quality_is_valid(payload)
        else MatrixScanEvent.Result.QUALITY_REJECTED
    )
    try:
        with transaction.atomic():
            scan = MatrixScanEvent.objects.create(
                terminal=terminal,
                event_id=payload["event_id"],
                matrix_id=payload["matrix_id"],
                frame_errors=payload["frame_errors"],
                copy_disagreements=payload["copy_disagreements"],
                cell_contrast=payload["cell_contrast"],
                scanned_at=payload.get("scanned_at"),
                result=initial_result,
            )
    except IntegrityError:
        duplicate = MatrixScanEvent.objects.select_related("session").get(
            terminal=terminal,
            event_id=payload["event_id"],
        )
        return duplicate, True

    if scan.result == MatrixScanEvent.Result.QUALITY_REJECTED:
        return scan, False

    device = BasketDevice.objects.filter(matrix_id=scan.matrix_id, enabled=True).first()
    if device is None:
        scan.result = MatrixScanEvent.Result.UNKNOWN_MATRIX
        scan.save(update_fields=("result",))
        return scan, False

    session = (
        BasketSession.objects.select_related("device", "selected_terminal")
        .filter(
            device=device,
            status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING),
        )
        .first()
    )
    if session is None:
        return scan, False
    scan.session = session

    if session.status == BasketSession.Status.CHECKOUT_PENDING:
        scan.result = MatrixScanEvent.Result.ALREADY_SELECTED
        scan.resulting_version = session.version
        scan.save(update_fields=("session", "result", "resulting_version"))
        return scan, False

    expected_version = session.version
    now = timezone.now()
    changed = BasketSession.objects.filter(
        pk=session.pk,
        status=BasketSession.Status.OPEN,
        version=expected_version,
    ).update(
        status=BasketSession.Status.CHECKOUT_PENDING,
        version=F("version") + 1,
        selected_terminal=terminal,
        checkout_started_at=now,
        updated_at=now,
    )
    if changed != 1:
        scan.result = MatrixScanEvent.Result.VERSION_CONFLICT
        scan.save(update_fields=("session", "result"))
        return scan, False

    session.status = BasketSession.Status.CHECKOUT_PENDING
    session.version = expected_version + 1
    session.selected_terminal = terminal
    session.checkout_started_at = now
    scan.result = MatrixScanEvent.Result.SELECTED
    scan.resulting_version = session.version
    scan.save(update_fields=("session", "result", "resulting_version"))
    transaction.on_commit(
        lambda: publish_terminal_event(
            terminal,
            {
                "type": "checkout.basket_selected",
                "session_id": str(session.id),
                "matrix_id": device.matrix_id,
                "version": session.version,
            },
        )
    )
    transaction.on_commit(lambda: publish_basket_event(session, "checkout.selected"))
    return scan, False


@transaction.atomic
def begin_manual_checkout(session_id, user, payload):
    """Lock an active basket for human review without a matrix scanner."""
    session = BasketSession.objects.filter(pk=session_id).first()
    if session is None:
        raise DomainError("session_not_found", 404)
    if session.status != BasketSession.Status.OPEN:
        raise DomainError("basket_locked", 409)
    if session.version != payload["expected_version"]:
        raise DomainError("version_conflict", 409, current_version=session.version)

    now = timezone.now()
    changed = BasketSession.objects.filter(
        pk=session.pk,
        status=BasketSession.Status.OPEN,
        version=payload["expected_version"],
    ).update(
        status=BasketSession.Status.CHECKOUT_PENDING,
        version=F("version") + 1,
        checkout_started_at=now,
        updated_at=now,
    )
    if changed != 1:
        raise DomainError("version_conflict", 409)

    BasketCorrection.objects.create(
        session=session,
        author=user,
        action="MANUAL_CHECKOUT",
        reason="Vérification manuelle depuis le backend",
        before={"status": BasketSession.Status.OPEN},
        after={"status": BasketSession.Status.CHECKOUT_PENDING},
    )
    session = session_with_lines(session.id)
    transaction.on_commit(lambda: publish_basket_event(session, "checkout.manually_selected"))
    return session


@transaction.atomic
def correct_line(session_id, line_id, user, payload):
    session = BasketSession.objects.filter(pk=session_id).first()
    if session is None:
        raise DomainError("session_not_found", 404)
    if session.status != BasketSession.Status.CHECKOUT_PENDING:
        raise DomainError("basket_locked", 409)
    if session.version != payload["expected_version"]:
        raise DomainError("version_conflict", 409, current_version=session.version)

    line = BasketLine.objects.select_related("product").filter(pk=line_id, session=session).first()
    if line is None:
        raise DomainError("line_not_found", 404)

    product = line.product
    if "product_id" in payload and payload["product_id"] != line.product_id:
        product = Product.objects.filter(pk=payload["product_id"], is_active=True).first()
        if product is None:
            raise DomainError("product_not_found", 404)
        if BasketLine.objects.filter(session=session, product=product).exclude(pk=line.pk).exists():
            raise DomainError("duplicate_line", 409)

    before = {
        "product_id": line.product_id,
        "quantity": line.quantity,
        "unit_price": str(line.unit_price_snapshot),
    }
    now = timezone.now()
    changed = BasketSession.objects.filter(
        pk=session.pk,
        status=BasketSession.Status.CHECKOUT_PENDING,
        version=payload["expected_version"],
    ).update(version=F("version") + 1, updated_at=now)
    if changed != 1:
        raise DomainError("version_conflict", 409)

    if payload["quantity"] == 0:
        after = {}
        correction_line_id = line.id
        line.delete()
        action = "REMOVE_LINE"
    else:
        line.product = product
        line.quantity = payload["quantity"]
        if product.pk != before["product_id"]:
            line.unit_price_snapshot = product.price
        line.save(update_fields=("product", "quantity", "unit_price_snapshot", "updated_at"))
        after = {
            "product_id": line.product_id,
            "quantity": line.quantity,
            "unit_price": str(line.unit_price_snapshot),
        }
        correction_line_id = line.id
        action = "UPDATE_LINE"

    BasketCorrection.objects.create(
        session=session,
        line_id=correction_line_id,
        author=user,
        action=action,
        reason=payload["reason"],
        before=before,
        after=after,
    )
    session.version += 1
    session = session_with_lines(session.id)
    transaction.on_commit(lambda: publish_basket_event(session))
    return session


@transaction.atomic
def remove_uncatalogued_line(session_id, line_id, user, payload):
    session = BasketSession.objects.filter(pk=session_id).first()
    if session is None:
        raise DomainError("session_not_found", 404)
    if session.status != BasketSession.Status.CHECKOUT_PENDING:
        raise DomainError("basket_locked", 409)
    if session.version != payload["expected_version"]:
        raise DomainError("version_conflict", 409, current_version=session.version)

    line = UncataloguedBasketLine.objects.filter(pk=line_id, session=session).first()
    if line is None:
        raise DomainError("uncatalogued_line_not_found", 404)

    now = timezone.now()
    changed = BasketSession.objects.filter(
        pk=session.pk,
        status=BasketSession.Status.CHECKOUT_PENDING,
        version=payload["expected_version"],
    ).update(version=F("version") + 1, updated_at=now)
    if changed != 1:
        raise DomainError("version_conflict", 409)

    BasketCorrection.objects.create(
        session=session,
        line_id=line.id,
        author=user,
        action="REMOVE_UNCATALOGUED_LINE",
        reason=payload["reason"],
        before={"detected_label": line.detected_label, "quantity": line.quantity},
        after={},
    )
    line.delete()
    session = session_with_lines(session.id)
    transaction.on_commit(lambda: publish_basket_event(session))
    return session


@transaction.atomic
def release_basket(session_id, user, payload):
    session = BasketSession.objects.filter(pk=session_id).first()
    if session is None:
        raise DomainError("session_not_found", 404)
    if session.status != BasketSession.Status.CHECKOUT_PENDING:
        raise DomainError("basket_locked", 409)
    if session.version != payload["expected_version"]:
        raise DomainError("version_conflict", 409, current_version=session.version)

    now = timezone.now()
    changed = BasketSession.objects.filter(
        pk=session.pk,
        status=BasketSession.Status.CHECKOUT_PENDING,
        version=payload["expected_version"],
    ).update(
        status=BasketSession.Status.OPEN,
        version=F("version") + 1,
        selected_terminal=None,
        checkout_started_at=None,
        updated_at=now,
    )
    if changed != 1:
        raise DomainError("version_conflict", 409)

    BasketCorrection.objects.create(
        session=session,
        author=user,
        action="RELEASE",
        reason=payload["reason"],
        before={"status": BasketSession.Status.CHECKOUT_PENDING},
        after={"status": BasketSession.Status.OPEN},
    )
    session = session_with_lines(session.id)
    transaction.on_commit(lambda: publish_basket_event(session, "checkout.released"))
    return session


@transaction.atomic
def cancel_basket(session_id, user, payload):
    session = BasketSession.objects.filter(pk=session_id).first()
    if session is None:
        raise DomainError("session_not_found", 404)
    if session.status not in (BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING):
        raise DomainError("basket_locked", 409)
    if session.version != payload["expected_version"]:
        raise DomainError("version_conflict", 409, current_version=session.version)

    previous_status = session.status
    now = timezone.now()
    changed = BasketSession.objects.filter(
        pk=session.pk,
        status=previous_status,
        version=payload["expected_version"],
    ).update(
        status=BasketSession.Status.CANCELLED,
        version=F("version") + 1,
        cancelled_at=now,
        updated_at=now,
    )
    if changed != 1:
        raise DomainError("version_conflict", 409)

    BasketCorrection.objects.create(
        session=session,
        author=user,
        action="CANCEL",
        reason=payload["reason"],
        before={"status": previous_status},
        after={"status": BasketSession.Status.CANCELLED},
    )
    session = session_with_lines(session.id)
    transaction.on_commit(lambda: publish_basket_event(session, "basket.cancelled"))
    return session


def serialize_sale(sale, duplicate=False):
    return {
        "id": str(sale.id),
        "sale_number": sale.sale_number,
        "session_id": str(sale.session_id),
        "subtotal": str(sale.subtotal),
        "total": str(sale.total),
        "payment_method": sale.payment_method,
        "payment_status": sale.payment_status,
        "duplicate": duplicate,
        "created_at": sale.created_at,
    }


@transaction.atomic
def complete_sale(session_id, user, idempotency_key, payload, *, payment_device=None):
    existing = Sale.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        if str(existing.session_id) != str(session_id):
            raise DomainError("idempotency_key_conflict", 409)
        return existing, True

    session = session_with_lines(session_id)
    if session is None:
        raise DomainError("session_not_found", 404)
    if session.status != BasketSession.Status.CHECKOUT_PENDING:
        raise DomainError("basket_locked", 409)
    if session.version != payload["expected_version"]:
        raise DomainError("version_conflict", 409, current_version=session.version)

    if session.uncatalogued_lines.exists():
        raise DomainError("uncatalogued_objects_pending", 422)
    lines = list(session.lines.all())
    if not lines:
        raise DomainError("empty_basket", 422)

    now = timezone.now()
    changed = BasketSession.objects.filter(
        pk=session.pk,
        status=BasketSession.Status.CHECKOUT_PENDING,
        version=payload["expected_version"],
    ).update(
        status=BasketSession.Status.COMPLETED,
        version=F("version") + 1,
        completed_at=now,
        updated_at=now,
    )
    if changed != 1:
        raise DomainError("version_conflict", 409)

    total = sum((line.subtotal for line in lines), Decimal("0"))
    sale = Sale.objects.create(
        session=session,
        cashier=user,
        payment_device=payment_device,
        subtotal=total,
        total=total,
        payment_method=payload["payment_method"],
        payment_status=payload["payment_status"],
        idempotency_key=idempotency_key,
    )

    for line in sorted(lines, key=lambda item: item.product_id):
        stock_changed = Product.objects.filter(
            pk=line.product_id,
            stock__gte=line.quantity,
        ).update(stock=F("stock") - line.quantity)
        if stock_changed != 1:
            current_stock = Product.objects.filter(pk=line.product_id).values_list("stock", flat=True).first()
            raise DomainError(
                "insufficient_stock",
                409,
                product_id=line.product_id,
                available=current_stock,
                requested=line.quantity,
            )

        SaleLine.objects.create(
            sale=sale,
            product=line.product,
            product_sku=line.product.sku,
            product_name=line.product.name,
            unit_price=line.unit_price_snapshot,
            quantity=line.quantity,
            line_total=line.subtotal,
        )
        StockMovement.objects.create(
            product=line.product,
            movement_type=StockMovement.Type.SALE,
            quantity=-line.quantity,
            sale=sale,
            author=user,
            reason=f"Vente {sale.sale_number}",
        )

    DeviceCommand.objects.get_or_create(
        device=session.device,
        command_type=DeviceCommand.Type.RESET_SESSION,
        session_id=session.id,
    )
    BasketDevice.objects.filter(pk=session.device_id).update(reset_state=BasketDevice.ResetState.PENDING)
    session.status = BasketSession.Status.COMPLETED
    session.version += 1
    transaction.on_commit(lambda: publish_basket_event(session, "sale.completed"))
    if session.selected_terminal_id:
        transaction.on_commit(
            lambda: publish_terminal_event(
                session.selected_terminal,
                {
                    "type": "sale.completed",
                    "session_id": str(session.id),
                    "sale_id": str(sale.id),
                    "version": session.version,
                },
            )
        )
    return sale, False
