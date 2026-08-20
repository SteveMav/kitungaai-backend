import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.baskets.models import BasketLine, BasketSession, DetectionEvent
from apps.baskets.services import detection_result_payload, ingest_detection
from apps.checkout.models import Sale
from apps.devices.authentication import BasketDeviceAuthentication
from apps.devices.models import BasketDevice, DeviceCommand
from apps.devices.services import active_session_for_device
from apps.devices.throttles import DeviceRateThrottle

from .models import RfidCard, RfidEnrollmentRequest, Wallet
from .payment_services import prepare_rfid_payment_request
from .services import normalize_rfid_uid, record_rfid_enrollment_request


def _message_response(*, code, message, http_status, **extra):
    return Response({"status": code, "message": message, **extra}, status=http_status)


def _request_key(request):
    try:
        return uuid.UUID(request.headers.get("Idempotency-Key", ""))
    except (TypeError, ValueError):
        return None


def _basket_status(session):
    if session.status == BasketSession.Status.OPEN:
        return "ACTIVE"
    if session.status == BasketSession.Status.COMPLETED:
        return "PAID"
    return session.status


def _customer_payload(customer):
    return {"id": customer.customer_code, "display_name": customer.display_name}


class IoTAPIView(APIView):
    authentication_classes = (BasketDeviceAuthentication,)
    permission_classes = (IsAuthenticated,)
    throttle_classes = (DeviceRateThrottle,)


class StartSessionView(IoTAPIView):
    def post(self, request, device_code):
        raw_uid = request.data.get("rfid_uid")
        if not isinstance(raw_uid, str) or not raw_uid.strip():
            return _message_response(
                code="INVALID_RFID",
                message="rfid_uid is required.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        uid = normalize_rfid_uid(raw_uid)
        card = (
            RfidCard.objects.select_related("customer")
            .filter(uid=uid)
            .first()
        )
        if card is None:
            BasketDevice.objects.filter(pk=request.auth.pk).update(last_seen_at=timezone.now())
            enrollment, _created = record_rfid_enrollment_request(device=request.auth, raw_uid=uid)
            if enrollment.status == RfidEnrollmentRequest.Status.PENDING:
                return Response(
                    {
                        "status": "RFID_ENROLLMENT_PENDING",
                        "message": "The card is awaiting administrator approval.",
                        "enrollment_id": enrollment.id,
                    },
                    status=status.HTTP_202_ACCEPTED,
                )
            if enrollment.status == RfidEnrollmentRequest.Status.REJECTED:
                return _message_response(
                    code="RFID_ENROLLMENT_REJECTED",
                    message="This RFID card was declined by an administrator.",
                    http_status=status.HTTP_403_FORBIDDEN,
                )
            return _message_response(
                code="RFID_ENROLLMENT_INCONSISTENT",
                message="The card approval is incomplete. Contact an administrator.",
                http_status=status.HTTP_409_CONFLICT,
            )
        if not card.is_active or not card.customer.is_active:
            return _message_response(
                code="RFID_CARD_INACTIVE",
                message="RFID card is not available for purchases.",
                http_status=status.HTTP_403_FORBIDDEN,
            )

        with transaction.atomic():
            device = BasketDevice.objects.select_for_update().get(pk=request.auth.pk)
            BasketDevice.objects.filter(pk=device.pk).update(last_seen_at=timezone.now())
            session = (
                BasketSession.objects.select_for_update()
                .filter(
                    device=device,
                    status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING),
                )
                .first()
            )
            if device.reset_state != BasketDevice.ResetState.READY and session is not None:
                return _message_response(
                    code="DEVICE_RESET_PENDING",
                    message="The device must acknowledge its reset before a new session.",
                    http_status=status.HTTP_409_CONFLICT,
                )
            if device.reset_state != BasketDevice.ResetState.READY:
                acknowledged_at = timezone.now()
                DeviceCommand.objects.filter(
                    device=device,
                    command_type=DeviceCommand.Type.RESET_SESSION,
                    status=DeviceCommand.Status.PENDING,
                ).update(
                    status=DeviceCommand.Status.ACKNOWLEDGED,
                    acknowledged_at=acknowledged_at,
                )
                device.reset_state = BasketDevice.ResetState.READY
                device.save(update_fields=("reset_state", "updated_at"))
            if session is None:
                session = BasketSession.objects.create(device=device, customer=card.customer)
            if session.customer_id and session.customer_id != card.customer_id:
                return _message_response(
                    code="SESSION_ALREADY_ACTIVE",
                    message="The device already serves another customer.",
                    http_status=status.HTTP_409_CONFLICT,
                )
            if not session.customer_id and BasketLine.objects.filter(session=session).exists():
                return _message_response(
                    code="SESSION_ALREADY_ACTIVE",
                    message="The device already contains a basket awaiting identification.",
                    http_status=status.HTTP_409_CONFLICT,
                )
            if not session.customer_id:
                session.customer = card.customer
                session.save(update_fields=("customer", "updated_at"))

        return Response(
            {
                "status": _basket_status(session),
                "customer": _customer_payload(card.customer),
            }
        )


