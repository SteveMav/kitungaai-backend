from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.catalog.models import VisionLabel
from apps.devices.models import BasketDevice
from apps.realtime import publish_basket_event

from .models import BasketLine, BasketSession, DetectionEvent


def _resolve_product(label, model_version):
    labels = VisionLabel.objects.filter(label=label.strip().lower(), is_active=True).select_related("product")
    if model_version:
        exact = labels.filter(model_version=model_version).first()
        if exact:
            return exact.product
    fallback = labels.filter(model_version="").first()
    return fallback.product if fallback else None


def detection_result_payload(event, duplicate=False):
    return {
        "event_id": str(event.event_id),
        "duplicate": duplicate,
        "result": event.result.lower(),
        "session_id": str(event.session_id) if event.session_id else None,
        "version": event.resulting_version,
        "line_quantity": event.resulting_line_quantity,
    }


def _existing_event(device, event_id):
    return DetectionEvent.objects.select_related("session", "product").filter(
        device=device,
        event_id=event_id,
    ).first()


@transaction.atomic
def ingest_detection(device, payload):
    existing = _existing_event(device, payload["event_id"])
    if existing:
        return existing, True

    session = (
        BasketSession.objects.select_related("device", "selected_terminal")
        .filter(
            device=device,
            status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING),
        )
        .first()
    )
    if session is None and device.reset_state == BasketDevice.ResetState.READY:
        try:
            with transaction.atomic():
                session = BasketSession.objects.create(device=device)
        except IntegrityError:
            session = (
                BasketSession.objects.select_related("device", "selected_terminal")
                .filter(
                    device=device,
                    status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING),
                )
                .first()
            )

    claimed_session_id = payload.get("session_id")
    event_session = session
    session_matches = True
    if claimed_session_id:
        event_session = BasketSession.objects.filter(pk=claimed_session_id, device=device).first()
        session_matches = bool(session and event_session and event_session.pk == session.pk)

    initial_result = DetectionEvent.Result.UNKNOWN_LABEL
    if session is None:
        initial_result = DetectionEvent.Result.RESET_PENDING
    elif session.status != BasketSession.Status.OPEN or not session_matches:
        initial_result = DetectionEvent.Result.BASKET_LOCKED

    try:
        with transaction.atomic():
            event = DetectionEvent.objects.create(
                device=device,
                session=event_session,
                event_id=payload["event_id"],
                boot_id=payload["boot_id"],
                sequence=payload["sequence"],
                action=payload["action"],
                detected_label=payload["detected_label"].strip().lower(),
                confidence=payload["confidence"],
                quantity=payload["quantity"],
                model_version=payload.get("model_version", ""),
                captured_at=payload["captured_at"],
                result=initial_result,
                is_legacy=payload.get("legacy", False),
            )
    except IntegrityError:
        return _existing_event(device, payload["event_id"]), True

    if session is None or session.status != BasketSession.Status.OPEN or not session_matches:
        return event, False

    product = _resolve_product(event.detected_label, event.model_version)
    if product is None or not product.is_active:
        return event, False

    event.product = product
    expected_version = session.version
    line = BasketLine.objects.filter(session=session, product=product).first()

    if event.action == DetectionEvent.Action.ITEM_REMOVED and (
        line is None or line.quantity < event.quantity
    ):
        event.result = DetectionEvent.Result.INVALID_REMOVAL
        event.save(update_fields=("product", "result"))
        return event, False

    changed = BasketSession.objects.filter(
        pk=session.pk,
        status=BasketSession.Status.OPEN,
        version=expected_version,
    ).update(version=F("version") + 1, updated_at=timezone.now())
    if changed != 1:
        event.result = DetectionEvent.Result.VERSION_CONFLICT
        event.save(update_fields=("product", "result"))
        return event, False

    if event.action == DetectionEvent.Action.ITEM_ADDED:
        if line is None:
            line = BasketLine.objects.create(
                session=session,
                product=product,
                quantity=event.quantity,
                unit_price_snapshot=product.price,
            )
        else:
            line.quantity = F("quantity") + event.quantity
            line.save(update_fields=("quantity", "updated_at"))
            line.refresh_from_db(fields=("quantity",))
    else:
        new_quantity = line.quantity - event.quantity
        if new_quantity == 0:
            line.delete()
            line = None
        else:
            line.quantity = new_quantity
            line.save(update_fields=("quantity", "updated_at"))

    session.version = expected_version + 1
    event.result = DetectionEvent.Result.APPLIED
    event.resulting_version = session.version
    event.resulting_line_quantity = line.quantity if line else 0
    event.save(
        update_fields=("product", "result", "resulting_version", "resulting_line_quantity")
    )
    transaction.on_commit(lambda: publish_basket_event(session))
    return event, False
