from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.baskets.models import BasketSession
from apps.checkout.models import Sale
from apps.checkout.services import DomainError, complete_sale

from .models import RfidPaymentRequest, Wallet, WalletTransaction


class RfidPaymentError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def _payment_payload(payment_request, event_type):
    return {
        "type": event_type,
        "request_id": str(payment_request.id),
        "session_id": str(payment_request.session_id),
        "matrix_id": payment_request.device.matrix_id,
        "customer": payment_request.card.customer.display_name,
        "amount": str(payment_request.amount),
        "balance": str(payment_request.balance_snapshot),
        "status": payment_request.status,
    }


def _schedule_payment_event(payment_request, event_type):
    payload = _payment_payload(payment_request, event_type)

    def publish():
        from apps.realtime import publish_rfid_payment_event

        publish_rfid_payment_event(payload)

    transaction.on_commit(publish)


def prepare_rfid_payment_request(*, session, device, card, wallet, idempotency_key, amount):
    amount = Decimal(amount)
    sufficient = wallet.balance >= amount
    desired_status = (
        RfidPaymentRequest.Status.PENDING
        if sufficient
        else RfidPaymentRequest.Status.INSUFFICIENT_FUNDS
    )
    payment_request = (
        RfidPaymentRequest.objects.select_for_update()
        .filter(session=session)
        .first()
    )
    if payment_request is None:
        payment_request = RfidPaymentRequest.objects.create(
            session=session,
            device=device,
            card=card,
            wallet=wallet,
            idempotency_key=idempotency_key,
            amount=amount,
            balance_snapshot=wallet.balance,
            session_version=session.version,
            status=desired_status,
        )
    elif payment_request.status != RfidPaymentRequest.Status.APPROVED:
        payment_request.device = device
        payment_request.card = card
        payment_request.wallet = wallet
        payment_request.idempotency_key = idempotency_key
        payment_request.amount = amount
        payment_request.balance_snapshot = wallet.balance
        payment_request.session_version = session.version
        payment_request.status = desired_status
        payment_request.reviewed_by = None
        payment_request.reviewed_at = None
        payment_request.save(
            update_fields=(
                "device",
                "card",
                "wallet",
                "idempotency_key",
                "amount",
                "balance_snapshot",
                "session_version",
                "status",
                "reviewed_by",
                "reviewed_at",
                "updated_at",
            )
        )
    event_type = "rfid.payment.requested" if sufficient else "rfid.payment.insufficient"
    _schedule_payment_event(payment_request, event_type)
    return payment_request, sufficient


@transaction.atomic
def refresh_insufficient_payment_requests(wallet):
    payment_requests = list(
        RfidPaymentRequest.objects.select_for_update()
        .select_related("device", "card__customer", "session")
        .filter(
            wallet=wallet,
            status=RfidPaymentRequest.Status.INSUFFICIENT_FUNDS,
            amount__lte=wallet.balance,
            session__status=BasketSession.Status.CHECKOUT_PENDING,
        )
    )
    for payment_request in payment_requests:
        payment_request.status = RfidPaymentRequest.Status.PENDING
        payment_request.balance_snapshot = wallet.balance
        payment_request.reviewed_by = None
        payment_request.reviewed_at = None
        payment_request.save(
            update_fields=("status", "balance_snapshot", "reviewed_by", "reviewed_at", "updated_at")
        )
        _schedule_payment_event(payment_request, "rfid.payment.requested")
    return payment_requests


def cancel_rfid_payment_request_for_session(*, session_id, sale=None):
    payment_request = (
        RfidPaymentRequest.objects.select_for_update()
        .select_related("device", "card__customer")
        .filter(
            session_id=session_id,
            status__in=(
                RfidPaymentRequest.Status.PENDING,
                RfidPaymentRequest.Status.INSUFFICIENT_FUNDS,
            ),
        )
        .first()
    )
    if payment_request is None:
        return None
    payment_request.status = RfidPaymentRequest.Status.CANCELLED
    payment_request.sale = sale
    payment_request.save(update_fields=("status", "sale", "updated_at"))
    _schedule_payment_event(payment_request, "rfid.payment.cancelled")
    return payment_request


