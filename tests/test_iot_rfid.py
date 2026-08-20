import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api.models import Product
from apps.baskets.models import BasketLine, BasketSession, UncataloguedBasketLine
from apps.catalog.models import VisionLabel
from apps.checkout.models import Sale
from apps.checkout.services import complete_sale, release_basket
from apps.devices.models import BasketDevice, CheckoutTerminal, DeviceCommand
from apps.wallets.models import (
    Customer,
    RfidCard,
    RfidEnrollmentRequest,
    RfidPaymentRequest,
    Wallet,
    WalletTransaction,
)
from apps.wallets.services import credit_wallet


class IotRfidContractTests(TestCase):
    terminal_secret = "terminal-secret-for-iot-rfid-tests"
    card_uid = "04A732B19C"

    def setUp(self):
        self.device = BasketDevice.objects.create(device_code="KITUNGA-PI-001", matrix_id=101)
        self.terminal = CheckoutTerminal(terminal_code="CAISSE-01")
        self.terminal.set_secret(self.terminal_secret)
        self.terminal.save()
        self.product = Product.objects.create(
            sku="ESP32", name="ESP32", price="1500.00", stock=4
        )
        VisionLabel.objects.create(label="esp32", product=self.product)
        self.customer = Customer.objects.create(customer_code="CUST-0042", display_name="Monsieur X")
        self.wallet = Wallet.objects.create(customer=self.customer)
        RfidCard.objects.create(customer=self.customer, uid=self.card_uid)

    def device_headers(self, key=None):
        headers = {}
        if key:
            headers["HTTP_IDEMPOTENCY_KEY"] = str(key)
        return headers

    def terminal_headers(self, key):
        return {
            "HTTP_AUTHORIZATION": f"Terminal {self.terminal.terminal_code}:{self.terminal_secret}",
            "HTTP_IDEMPOTENCY_KEY": str(key),
        }

    def start_session(self):
        response = self.client.post(
            reverse("iot-session-start", args=[self.device.device_code]),
            data={"rfid_uid": self.card_uid},
            content_type="application/json",
            **self.device_headers(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("basket_id", response.json())
        return BasketSession.objects.get(
            device=self.device,
            status__in=(BasketSession.Status.OPEN, BasketSession.Status.CHECKOUT_PENDING),
        ).id

    def add_detection(self, basket_id, key=None, label="ESP32"):
        key = key or uuid.uuid4()
        return self.client.post(
            reverse("iot-detection", args=[self.device.device_code]),
            data={"label": label, "confidence": "0.95"},
            content_type="application/json",
            **self.device_headers(key),
        )

    def checkout(self, session):
        key = uuid.uuid4()
        return self.client.post(
            reverse("api_v1:checkout-scans"),
            data={
                "event_id": str(key),
                "matrix_id": self.device.matrix_id,
                "frame_errors": 0,
                "copy_disagreements": 0,
                "cell_contrast": "0.75",
                "scanned_at": timezone.now().isoformat(),
            },
            content_type="application/json",
            **self.terminal_headers(key),
        )

    def payment(self, basket_id, uid=None, key=None):
        key = key or uuid.uuid4()
        return self.client.post(
            reverse("iot-rfid-payment", args=[self.device.device_code]),
            data={"rfid_uid": uid or self.card_uid},
            content_type="application/json",
            **self.device_headers(key),
        )

    def prepare_checkout(self):
        basket_id = self.start_session()
        self.assertEqual(self.add_detection(basket_id).status_code, 201)
        session = BasketSession.objects.get(pk=basket_id)
        self.assertEqual(self.checkout(session).status_code, 200)
        session.refresh_from_db()
        self.assertEqual(session.status, BasketSession.Status.CHECKOUT_PENDING)
        return basket_id, session

    def test_unknown_rfid_creates_a_pending_admin_request_without_a_basket(self):
        response = self.client.post(
            reverse("iot-session-start", args=[self.device.device_code]),
            data={"rfid_uid": "DEADBEEF"},
            content_type="application/json",
            **self.device_headers(),
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "RFID_ENROLLMENT_PENDING")
        self.assertFalse(BasketSession.objects.exists())
        enrollment = RfidEnrollmentRequest.objects.get(uid="DEADBEEF")
        self.assertEqual(enrollment.status, RfidEnrollmentRequest.Status.PENDING)
        self.assertEqual(enrollment.device, self.device)

    def test_unknown_rfid_still_notifies_admin_while_device_reset_is_pending(self):
        self.device.reset_state = BasketDevice.ResetState.PENDING
        self.device.save(update_fields=("reset_state", "updated_at"))

        with patch("apps.realtime.publish_rfid_enrollment_event") as publish_event:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("iot-session-start", args=[self.device.device_code]),
                    data={"rfid_uid": "AA11BB22"},
                    content_type="application/json",
                    **self.device_headers(),
                )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "RFID_ENROLLMENT_PENDING")
        self.assertTrue(RfidEnrollmentRequest.objects.filter(uid="AA11BB22").exists())
        self.assertFalse(BasketSession.objects.exists())
        publish_event.assert_called_once()
        self.assertEqual(publish_event.call_args.kwargs["event_type"], "rfid.enrollment.requested")

    def test_known_rfid_starts_a_new_session_and_acknowledges_an_orphan_reset(self):
        self.device.reset_state = BasketDevice.ResetState.PENDING
        self.device.save(update_fields=("reset_state", "updated_at"))
        command = DeviceCommand.objects.create(
            device=self.device,
            command_type=DeviceCommand.Type.RESET_SESSION,
            session_id=uuid.uuid4(),
        )

        basket_id = self.start_session()

        self.device.refresh_from_db()
        command.refresh_from_db()
        self.assertEqual(self.device.reset_state, BasketDevice.ResetState.READY)
        self.assertEqual(command.status, DeviceCommand.Status.ACKNOWLEDGED)
        self.assertIsNotNone(command.acknowledged_at)
        self.assertTrue(BasketSession.objects.filter(pk=basket_id, customer=self.customer).exists())

    def test_unknown_rfid_can_be_accepted_by_an_administrator_then_start_a_session(self):
        unknown_uid = "DEADBEEF"
        response = self.client.post(
            reverse("iot-session-start", args=[self.device.device_code]),
            data={"rfid_uid": unknown_uid},
            content_type="application/json",
            **self.device_headers(),
        )
        enrollment_id = response.json()["enrollment_id"]
        administrator = get_user_model().objects.create_superuser(
            username="rfid-admin",
            password="strong-test-password",
        )
        self.client.force_login(administrator)
        page = self.client.get(reverse("ui:rfid-enrollment-detail", args=[enrollment_id]))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, unknown_uid)

        approved = self.client.post(
            reverse("ui:rfid-enrollment-approve", args=[enrollment_id]),
            data={"customer_code": "CUST-9000", "display_name": "Nouvelle cliente"},
        )
        self.assertRedirects(approved, reverse("ui:rfid-enrollments"))
        enrollment = RfidEnrollmentRequest.objects.get(pk=enrollment_id)
        self.assertEqual(enrollment.status, RfidEnrollmentRequest.Status.APPROVED)
        self.assertEqual(enrollment.customer.customer_code, "CUST-9000")
        self.assertTrue(RfidCard.objects.filter(uid=unknown_uid, customer=enrollment.customer).exists())
        self.assertTrue(Wallet.objects.filter(customer=enrollment.customer).exists())

        self.client.logout()
        started = self.client.post(
            reverse("iot-session-start", args=[self.device.device_code]),
            data={"rfid_uid": unknown_uid},
            content_type="application/json",
            **self.device_headers(),
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["status"], "ACTIVE")

    def test_unknown_device_identifier_is_rejected(self):
        response = self.client.post(
            reverse("iot-session-start", args=["UNKNOWN-PI"]),
            data={"rfid_uid": self.card_uid},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "DEVICE_UNAUTHORIZED")

    def test_detection_replay_is_applied_once(self):
        basket_id = self.start_session()
        key = uuid.uuid4()
        first = self.add_detection(basket_id, key)
        replay = self.add_detection(basket_id, key)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["duplicate"])
        self.assertEqual(BasketLine.objects.get().quantity, 1)

    def test_iot_detection_keeps_an_uncatalogued_model_object_in_the_basket(self):
        basket_id = self.start_session()

        response = self.add_detection(basket_id, label="Buzzer")

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()["status"], "UNCATALOGUED_OBJECT_ADDED")
        self.assertFalse(response.json()["catalogued"])
        self.assertEqual(response.json()["display_label"], "Objet non répertorié : buzzer")
        self.assertEqual(UncataloguedBasketLine.objects.get().detected_label, "buzzer")

    def test_second_scan_requests_confirmation_then_approved_payment_debits_wallet(self):
        credit_wallet(wallet_id=self.wallet.id, amount="2000.00", user=None, reason="Test")
        basket_id = self.start_session()
        self.assertEqual(self.add_detection(basket_id).status_code, 201)
        session = BasketSession.objects.get(pk=basket_id)
        self.assertEqual(session.status, BasketSession.Status.OPEN)
        key = uuid.uuid4()
        with patch("apps.realtime.publish_rfid_payment_event") as publish_event:
            with self.captureOnCommitCallbacks(execute=True):
                first = self.payment(basket_id, key=key)
        replay = self.payment(basket_id, key=key)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(first.json()["status"], "PAYMENT_CONFIRMATION_PENDING")
        publish_event.assert_called_once()
        self.assertEqual(publish_event.call_args.args[0]["type"], "rfid.payment.requested")
        self.assertEqual(publish_event.call_args.args[0]["amount"], "1500.00")
        self.assertEqual(replay.status_code, 202)
        self.assertEqual(replay.json()["payment_request_id"], first.json()["payment_request_id"])
        self.wallet.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("2000.00"))
        self.assertEqual(self.product.stock, 4)
        self.assertFalse(Sale.objects.exists())

        administrator = get_user_model().objects.create_superuser(
            username="payment-admin",
            password="strong-test-password",
        )
        self.client.force_login(administrator)
        payment_request = RfidPaymentRequest.objects.get(pk=first.json()["payment_request_id"])
        confirmed = self.client.post(
            reverse("ui:rfid-payment-confirm", args=[payment_request.id])
        )

        sale = Sale.objects.get()
        self.assertRedirects(confirmed, reverse("ui:invoice-detail", args=[sale.id]))
        self.wallet.refresh_from_db()
        self.product.refresh_from_db()
        payment_request.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("500.00"))
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(payment_request.status, RfidPaymentRequest.Status.APPROVED)
        self.assertEqual(payment_request.sale, sale)
        payment = WalletTransaction.objects.get(kind=WalletTransaction.Kind.RFID_PAYMENT)
        self.assertEqual(payment.amount, Decimal("-1500.00"))
        self.assertEqual(payment.created_by, administrator)

        repeated = self.client.post(reverse("ui:rfid-payment-confirm", args=[payment_request.id]))
        self.assertRedirects(repeated, reverse("ui:invoice-detail", args=[sale.id]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("500.00"))
        self.assertEqual(WalletTransaction.objects.filter(kind=WalletTransaction.Kind.RFID_PAYMENT).count(), 1)

        reset_command_id = str(
            DeviceCommand.objects.get(
                device=self.device,
                session_id=basket_id,
                command_type=DeviceCommand.Type.RESET_SESSION,
            ).id
        )
        self.client.logout()

        acknowledgement = self.client.post(
            reverse("api_v1:device-command-ack", args=[self.device.device_code, reset_command_id]),
            data={},
            content_type="application/json",
            **self.device_headers(),
        )
        self.assertEqual(acknowledgement.status_code, 200)
        next_basket_id = self.start_session()
        self.assertNotEqual(next_basket_id, basket_id)

    def test_insufficient_funds_creates_no_sale_and_can_be_recharged_before_confirmation(self):
        basket_id = self.start_session()
        self.assertEqual(self.add_detection(basket_id).status_code, 201)
        session = BasketSession.objects.get(pk=basket_id)
        response = self.payment(basket_id)
        self.assertEqual(response.status_code, 402)
        self.assertEqual(response.json()["status"], "INSUFFICIENT_FUNDS")
        self.wallet.refresh_from_db()
        self.product.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("0.00"))
        self.assertEqual(self.product.stock, 4)
        self.assertEqual(session.status, BasketSession.Status.CHECKOUT_PENDING)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(WalletTransaction.objects.filter(kind=WalletTransaction.Kind.RFID_PAYMENT).exists())
        payment_request = RfidPaymentRequest.objects.get(session=session)
        self.assertEqual(payment_request.status, RfidPaymentRequest.Status.INSUFFICIENT_FUNDS)

        credit_wallet(wallet_id=self.wallet.id, amount="2000.00", user=None, reason="Recharge")
        payment_request.refresh_from_db()
        self.assertEqual(payment_request.status, RfidPaymentRequest.Status.PENDING)
        self.assertEqual(payment_request.balance_snapshot, Decimal("2000.00"))

        release_user = get_user_model().objects.create_superuser(
            username="release-admin",
            password="strong-test-password",
        )
        release_basket(
            session.id,
            release_user,
            {"expected_version": session.version, "reason": "Retour au panier"},
        )
        payment_request.refresh_from_db()
        self.assertEqual(payment_request.status, RfidPaymentRequest.Status.CANCELLED)

    def test_payment_rejects_a_card_from_another_customer(self):
        other_customer = Customer.objects.create(customer_code="CUST-0043", display_name="Madame Y")
        Wallet.objects.create(customer=other_customer, balance="10000.00")
        RfidCard.objects.create(customer=other_customer, uid="DEADBEEF")
        basket_id, _session = self.prepare_checkout()
        response = self.payment(basket_id, uid="DEADBEEF")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "RFID_MISMATCH")
        self.assertFalse(Sale.objects.exists())

    def test_paid_status_exposes_the_reset_command_after_manual_confirmation(self):
        basket_id = self.start_session()
        self.assertEqual(self.add_detection(basket_id).status_code, 201)
        session = BasketSession.objects.get(pk=basket_id)
        session.status = BasketSession.Status.CHECKOUT_PENDING
        session.save(update_fields=("status", "updated_at"))
        complete_sale(
            session.id,
            None,
            uuid.uuid4(),
            {
                "expected_version": session.version,
                "payment_method": "CASH",
                "payment_status": Sale.PaymentStatus.PAID,
            },
        )

        status_response = self.client.get(
            reverse("iot-basket-status", args=[self.device.device_code]),
            **self.device_headers(),
        )

        self.assertEqual(status_response.status_code, 200)
        self.assertEqual(status_response.json()["status"], "PAID")
        self.assertIn("reset_command_id", status_response.json())
