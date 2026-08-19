import uuid
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from .models import Customer, RfidCard, RfidEnrollmentRequest, Wallet, WalletTransaction


class WalletError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class RfidEnrollmentError(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


def normalize_rfid_uid(raw_uid):
    return "".join(str(raw_uid).strip().upper().split())


def _publish_enrollment_event(event_type, enrollment):
    from apps.realtime import publish_rfid_enrollment_event

    pending_count = RfidEnrollmentRequest.objects.filter(
        status=RfidEnrollmentRequest.Status.PENDING
    ).count()
    publish_rfid_enrollment_event(
        event_type=event_type,
        enrollment_id=enrollment.id,
        matrix_id=enrollment.device.matrix_id,
        pending_count=pending_count,
    )


def record_rfid_enrollment_request(*, device, raw_uid):
    """Create one pending approval request per card, safely under repeated scans."""
    uid = normalize_rfid_uid(raw_uid)
    try:
        with transaction.atomic():
            enrollment = (
                RfidEnrollmentRequest.objects.select_for_update()
                .select_related("device")
                .filter(uid=uid)
                .first()
            )
            if enrollment is not None:
                if enrollment.status == RfidEnrollmentRequest.Status.PENDING:
                    enrollment.device = device
                    enrollment.seen_count = F("seen_count") + 1
                    enrollment.save(update_fields=("device", "seen_count", "last_seen_at"))
                    enrollment.refresh_from_db(fields=("seen_count", "last_seen_at", "device"))
                return enrollment, False

            enrollment = RfidEnrollmentRequest.objects.create(uid=uid, device=device)
            transaction.on_commit(
                lambda: _publish_enrollment_event("rfid.enrollment.requested", enrollment)
            )
            return enrollment, True
    except IntegrityError:
        enrollment = RfidEnrollmentRequest.objects.select_related("device").get(uid=uid)
        return enrollment, False


@transaction.atomic
def approve_rfid_enrollment(*, enrollment_id, reviewer, existing_customer=None, customer_code="", display_name=""):
    enrollment = (
        RfidEnrollmentRequest.objects.select_for_update()
        .select_related("device")
        .filter(pk=enrollment_id)
        .first()
    )
    if enrollment is None:
        raise RfidEnrollmentError("enrollment_not_found")
    if enrollment.status != RfidEnrollmentRequest.Status.PENDING:
        raise RfidEnrollmentError("enrollment_not_pending")
    if RfidCard.objects.filter(uid=enrollment.uid).exists():
        raise RfidEnrollmentError("rfid_uid_already_assigned")

    if existing_customer is not None:
        customer = Customer.objects.select_for_update().filter(
            pk=existing_customer.pk,
            is_active=True,
        ).first()
        if customer is None:
            raise RfidEnrollmentError("customer_not_available")
    else:
        normalized_name = display_name.strip()
        normalized_code = customer_code.strip().upper() or f"CUST-{enrollment.id:06d}"
        if not normalized_name:
            raise RfidEnrollmentError("customer_name_required")
        if Customer.objects.filter(customer_code=normalized_code).exists():
            raise RfidEnrollmentError("customer_code_taken")
        customer = Customer.objects.create(
            customer_code=normalized_code,
            display_name=normalized_name,
        )

    Wallet.objects.get_or_create(customer=customer)
    RfidCard.objects.create(customer=customer, uid=enrollment.uid)
    enrollment.status = RfidEnrollmentRequest.Status.APPROVED
    enrollment.customer = customer
    enrollment.reviewed_by = reviewer
    enrollment.reviewed_at = timezone.now()
    enrollment.rejection_reason = ""
    enrollment.save(
        update_fields=(
            "status",
            "customer",
            "reviewed_by",
            "reviewed_at",
            "rejection_reason",
            "last_seen_at",
        )
    )
    transaction.on_commit(lambda: _publish_enrollment_event("rfid.enrollment.approved", enrollment))
    return enrollment, customer


@transaction.atomic
def reject_rfid_enrollment(*, enrollment_id, reviewer, reason=""):
    enrollment = RfidEnrollmentRequest.objects.select_for_update().filter(pk=enrollment_id).first()
    if enrollment is None:
        raise RfidEnrollmentError("enrollment_not_found")
    if enrollment.status != RfidEnrollmentRequest.Status.PENDING:
        raise RfidEnrollmentError("enrollment_not_pending")
    enrollment.status = RfidEnrollmentRequest.Status.REJECTED
    enrollment.reviewed_by = reviewer
    enrollment.reviewed_at = timezone.now()
    enrollment.rejection_reason = reason.strip()[:255]
    enrollment.save(
        update_fields=("status", "reviewed_by", "reviewed_at", "rejection_reason", "last_seen_at")
    )
    transaction.on_commit(lambda: _publish_enrollment_event("rfid.enrollment.rejected", enrollment))
    return enrollment


@transaction.atomic
def credit_wallet(*, wallet_id, amount, user, reason):
    amount = Decimal(amount)
    if amount <= 0:
        raise WalletError("invalid_top_up")

    wallet = Wallet.objects.select_for_update().filter(pk=wallet_id, is_active=True).first()
    if wallet is None:
        raise WalletError("wallet_not_found")
    Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") + amount)
    wallet.refresh_from_db(fields=("balance",))
    return WalletTransaction.objects.create(
        wallet=wallet,
        kind=WalletTransaction.Kind.TOP_UP,
        amount=amount,
        balance_after=wallet.balance,
        reason=reason.strip()[:255],
        created_by=user,
    )


def new_payment_key():
    return uuid.uuid4()
