from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import BasketDeviceAuthentication
from .models import DeviceCommand
from .serializers import CommandAckSerializer, HeartbeatSerializer
from .services import acknowledge_command, active_session_for_device, device_state_payload, process_heartbeat
from .throttles import DeviceRateThrottle


class DeviceAPIView(APIView):
    authentication_classes = (BasketDeviceAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (DeviceRateThrottle,)


class HeartbeatView(DeviceAPIView):
    def post(self, request, device_code):
        serializer = HeartbeatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device, session, command = process_heartbeat(request.auth, serializer.validated_data)
        return Response(device_state_payload(device, session, command))


class DeviceStateView(DeviceAPIView):
    def get(self, request, device_code):
        session = active_session_for_device(request.auth)
        command = (
            DeviceCommand.objects.filter(device=request.auth, status=DeviceCommand.Status.PENDING)
            .order_by("created_at")
            .first()
        )
        return Response(device_state_payload(request.auth, session, command))


class CommandAckView(DeviceAPIView):
    def post(self, request, device_code, command_id):
        serializer = CommandAckSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command, duplicate = acknowledge_command(request.auth, command_id)
        if command is None:
            return Response({"error": "command_not_found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            {
                "command_id": str(command.id),
                "status": command.status,
                "duplicate": duplicate,
                "reset_state": request.auth.reset_state,
            }
        )
