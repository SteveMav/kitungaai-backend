from django.db import transaction
from django.utils import timezone

from apps.baskets.models import BasketSession

from .models import BasketDevice, DeviceCommand


def active_session_for_device(device):
    return (
        BasketSession.objects.filter(
            device=device,
            status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING),
        )
        .select_related("device", "selected_terminal")
        .first()
    )


@transaction.atomic
def process_heartbeat(device, payload):
    now = timezone.now()
    updates = {"last_seen_at": now}
    if "firmware_version" in payload:
        updates["firmware_version"] = payload["firmware_version"]
    if "boot_id" in payload:
        updates["last_boot_id"] = payload["boot_id"]
    BasketDevice.objects.filter(pk=device.pk).update(**updates)
    for key, value in updates.items():
        setattr(device, key, value)

    session = active_session_for_device(device)
    command = (
        DeviceCommand.objects.filter(device=device, status=DeviceCommand.Status.PENDING)
        .order_by("created_at")
        .first()
    )
    return device, session, command


@transaction.atomic
def acknowledge_command(device, command_id):
    command = DeviceCommand.objects.select_for_update().filter(pk=command_id, device=device).first()
    if command is None:
        return None, False
    if command.status == DeviceCommand.Status.ACKNOWLEDGED:
        return command, True

    command.status = DeviceCommand.Status.ACKNOWLEDGED
    command.acknowledged_at = timezone.now()
    command.save(update_fields=("status", "acknowledged_at"))
    BasketDevice.objects.filter(pk=device.pk).update(reset_state=BasketDevice.ResetState.READY)
    device.reset_state = BasketDevice.ResetState.READY
    return command, False


def device_state_payload(device, session, command=None):
    return {
        "device_code": device.device_code,
        "matrix_id": device.matrix_id,
        "enabled": device.enabled,
        "last_seen_at": device.last_seen_at,
        "reset_state": device.reset_state,
        "session": (
            {
                "id": str(session.id),
                "status": session.status,
                "version": session.version,
            }
            if session
            else None
        ),
        "command": (
            {
                "id": str(command.id),
                "type": command.command_type,
                "session_id": str(command.session_id),
                "status": command.status,
            }
            if command
            else None
        ),
    }
