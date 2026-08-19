import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from api.models import Product
from apps.baskets.models import BasketLine, BasketSession, DetectionEvent, UncataloguedBasketLine
from apps.catalog.models import VisionLabel
from apps.checkout.models import MatrixScanEvent, Sale, StockMovement
from apps.devices.models import BasketDevice, CheckoutTerminal, DeviceCommand


class KitungaApiMixin:
    device_secret = "device-secret-for-tests-123456789"
    terminal_secret = "terminal-secret-for-tests-123456"

    def setUp(self):
        super().setUp()
        self.device = BasketDevice(device_code="KITUNGA-PI-01", matrix_id=101)
        self.device.set_secret(self.device_secret)
        self.device.save()
        self.terminal = CheckoutTerminal(terminal_code="CAISSE-01")
        self.terminal.set_secret(self.terminal_secret)
        self.terminal.save()
        self.product = Product.objects.create(
            sku="ARD-MEGA-2560",
            name="Arduino Mega 2560",
            price="1500.00",
            stock=10,
        )
        VisionLabel.objects.create(label="arduino_mega_2560", product=self.product)

    def device_headers(self, event_id=None):
        headers = {"HTTP_AUTHORIZATION": f"Device {self.device_secret}"}
        if event_id:
            headers["HTTP_IDEMPOTENCY_KEY"] = str(event_id)
        return headers

    def terminal_headers(self, event_id=None):
        headers = {"HTTP_AUTHORIZATION": f"Terminal {self.terminal.terminal_code}:{self.terminal_secret}"}
        if event_id:
            headers["HTTP_IDEMPOTENCY_KEY"] = str(event_id)
        return headers

    def heartbeat(self):
        response = self.client.post(
            reverse("api_v1:device-heartbeat", args=[self.device.device_code]),
            data={"firmware_version": "1.0.0", "boot_id": "BOOT-1"},
            content_type="application/json",
            **self.device_headers(),
        )
        if response.status_code == 200 and response.json().get("session"):
            self.active_session_id = response.json()["session"]["id"]
        return response

    def send_detection(self, event_id=None, **overrides):
        event_id = event_id or uuid.uuid4()
        payload = {
            "event_id": str(event_id),
            "session_id": getattr(self, "active_session_id", None),
            "boot_id": "BOOT-1",
            "sequence": 1,
            "captured_at": timezone.now().isoformat(),
            "action": "ITEM_ADDED",
            "detected_label": "arduino_mega_2560",
            "confidence": "0.9600",
            "quantity": 2,
            "model_version": "",
            **overrides,
        }
        return self.client.post(
            reverse("api_v1:device-events", args=[self.device.device_code]),
            data=payload,
            content_type="application/json",
            **self.device_headers(event_id),
        )

    def scan(self, event_id=None, **overrides):
        event_id = event_id or uuid.uuid4()
        payload = {
            "event_id": str(event_id),
            "matrix_id": self.device.matrix_id,
            "frame_errors": 0,
            "copy_disagreements": 0,
            "cell_contrast": "0.7500",
            "scanned_at": timezone.now().isoformat(),
            **overrides,
        }
        return self.client.post(
            reverse("api_v1:checkout-scans"),
            data=payload,
            content_type="application/json",
            **self.terminal_headers(event_id),
        )

    def cashier(self, role="Caissier", username="cashier"):
        user = get_user_model().objects.create_user(username=username, password="strong-test-password")
        user.groups.add(Group.objects.get(name=role))
        return user

    def prepare_checkout(self, quantity=2):
        self.assertEqual(self.heartbeat().status_code, 200)
        self.assertEqual(self.send_detection(quantity=quantity).status_code, 201)
        self.assertEqual(self.scan().status_code, 200)
        return BasketSession.objects.get(device=self.device)


