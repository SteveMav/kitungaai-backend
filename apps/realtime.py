import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer


logger = logging.getLogger("kitunga")


def _publish(group, payload):
    try:
        channel_layer = get_channel_layer()
        if channel_layer is not None:
            async_to_sync(channel_layer.group_send)(
                group,
                {"type": "domain_message", "payload": payload},
            )
    except Exception:
        logger.warning("websocket_publish_failed", extra={"group": group}, exc_info=True)


def publish_basket_event(session, event_type="basket.updated"):
    payload = {
        "type": event_type,
        "session_id": str(session.id),
        "matrix_id": session.device.matrix_id,
        "version": session.version,
    }
    _publish(f"basket_{session.device.matrix_id}", payload)
    if session.selected_terminal_id:
        _publish(f"cashier_terminal_{session.selected_terminal.terminal_code}", payload)


def publish_terminal_event(terminal, payload):
    _publish(f"cashier_terminal_{terminal.terminal_code}", payload)


def publish_rfid_enrollment_event(*, event_type, enrollment_id, matrix_id, pending_count):
    _publish(
        "rfid_enrollment",
        {
            "type": event_type,
            "enrollment_id": enrollment_id,
            "matrix_id": matrix_id,
            "pending_count": pending_count,
        },
    )
