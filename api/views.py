"""Adaptateurs temporaires pour les routes historiques de Kitunga.

La logique métier et les données autoritatives vivent dans les apps V1. Ces vues
conservent les chemins historiques pendant la migration des clients matériels et
du frontend, tout en appliquant les mêmes contrôles d'authentification.
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.baskets.models import BasketLine, BasketSession, DetectionEvent
from apps.baskets.selectors import serialize_session, session_with_lines
from apps.baskets.serializers import DetectionEventSerializer
from apps.baskets.services import detection_result_payload, ingest_detection
from apps.checkout.permissions import CanCorrectBasket, CashierAccess
from apps.checkout.services import DomainError, correct_line
from apps.dashboard.views import DashboardStatsView
from apps.devices.authentication import BasketDeviceAuthentication
from apps.devices.services import active_session_for_device, process_heartbeat
from apps.devices.throttles import DeviceRateThrottle


def _legacy_basket_payload(session):
    payload = serialize_session(session)
    return {
        "id": payload["id"],
        "device_id": payload["device_code"],
        "status": "ACTIVE" if payload["status"] == BasketSession.Status.OPEN else payload["status"],
        "items": [
            {
                "id": line["id"],
                "product": line["product"]["id"],
                "product_details": {
                    **line["product"],
                    "price": line["unit_price"],
                },
                "quantity": line["quantity"],
                "subtotal": line["subtotal"],
            }
            for line in payload["lines"]
        ],
        "item_count": payload["item_count"],
        "total_price": payload["total"],
        "version": payload["version"],
    }


@api_view(["POST"])
@authentication_classes((BasketDeviceAuthentication,))
@permission_classes((IsAuthenticated,))
@throttle_classes((DeviceRateThrottle,))
def add_detection(request, device_id=None):
    label = request.data.get("detected_label") or request.data.get("label")
    if not label:
        device, session, _command = process_heartbeat(request.auth, {})
        session = session_with_lines(session.id) if session else None
        return Response(
            {
                "message": "Panier actif vérifié.",
                "code": device.device_code,
                "basket": _legacy_basket_payload(session) if session else None,
            }
        )

    event_id = request.data.get("event_id") or request.headers.get("Idempotency-Key")
    if not event_id or request.headers.get("Idempotency-Key") != str(event_id):
        return Response(
            {"error": "invalid_event", "detail": "event_id et Idempotency-Key sont obligatoires et identiques."},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    try:
        active_session = active_session_for_device(request.auth)
        if active_session is None:
            _device, active_session, _command = process_heartbeat(request.auth, {})
        quantity = int(request.data.get("quantity", 1))
        confidence = request.data.get("confidence", "1.0")
        sequence = int(request.data.get("sequence", 0))
        captured_at = request.data.get("captured_at") or timezone.now()
        action = request.data.get("action", DetectionEvent.Action.ITEM_ADDED)
        payload = {
            "event_id": event_id,
            "session_id": request.data.get("session_id") or (active_session.id if active_session else None),
            "boot_id": str(request.data.get("boot_id", "legacy"))[:96],
            "sequence": sequence,
            "captured_at": captured_at,
            "action": action,
            "detected_label": str(label)[:128],
            "confidence": confidence,
            "quantity": quantity,
            "model_version": str(request.data.get("model_version", ""))[:64],
            "legacy": True,
        }
    except (TypeError, ValueError):
        return Response({"error": "invalid_event"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

    serializer = DetectionEventSerializer(data=payload)
    if not serializer.is_valid():
        return Response(
            {"error": "invalid_event", "fields": serializer.errors},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    event, duplicate = ingest_detection(request.auth, serializer.validated_data)

    response_payload = detection_result_payload(event, duplicate)
    if event.result == DetectionEvent.Result.APPLIED:
        session = session_with_lines(event.session_id)
        response_payload.update(
            {
                "message": "Événement appliqué.",
                "code": request.auth.device_code,
                "basket": _legacy_basket_payload(session),
            }
        )
        return Response(response_payload, status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED)
    error_status = {
        DetectionEvent.Result.UNKNOWN_LABEL: status.HTTP_404_NOT_FOUND,
        DetectionEvent.Result.BASKET_LOCKED: status.HTTP_409_CONFLICT,
        DetectionEvent.Result.RESET_PENDING: status.HTTP_409_CONFLICT,
        DetectionEvent.Result.INVALID_REMOVAL: status.HTTP_422_UNPROCESSABLE_ENTITY,
        DetectionEvent.Result.VERSION_CONFLICT: status.HTTP_409_CONFLICT,
    }[event.result]
    response_payload["error"] = event.result.lower()
    return Response(response_payload, status=error_status)


@api_view(["GET"])
@authentication_classes((SessionAuthentication,))
@permission_classes((IsAuthenticated, CashierAccess))
def get_basket(request, device_id):
    device = request.query_params.get("device_code", device_id)
    session = BasketSession.objects.filter(
        device__device_code=device,
        status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING),
    ).first()
    if session is None:
        return Response({"error": "session_not_found"}, status=status.HTTP_404_NOT_FOUND)
    return Response(_legacy_basket_payload(session_with_lines(session.id)))


@api_view(["POST"])
@authentication_classes((SessionAuthentication,))
@permission_classes((IsAuthenticated, CashierAccess, CanCorrectBasket))
def remove_item(request, device_id):
    session = BasketSession.objects.filter(
        device__device_code=device_id,
        status=BasketSession.Status.CHECKOUT_PENDING,
    ).first()
    if session is None:
        return Response({"error": "basket_locked"}, status=status.HTTP_409_CONFLICT)
    line = BasketLine.objects.filter(session=session, product_id=request.data.get("product_id")).first()
    if line is None:
        return Response({"error": "line_not_found"}, status=status.HTTP_404_NOT_FOUND)
    try:
        expected_version = int(request.data.get("expected_version"))
        remove_quantity = int(request.data.get("quantity", 1))
    except (TypeError, ValueError):
        return Response({"error": "invalid_event"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
    payload = {
        "expected_version": expected_version,
        "quantity": max(0, line.quantity - remove_quantity),
        "reason": str(request.data.get("reason", "Correction via API legacy"))[:255],
    }
    try:
        updated = correct_line(session.id, line.id, request.user, payload)
    except DomainError as error:
        return Response({"error": error.code, **error.details}, status=error.http_status)
    return Response({"message": "Panier mis à jour.", "basket": _legacy_basket_payload(updated)})


@api_view(["POST"])
@authentication_classes((SessionAuthentication,))
@permission_classes((IsAuthenticated, CashierAccess, CanCorrectBasket))
def clear_basket(request, device_id):
    return Response(
        {"error": "deprecated_endpoint", "detail": "Corrigez chaque ligne avec sa version autoritative."},
        status=status.HTTP_410_GONE,
    )


@api_view(["GET"])
@authentication_classes((SessionAuthentication,))
@permission_classes((IsAuthenticated, CashierAccess))
def dashboard_stats(request):
    return DashboardStatsView().get(request)