class DeviceEventApiTests(KitungaApiMixin, TestCase):
    def test_disabled_or_unknown_device_is_rejected_without_mutation(self):
        self.device.enabled = False
        self.device.save(update_fields=("enabled",))
        response = self.heartbeat()
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["error"], "unauthorized_device")
        self.assertFalse(BasketSession.objects.exists())

    def test_heartbeat_creates_one_open_session(self):
        first = self.heartbeat()
        second = self.heartbeat()
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["session"]["id"], second.json()["session"]["id"])
        self.assertEqual(BasketSession.objects.count(), 1)

    def test_detection_replay_does_not_duplicate_quantity(self):
        self.heartbeat()
        event_id = uuid.uuid4()
        first = self.send_detection(event_id)
        replay = self.send_detection(event_id)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["duplicate"])
        self.assertEqual(DetectionEvent.objects.count(), 1)
        self.assertEqual(BasketLine.objects.get().quantity, 2)
        self.assertEqual(BasketSession.objects.get().version, 2)

    def test_line_keeps_price_snapshot_after_catalog_change(self):
        self.heartbeat()
        self.send_detection(quantity=1)
        self.product.price = "1900.00"
        self.product.save(update_fields=("price", "updated_at"))
        self.assertEqual(str(BasketLine.objects.get().unit_price_snapshot), "1500.00")

    def test_yolo_label_uses_the_french_catalogue_product_name(self):
        VisionLabel.objects.create(label="arduino-mega", product=self.product)
        self.heartbeat()
        response = self.send_detection(detected_label="Arduino-Mega")

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["catalogued"])
        self.assertEqual(response.json()["display_label"], "Arduino Mega 2560")
        self.assertEqual(BasketLine.objects.get().product, self.product)

    def test_unknown_label_is_added_as_an_uncatalogued_basket_line(self):
        self.heartbeat()
        response = self.send_detection(detected_label="label_inconnu")
        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.json()["accepted"])
        self.assertFalse(response.json()["catalogued"])
        self.assertEqual(response.json()["display_label"], "Objet non répertorié : label_inconnu")
        self.assertEqual(DetectionEvent.objects.get().result, DetectionEvent.Result.UNCATALOGUED_OBJECT)
        self.assertFalse(BasketLine.objects.exists())
        self.assertEqual(UncataloguedBasketLine.objects.get().detected_label, "label_inconnu")

    def test_late_event_is_audited_when_checkout_locked(self):
        self.heartbeat()
        self.send_detection(quantity=1)
        self.scan()
        late = self.send_detection(sequence=2)
        self.assertEqual(late.status_code, 409)
        self.assertEqual(late.json()["error"], "basket_locked")
        self.assertEqual(DetectionEvent.objects.order_by("id").last().result, DetectionEvent.Result.BASKET_LOCKED)
        self.assertEqual(BasketLine.objects.get().quantity, 1)