class BasketIoTView(IoTAPIView):
    def session_or_response(self, request):
        session = (
            BasketSession.objects.select_related("device", "customer")
            .filter(
                device=request.auth,
                status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING),
            )
            .first()
        )
        if session is None:
            return None, _message_response(
                code="NO_ACTIVE_INVOICE",
                message="No active invoice exists for this device.",
                http_status=status.HTTP_409_CONFLICT,
            )
        return session, None


class SendDetectionView(BasketIoTView):
    def post(self, request, device_code):
        event_id = _request_key(request)
        if event_id is None:
            return _message_response(
                code="INVALID_IDEMPOTENCY_KEY",
                message="Idempotency-Key must be a UUID.",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        label = request.data.get("label")
        confidence = request.data.get("confidence")
        if not isinstance(label, str) or not label.strip() or confidence is None:
            return _message_response(
                code="INVALID_DETECTION",
                message="label and confidence are required.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            confidence = Decimal(str(confidence))
        except Exception:
            confidence = Decimal("-1")
        if confidence < 0 or confidence > 1:
            return _message_response(
                code="INVALID_DETECTION",
                message="confidence must be between 0 and 1.",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        session, error = self.session_or_response(request)
        if error:
            return error
        if not session.customer_id:
            return _message_response(
                code="SESSION_NOT_IDENTIFIED",
                message="A customer card must start the session first.",
                http_status=status.HTTP_409_CONFLICT,
            )

        event, duplicate = ingest_detection(
            request.auth,
            {
                "event_id": event_id,
                "session_id": session.id,
                "boot_id": "iot-compat",
                "sequence": 0,
                "captured_at": timezone.now(),
                "action": DetectionEvent.Action.ITEM_ADDED,
                "detected_label": label,
                "confidence": confidence,
                "quantity": 1,
                "model_version": "",
            },
        )
        if event.result in (
            DetectionEvent.Result.APPLIED,
            DetectionEvent.Result.UNCATALOGUED_OBJECT,
        ):
            detection_payload = detection_result_payload(event, duplicate)
            return Response(
                {
                    "status": (
                        "PRODUCT_ADDED"
                        if event.result == DetectionEvent.Result.APPLIED
                        else "UNCATALOGUED_OBJECT_ADDED"
                    ),
                    "label": event.detected_label,
                    "accepted": True,
                    "duplicate": duplicate,
                    "display_label": detection_payload["display_label"],
                    "catalogued": detection_payload["catalogued"],
                },
                status=status.HTTP_200_OK if duplicate else status.HTTP_201_CREATED,
            )
        if event.result == DetectionEvent.Result.UNKNOWN_LABEL:
            return _message_response(
                code="UNKNOWN_PRODUCT",
                message="No product matches this YOLO label.",
                http_status=status.HTTP_404_NOT_FOUND,
            )
        return _message_response(
            code="CHECKOUT_REQUIRED",
            message="The basket no longer accepts detections.",
            http_status=status.HTTP_409_CONFLICT,
        )


class BasketStatusView(BasketIoTView):
    def get(self, request, device_code):
        command = (
            DeviceCommand.objects.filter(
                device=request.auth,
                command_type=DeviceCommand.Type.RESET_SESSION,
                status=DeviceCommand.Status.PENDING,
            )
            .order_by("created_at")
            .first()
        )
        if command is not None:
            sale = Sale.objects.filter(session_id=command.session_id).first()
            return Response(
                {
                    "status": "PAID",
                    "payment_status": "PAID",
                    "sale_number": sale.sale_number if sale is not None else None,
                    "reset_command_id": str(command.id),
                }
            )

        session = active_session_for_device(request.auth)
        if session is None:
            return Response({"status": "IDLE"})
        return Response({"status": _basket_status(session)})


class RfidPaymentView(BasketIoTView):
    @transaction.atomic
    def post(self, request, device_code):
        key = _request_key(request)
        if key is None:
            return _message_response(
                code="INVALID_IDEMPOTENCY_KEY",
                message="Idempotency-Key must be a UUID.",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        previous_sale = Sale.objects.filter(idempotency_key=key).first()
        if previous_sale is not None:
            if previous_sale.payment_device_id != request.auth.id:
                return _message_response(
                    code="IDEMPOTENCY_KEY_CONFLICT",
                    message="This payment key belongs to another device.",
                    http_status=status.HTTP_409_CONFLICT,
                )
            command = DeviceCommand.objects.filter(
                device=request.auth,
                command_type=DeviceCommand.Type.RESET_SESSION,
                session_id=previous_sale.session_id,
            ).first()
            return Response(
                {
                    "status": "PAID",
                    "payment_status": "PAID",
                    "sale_number": previous_sale.sale_number,
                    "reset_command_id": str(command.id) if command is not None else None,
                    "duplicate": True,
                }
            )
        raw_uid = request.data.get("rfid_uid")
        if not isinstance(raw_uid, str) or not raw_uid.strip():
            return _message_response(
                code="INVALID_RFID",
                message="rfid_uid is required.",
                http_status=status.HTTP_400_BAD_REQUEST,
            )
        uid = normalize_rfid_uid(raw_uid)
        session, error = self.session_or_response(request)
        if error:
            return error
        session = BasketSession.objects.select_for_update().select_related("customer").get(pk=session.pk)
        existing = Sale.objects.filter(session=session).first()
        if existing is not None:
            if existing.payment_method == "RFID" and existing.payment_status == Sale.PaymentStatus.PAID:
                command = (
                    DeviceCommand.objects.filter(
                        device=request.auth,
                        command_type=DeviceCommand.Type.RESET_SESSION,
                        session_id=session.id,
                    )
                    .order_by("created_at")
                    .first()
                )
                return Response(
                    {
                        "status": "PAID",
                        "payment_status": "PAID",
                        "sale_number": existing.sale_number,
                        "reset_command_id": str(command.id) if command is not None else None,
                        "duplicate": True,
                    }
                )
            return _message_response(
                code="PAYMENT_DECLINED",
                message="This basket was already settled by another payment method.",
                http_status=status.HTTP_409_CONFLICT,
            )
        if session.status not in (
            BasketSession.Status.OPEN,
            BasketSession.Status.CHECKOUT_PENDING,
        ):
            return _message_response(
                code="CHECKOUT_REQUIRED",
                message="The basket is no longer available for payment.",
                http_status=status.HTTP_409_CONFLICT,
            )
        card = (
            RfidCard.objects.select_related("customer", "customer__wallet")
            .filter(uid=uid, is_active=True, customer__is_active=True)
            .first()
        )
        if card is None:
            return _message_response(
                code="UNKNOWN_RFID",
                message="RFID card is not linked to an active customer.",
                http_status=status.HTTP_404_NOT_FOUND,
            )
        if session.customer_id != card.customer_id:
            return _message_response(
                code="RFID_MISMATCH",
                message="Payment RFID does not match the active customer.",
                http_status=status.HTTP_403_FORBIDDEN,
            )
        wallet = Wallet.objects.select_for_update().filter(customer=card.customer, is_active=True).first()
        if wallet is None:
            return _message_response(
                code="PAYMENT_DECLINED",
                message="The customer wallet is unavailable.",
                http_status=status.HTTP_409_CONFLICT,
            )
        total = sum((line.subtotal for line in session.lines.all()), Decimal("0"))
        if total <= 0:
            return _message_response(
                code="PAYMENT_DECLINED",
                message="The basket is empty.",
                http_status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        if session.status == BasketSession.Status.OPEN:
            now = timezone.now()
            changed = BasketSession.objects.filter(
                pk=session.pk,
                status=BasketSession.Status.OPEN,
                version=session.version,
            ).update(
                status=BasketSession.Status.CHECKOUT_PENDING,
                version=F("version") + 1,
                checkout_started_at=now,
                updated_at=now,
            )
            if changed != 1:
                return _message_response(
                    code="CHECKOUT_REQUIRED",
                    message="The basket changed before RFID payment could be confirmed.",
                    http_status=status.HTTP_409_CONFLICT,
                )
            session.status = BasketSession.Status.CHECKOUT_PENDING
            session.version += 1

        payment_request, sufficient = prepare_rfid_payment_request(
            session=session,
            device=request.auth,
            card=card,
            wallet=wallet,
            idempotency_key=key,
            amount=total,
        )
        if not sufficient:
            return _message_response(
                code="INSUFFICIENT_FUNDS",
                message="Wallet balance is insufficient.",
                http_status=status.HTTP_402_PAYMENT_REQUIRED,
                payment_request_id=str(payment_request.id),
                amount=str(total),
                balance=str(wallet.balance),
            )
        return Response(
            {
                "status": "PAYMENT_CONFIRMATION_PENDING",
                "payment_status": "PENDING",
                "payment_request_id": str(payment_request.id),
                "amount": str(total),
                "balance": str(wallet.balance),
            },
            status=status.HTTP_202_ACCEPTED,
        )
