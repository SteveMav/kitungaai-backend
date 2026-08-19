from apps.wallets.models import RfidEnrollmentRequest


def can_manage_rfid_enrollments(user):
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or user.groups.filter(name="Administrateur").exists())
    )


def rfid_enrollment_notifier(request):
    if not can_manage_rfid_enrollments(request.user):
        return {"can_manage_rfid_enrollments": False, "pending_rfid_enrollment_count": 0}
    return {
        "can_manage_rfid_enrollments": True,
        "pending_rfid_enrollment_count": RfidEnrollmentRequest.objects.filter(
            status=RfidEnrollmentRequest.Status.PENDING
        ).count(),
    }