class CheckoutApiTests(KitungaApiMixin, TestCase):
    def test_scan_replay_selects_and_versions_once(self):
        self.heartbeat()
        event_id = uuid.uuid4()
        first = self.scan(event_id)
        replay = self.scan(event_id)
        session = BasketSession.objects.get(device=self.device)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["duplicate"])
        self.assertEqual(MatrixScanEvent.objects.count(), 1)
        self.assertEqual(session.status, BasketSession.Status.CHECKOUT_PENDING)
        self.assertEqual(session.version, 2)

    def test_bad_scan_quality_never_selects_basket(self):
        self.heartbeat()
        response = self.scan(frame_errors=1)
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "quality_rejected")
        self.assertEqual(BasketSession.objects.get().status, BasketSession.Status.OPEN)

    def test_cashier_endpoint_rejects_user_without_role(self):
        session = self.prepare_checkout(quantity=1)
        user = get_user_model().objects.create_user(username="visitor", password="strong-test-password")
        self.client.force_login(user)
        response = self.client.get(reverse("api_v1:cashier-session", args=[session.id]))
        self.assertEqual(response.status_code, 403)

    def test_sale_replay_decrements_stock_once_and_creates_reset(self):
        session = self.prepare_checkout(quantity=2)
        self.client.force_login(self.cashier())
        key = uuid.uuid4()
        url = reverse("api_v1:cashier-complete", args=[session.id])
        payload = {
            "expected_version": session.version,
            "payment_method": "CASH",
            "payment_status": "PAID",
        }
        first = self.client.post(
            url,
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key),
        )
        replay = self.client.post(
            url,
            data=payload,
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(key),
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(replay.status_code, 200)
        self.assertTrue(replay.json()["duplicate"])
        self.product.refresh_from_db()
        session.refresh_from_db()
        self.device.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(session.status, BasketSession.Status.COMPLETED)
        self.assertEqual(self.device.reset_state, BasketDevice.ResetState.PENDING)
        self.assertEqual(Sale.objects.count(), 1)
        self.assertEqual(StockMovement.objects.get().quantity, -2)
        self.assertEqual(DeviceCommand.objects.count(), 1)

    def test_insufficient_stock_rolls_back_entire_sale(self):
        session = self.prepare_checkout(quantity=11)
        self.client.force_login(self.cashier())
        response = self.client.post(
            reverse("api_v1:cashier-complete", args=[session.id]),
            data={
                "expected_version": session.version,
                "payment_method": "CASH",
                "payment_status": "PAID",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "insufficient_stock")
        self.product.refresh_from_db()
        session.refresh_from_db()
        self.assertEqual(self.product.stock, 10)
        self.assertEqual(session.status, BasketSession.Status.CHECKOUT_PENDING)
        self.assertFalse(Sale.objects.exists())
        self.assertFalse(StockMovement.objects.exists())

    def test_sale_is_blocked_while_an_uncatalogued_object_is_pending(self):
        self.heartbeat()
        self.assertEqual(self.send_detection(quantity=1).status_code, 201)
        self.assertEqual(self.send_detection(sequence=2, detected_label="buzzer", quantity=1).status_code, 201)
        session = BasketSession.objects.get(device=self.device)
        self.assertEqual(self.scan().status_code, 200)
        session.refresh_from_db()
        self.client.force_login(self.cashier())

        response = self.client.post(
            reverse("api_v1:cashier-complete", args=[session.id]),
            data={
                "expected_version": session.version,
                "payment_method": "CASH",
                "payment_status": "PAID",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["error"], "uncatalogued_objects_pending")
        self.assertFalse(Sale.objects.exists())

    def test_version_conflict_does_not_correct_line(self):
        session = self.prepare_checkout(quantity=2)
        line = BasketLine.objects.get(session=session)
        self.client.force_login(self.cashier())
        response = self.client.patch(
            reverse("api_v1:cashier-correct-line", args=[session.id, line.id]),
            data={"expected_version": session.version - 1, "quantity": 1, "reason": "Test conflit"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"], "version_conflict")
        line.refresh_from_db()
        self.assertEqual(line.quantity, 2)

    def test_reset_ack_is_repeatable_and_next_heartbeat_opens_new_cycle(self):
        session = self.prepare_checkout(quantity=1)
        self.client.force_login(self.cashier())
        self.client.post(
            reverse("api_v1:cashier-complete", args=[session.id]),
            data={
                "expected_version": session.version,
                "payment_method": "CASH",
                "payment_status": "PAID",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.client.logout()
        heartbeat = self.heartbeat()
        command_id = heartbeat.json()["command"]["id"]
        ack_url = reverse("api_v1:device-command-ack", args=[self.device.device_code, command_id])
        first_ack = self.client.post(ack_url, data={}, content_type="application/json", **self.device_headers())
        replay_ack = self.client.post(ack_url, data={}, content_type="application/json", **self.device_headers())
        new_heartbeat = self.heartbeat()

        self.assertEqual(first_ack.status_code, 200)
        self.assertFalse(first_ack.json()["duplicate"])
        self.assertTrue(replay_ack.json()["duplicate"])
        self.assertNotEqual(new_heartbeat.json()["session"]["id"], str(session.id))
        self.assertEqual(new_heartbeat.json()["session"]["status"], BasketSession.Status.OPEN)

    def test_event_from_completed_cycle_cannot_modify_new_session(self):
        old_session = self.prepare_checkout(quantity=1)
        self.client.force_login(self.cashier())
        self.client.post(
            reverse("api_v1:cashier-complete", args=[old_session.id]),
            data={
                "expected_version": old_session.version,
                "payment_method": "CASH",
                "payment_status": "PAID",
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        self.client.logout()
        command_id = self.heartbeat().json()["command"]["id"]
        self.client.post(
            reverse("api_v1:device-command-ack", args=[self.device.device_code, command_id]),
            data={},
            content_type="application/json",
            **self.device_headers(),
        )
        new_session_id = self.heartbeat().json()["session"]["id"]

        late_event = self.send_detection(session_id=str(old_session.id), sequence=99, quantity=1)

        self.assertEqual(late_event.status_code, 409)
        self.assertEqual(late_event.json()["error"], "basket_locked")
        self.assertFalse(BasketLine.objects.filter(session_id=new_session_id).exists())
        self.assertEqual(DetectionEvent.objects.order_by("id").last().session_id, old_session.id)
