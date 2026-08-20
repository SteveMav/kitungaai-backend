from apps.wallets.models import RfidEnrollmentRequest, RfidPaymentRequest


def can_manage_rfid_enrollments(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name="Administrateur").exists())
    )


def rfid_enrollment_notifier(request):
    can_manage = can_manage_rfid_enrollments(request.user)
    can_process_payments = bool(
        request.user
        and request.user.is_authenticated
        and (
            request.user.is_superuser
            or request.user.groups.filter(name__in=("Administrateur", "Caissier", "Superviseur")).exists()
        )
    )
    context = {
        "can_manage_rfid_enrollments": can_manage,
        "pending_rfid_enrollment_count": 0,
        "can_process_rfid_payments": can_process_payments,
        "pending_rfid_payment": None,
    }
    if can_manage:
        context["pending_rfid_enrollment_count"] = RfidEnrollmentRequest.objects.filter(
            status=RfidEnrollmentRequest.Status.PENDING
        ).count()
    if can_process_payments:
        context["pending_rfid_payment"] = (
            RfidPaymentRequest.objects.filter(
                status__in=(
                    RfidPaymentRequest.Status.PENDING,
                    RfidPaymentRequest.Status.INSUFFICIENT_FUNDS,
                )
            )
            .select_related("device", "card__customer")
            .order_by("-updated_at")
            .first()
        )
    return context
