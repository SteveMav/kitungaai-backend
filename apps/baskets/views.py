from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.devices.authentication import BasketDeviceAuthentication
from apps.devices.throttles import DeviceRateThrottle

from .models import DetectionEvent
from .serializers import DetectionEventSerializer
from .services import detection_result_payload, ingest_detection


RESULT_STATUS = {
    DetectionEvent.Result.APPLIED: status.HTTP_201_CREATED,
    DetectionEvent.Result.UNKNOWN_LABEL: status.HTTP_404_NOT_FOUND,
    DetectionEvent.Result.BASKET_LOCKED: status.HTTP_409_CONFLICT,
    DetectionEvent.Result.RESET_PENDING: status.HTTP_409_CONFLICT,
    DetectionEvent.Result.INVALID_REMOVAL: status.HTTP_422_UNPROCESSABLE_ENTITY,
    DetectionEvent.Result.VERSION_CONFLICT: status.HTTP_409_CONFLICT,
}


class DetectionEventView(APIView):
    authentication_classes = (BasketDeviceAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (DeviceRateThrottle,)

    def post(self, request, device_code):
        serializer = DetectionEventSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "invalid_event", "fields": serializer.errors},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        event_id = str(serializer.validated_data["event_id"])
        if not serializer.validated_data.get("session_id"):
            return Response(
                {"error": "invalid_event", "fields": {"session_id": ["Requis depuis la réponse heartbeat."]}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        idempotency_key = request.headers.get("Idempotency-Key", "")
        if idempotency_key != event_id:
            return Response(
                {"error": "invalid_event", "fields": {"Idempotency-Key": ["Doit correspondre à event_id."]}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        event, duplicate = ingest_detection(request.auth, serializer.validated_data)
        payload = detection_result_payload(event, duplicate)
        if duplicate:
            return Response(payload, status=status.HTTP_200_OK)
        payload_status = RESULT_STATUS[event.result]
        if event.result == DetectionEvent.Result.UNKNOWN_LABEL:
            payload["error"] = "unknown_label"
        elif event.result == DetectionEvent.Result.BASKET_LOCKED:
            payload["error"] = "basket_locked"
        elif event.result == DetectionEvent.Result.RESET_PENDING:
            payload["error"] = "basket_locked"
        elif event.result == DetectionEvent.Result.VERSION_CONFLICT:
            payload["error"] = "version_conflict"
        elif event.result == DetectionEvent.Result.INVALID_REMOVAL:
            payload["error"] = "invalid_event"
        return Response(payload, status=payload_status)