@transaction.atomic
def confirm_rfid_payment_request(*, request_id, reviewer):
    payment_request = (
        RfidPaymentRequest.objects.select_for_update()
        .select_related("device", "card__customer", "wallet", "sale")
        .filter(pk=request_id)
        .first()
    )
    if payment_request is None:
        raise RfidPaymentError("payment_request_not_found")
    if payment_request.status == RfidPaymentRequest.Status.APPROVED and payment_request.sale_id:
        return payment_request.sale, True
    if payment_request.status != RfidPaymentRequest.Status.PENDING:
        raise RfidPaymentError("payment_request_not_pending")

    session = BasketSession.objects.select_for_update().filter(pk=payment_request.session_id).first()
    if session is None or session.status != BasketSession.Status.CHECKOUT_PENDING:
        raise RfidPaymentError("basket_locked")
    if session.version != payment_request.session_version:
        raise RfidPaymentError("basket_changed")
    current_total = sum((line.subtotal for line in session.lines.all()), Decimal("0"))
    if current_total != payment_request.amount:
        raise RfidPaymentError("basket_changed")

    wallet = Wallet.objects.select_for_update().filter(pk=payment_request.wallet_id, is_active=True).first()
    if wallet is None:
        raise RfidPaymentError("wallet_not_found")
    if wallet.balance < payment_request.amount:
        payment_request.status = RfidPaymentRequest.Status.INSUFFICIENT_FUNDS
        payment_request.balance_snapshot = wallet.balance
        payment_request.reviewed_by = reviewer
        payment_request.reviewed_at = timezone.now()
        payment_request.save(
            update_fields=("status", "balance_snapshot", "reviewed_by", "reviewed_at", "updated_at")
        )
        _schedule_payment_event(payment_request, "rfid.payment.insufficient")
        return None, False

    Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") - payment_request.amount)
    wallet.refresh_from_db(fields=("balance",))
    try:
        sale, duplicate = complete_sale(
            session.id,
            reviewer,
            payment_request.idempotency_key,
            {
                "expected_version": payment_request.session_version,
                "payment_method": "RFID",
                "payment_status": Sale.PaymentStatus.PAID,
            },
            payment_device=payment_request.device,
        )
    except DomainError as error:
        raise RfidPaymentError(error.code) from error

    WalletTransaction.objects.get_or_create(
        idempotency_key=payment_request.idempotency_key,
        defaults={
            "wallet": wallet,
            "sale": sale,
            "kind": WalletTransaction.Kind.RFID_PAYMENT,
            "amount": -payment_request.amount,
            "balance_after": wallet.balance,
            "reason": f"Paiement RFID {sale.sale_number}",
            "created_by": reviewer,
        },
    )
    payment_request.status = RfidPaymentRequest.Status.APPROVED
    payment_request.sale = sale
    payment_request.balance_snapshot = wallet.balance
    payment_request.reviewed_by = reviewer
    payment_request.reviewed_at = timezone.now()
    payment_request.save(
        update_fields=(
            "status",
            "sale",
            "balance_snapshot",
            "reviewed_by",
            "reviewed_at",
            "updated_at",
        )
    )
    _schedule_payment_event(payment_request, "rfid.payment.approved")
    return sale, duplicate


@transaction.atomic
def reject_rfid_payment_request(*, request_id, reviewer):
    payment_request = (
        RfidPaymentRequest.objects.select_for_update()
        .select_related("device", "card__customer")
        .filter(pk=request_id)
        .first()
    )
    if payment_request is None:
        raise RfidPaymentError("payment_request_not_found")
    if payment_request.status == RfidPaymentRequest.Status.APPROVED:
        raise RfidPaymentError("payment_already_approved")
    payment_request.status = RfidPaymentRequest.Status.REJECTED
    payment_request.reviewed_by = reviewer
    payment_request.reviewed_at = timezone.now()
    payment_request.save(update_fields=("status", "reviewed_by", "reviewed_at", "updated_at"))
    _schedule_payment_event(payment_request, "rfid.payment.rejected")
    return payment_request
