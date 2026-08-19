import uuid

from rest_framework import status
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.baskets.selectors import serialize_session, session_with_lines
from apps.devices.authentication import CheckoutTerminalAuthentication
from apps.devices.throttles import TerminalRateThrottle

from .models import MatrixScanEvent
from .permissions import (
    CanCancelBasket,
    CanCompleteSale,
    CanCorrectBasket,
    CanReleaseBasket,
    CashierAccess,
)
from .serializers import (
    CompleteSaleSerializer,
    CorrectLineSerializer,
    ExpectedVersionSerializer,
    MatrixScanSerializer,
)
from .services import (
    DomainError,
    cancel_basket,
    complete_sale,
    correct_line,
    release_basket,
    scan_result_payload,
    select_basket_from_scan,
    serialize_sale,
)


SCAN_STATUS = {
    MatrixScanEvent.Result.SELECTED: status.HTTP_200_OK,
    MatrixScanEvent.Result.UNKNOWN_MATRIX: status.HTTP_404_NOT_FOUND,
    MatrixScanEvent.Result.NO_OPEN_SESSION: status.HTTP_409_CONFLICT,
    MatrixScanEvent.Result.ALREADY_SELECTED: status.HTTP_409_CONFLICT,
    MatrixScanEvent.Result.QUALITY_REJECTED: status.HTTP_422_UNPROCESSABLE_ENTITY,
    MatrixScanEvent.Result.VERSION_CONFLICT: status.HTTP_409_CONFLICT,
}


def domain_error_response(error):
    return Response({"error": error.code, **error.details}, status=error.http_status)


class MatrixScanView(APIView):
    authentication_classes = (CheckoutTerminalAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (TerminalRateThrottle,)

    def post(self, request):
        serializer = MatrixScanSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "invalid_scan", "fields": serializer.errors},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        event_id = str(serializer.validated_data["event_id"])
        if request.headers.get("Idempotency-Key", "") != event_id:
            return Response(
                {"error": "invalid_scan", "fields": {"Idempotency-Key": ["Doit correspondre à event_id."]}},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        scan, duplicate = select_basket_from_scan(request.auth, serializer.validated_data)
        payload = scan_result_payload(scan, duplicate)
        if duplicate:
            return Response(payload)
        if scan.result != MatrixScanEvent.Result.SELECTED:
            payload["error"] = scan.result.lower()
        return Response(payload, status=SCAN_STATUS[scan.result])


class CashierAPIView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated, CashierAccess)


class CashierSessionView(CashierAPIView):
    def get(self, request, session_id):
        session = session_with_lines(session_id)
        if session is None:
            return Response({"error": "session_not_found"}, status=status.HTTP_404_NOT_FOUND)
        return Response(serialize_session(session))


class CorrectLineView(CashierAPIView):
    permission_classes = (IsAuthenticated, CashierAccess, CanCorrectBasket)

    def patch(self, request, session_id, line_id):
        serializer = CorrectLineSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = correct_line(session_id, line_id, request.user, serializer.validated_data)
        except DomainError as error:
            return domain_error_response(error)
        return Response(serialize_session(session))


class CompleteSaleView(CashierAPIView):
    permission_classes = (IsAuthenticated, CashierAccess, CanCompleteSale)

    def post(self, request, session_id):
        serializer = CompleteSaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_key = request.headers.get("Idempotency-Key", "")
        try:
            idempotency_key = uuid.UUID(raw_key)
        except (TypeError, ValueError):
            return Response({"error": "invalid_idempotency_key"}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)
        try:
            sale, duplicate = complete_sale(
                session_id,
                request.user,
                idempotency_key,
                serializer.validated_data,
            )
        except DomainError as error:
            return domain_error_response(error)
        return Response(
            serialize_sale(sale, duplicate),
            status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED,
        )


class ReleaseBasketView(CashierAPIView):
    permission_classes = (IsAuthenticated, CashierAccess, CanReleaseBasket)

    def post(self, request, session_id):
        serializer = ExpectedVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = release_basket(session_id, request.user, serializer.validated_data)
        except DomainError as error:
            return domain_error_response(error)
        return Response(serialize_session(session))


class CancelBasketView(CashierAPIView):
    permission_classes = (IsAuthenticated, CashierAccess, CanCancelBasket)

    def post(self, request, session_id):
        serializer = ExpectedVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = cancel_basket(session_id, request.user, serializer.validated_data)
        except DomainError as error:
            return domain_error_response(error)
        return Response(serialize_session(session))
