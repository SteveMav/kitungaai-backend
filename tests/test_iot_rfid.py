import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api.models import Product
from apps.baskets.models import BasketLine, BasketSession
from apps.catalog.models import VisionLabel
from apps.checkout.models import Sale
from apps.devices.models import BasketDevice, CheckoutTerminal
from apps.wallets.models import (
    Customer,
    RfidCard,
    RfidEnrollmentRequest,
    Wallet,
    WalletTransaction,
)
from apps.wallets.services import credit_wallet


class IotRfidContractTests(TestCase):
    device_secret = "device-secret-for-iot-rfid-tests"
    terminal_secret = "terminal-secret-for-iot-rfid-tests"
    card_uid = "04A732B19C"

    def setUp(self):
        self.device = BasketDevice(device_code="KITUNGA-PI-001", matrix_id=101)
        self.device.set_secret(self.device_secret)
        self.device.save()
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
        headers = {
            "HTTP_AUTHORIZATION": f"Device {self.device_secret}",
            "HTTP_X_DEVICE_CODE": self.device.device_code,
        }
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
            reverse("iot-session-start"),
            data={"device_id": self.device.device_code, "rfid_uid": self.card_uid},
            content_type="application/json",
            **self.device_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json()["basket_id"]

    def add_detection(self, basket_id, key=None):
        key = key or uuid.uuid4()
        return self.client.post(
            reverse("iot-detection", args=[basket_id]),
            data={"device_id": self.device.device_code, "label": "ESP32", "confidence": "0.95"},
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
            reverse("iot-rfid-payment", args=[basket_id]),
            data={"device_id": self.device.device_code, "rfid_uid": uid or self.card_uid},
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
            reverse("iot-session-start"),
            data={"device_id": self.device.device_code, "rfid_uid": "DEADBEEF"},
            content_type="application/json",
            **self.device_headers(),
        )
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.json()["status"], "RFID_ENROLLMENT_PENDING")
        self.assertFalse(BasketSession.objects.exists())
        enrollment = RfidEnrollmentRequest.objects.get(uid="DEADBEEF")
        self.assertEqual(enrollment.status, RfidEnrollmentRequest.Status.PENDING)
        self.assertEqual(enrollment.device, self.device)

    def test_unknown_rfid_can_be_accepted_by_an_administrator_then_start_a_session(self):
        unknown_uid = "DEADBEEF"
        response = self.client.post(
            reverse("iot-session-start"),
            data={"device_id": self.device.device_code, "rfid_uid": unknown_uid},
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
            reverse("iot-session-start"),
            data={"device_id": self.device.device_code, "rfid_uid": unknown_uid},
            content_type="application/json",
            **self.device_headers(),
        )
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.json()["status"], "ACTIVE")

    def test_iot_authentication_error_has_actionable_json_status(self):
        response = self.client.post(
            reverse("iot-session-start"),
            data={"device_id": self.device.device_code, "rfid_uid": self.card_uid},
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

    def test_rfid_payment_debits_wallet_and_replay_is_safe(self):
        credit_wallet(wallet_id=self.wallet.id, amount="2000.00", user=None, reason="Test")
        basket_id, _session = self.prepare_checkout()
        key = uuid.uuid4()
        first = self.payment(basket_id, key=key)
        replay = self.payment(basket_id, key=key)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json()["status"], "PAID")
        reset_command_id = first.json()["reset_command_id"]
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["duplicate"])
        self.wallet.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(self.wallet.balance, Decimal("500.00"))
        self.assertEqual(self.product.stock, 3)
        self.assertEqual(Sale.objects.count(), 1)
        payment = WalletTransaction.objects.get(kind=WalletTransaction.Kind.RFID_PAYMENT)
        self.assertEqual(payment.amount, Decimal("-1500.00"))
        self.assertIsNone(payment.created_by)

        acknowledgement = self.client.post(
            reverse("api_v1:device-command-ack", args=[self.device.device_code, reset_command_id]),
            data={},
            content_type="application/json",
            **self.device_headers(),
        )
        self.assertEqual(acknowledgement.status_code, 200)
        next_basket_id = self.start_session()
        self.assertNotEqual(next_basket_id, basket_id)

    def test_insufficient_funds_keeps_wallet_stock_and_basket_unchanged(self):
        basket_id, session = self.prepare_checkout()
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

    def test_payment_rejects_a_card_from_another_customer(self):
        other_customer = Customer.objects.create(customer_code="CUST-0043", display_name="Madame Y")
        Wallet.objects.create(customer=other_customer, balance="10000.00")
        RfidCard.objects.create(customer=other_customer, uid="DEADBEEF")
        basket_id, _session = self.prepare_checkout()
        response = self.payment(basket_id, uid="DEADBEEF")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["status"], "RFID_MISMATCH")
        self.assertFalse(Sale.objects.exists())
