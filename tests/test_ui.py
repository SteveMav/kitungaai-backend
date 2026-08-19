import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from api.models import Product
from apps.baskets.models import BasketLine, BasketSession, UncataloguedBasketLine
from apps.catalog.models import VisionLabel
from apps.checkout.models import Sale, StockMovement
from apps.devices.models import BasketDevice, CheckoutTerminal


class KitungaUiTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin-ui",
            password="strong-test-password",
        )
        self.product = Product.objects.create(
            sku="ARD-MEGA",
            name="Arduino Mega",
            price="15000.00",
            stock=10,
        )
        VisionLabel.objects.create(label="arduino_mega", product=self.product)
        self.device = BasketDevice(device_code="UI-PI-01", matrix_id=201)
        self.device.set_secret("device-ui-test-secret-123456789")
        self.device.save()
        self.terminal = CheckoutTerminal(terminal_code="UI-CAISSE-01")
        self.terminal.set_secret("terminal-ui-test-secret-123456")
        self.terminal.save()
        self.session = BasketSession.objects.create(device=self.device)
        self.line = BasketLine.objects.create(
            session=self.session,
            product=self.product,
            quantity=2,
            unit_price_snapshot=self.product.price,
        )

    def test_anonymous_user_is_redirected_to_login(self):
        response = self.client.get(reverse("ui:dashboard"))
        self.assertRedirects(response, f"{reverse('login')}?next=/")

    def test_static_stylesheet_is_discoverable(self):
        self.assertIsNotNone(finders.find("kitunga/app.css"))

    def test_main_pages_render_for_authenticated_staff(self):
        self.client.force_login(self.user)
        for url in (
            reverse("ui:dashboard"),
            reverse("ui:baskets"),
            reverse("ui:basket-detail", args=[self.session.id]),
            reverse("ui:checkout"),
            reverse("ui:inventory"),
            reverse("ui:product-edit", args=[self.product.id]),
            reverse("ui:rfid-enrollments"),
        ):
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_cashier_cannot_view_or_process_rfid_enrollment_requests(self):
        cashier = get_user_model().objects.create_user(
            username="cashier-no-rfid",
            password="strong-test-password",
        )
        cashier.groups.add(Group.objects.get(name="Caissier"))
        self.client.force_login(cashier)
        response = self.client.get(reverse("ui:rfid-enrollments"))
        self.assertEqual(response.status_code, 403)

    def test_product_form_has_no_barcode_and_audits_stock_change(self):
        self.client.force_login(self.user)
        page = self.client.get(reverse("ui:product-edit", args=[self.product.id]))
        self.assertNotContains(page, "Code-barres")
        response = self.client.post(
            reverse("ui:product-edit", args=[self.product.id]),
            data={
                "sku": "ARD-MEGA",
                "name": "Arduino Mega",
                "price": "16000.00",
                "stock": 14,
                "is_active": "on",
                "vision_labels": "arduino_mega, mega_2560",
                "adjustment_reason": "Réception fournisseur",
            },
        )
        self.assertRedirects(response, reverse("ui:inventory"))
        movement = StockMovement.objects.get(movement_type=StockMovement.Type.ADJUSTMENT)
        self.assertEqual(movement.quantity, 4)
        self.assertEqual(movement.reason, "Réception fournisseur")
        self.assertTrue(VisionLabel.objects.filter(label="mega_2560", product=self.product).exists())

    def test_live_basket_payload_contains_sku_but_no_barcode(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse("ui:basket-data", args=[self.session.id]))
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["lines"][0]["product"]["sku"], "ARD-MEGA")
        self.assertNotIn("barcode", payload["lines"][0]["product"])

    def test_live_basket_payload_includes_uncatalogued_objects_without_a_price(self):
        UncataloguedBasketLine.objects.create(
            session=self.session,
            detected_label="buzzer",
            quantity=1,
        )
        self.client.force_login(self.user)
        response = self.client.get(reverse("ui:basket-data", args=[self.session.id]))

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        unknown_line = next(line for line in payload["lines"] if not line["catalogued"])
        self.assertEqual(unknown_line["product"]["name"], "Objet non répertorié : buzzer")
        self.assertEqual(unknown_line["unit_price"], "0")
        self.assertEqual(payload["item_count"], 3)
        self.assertEqual(payload["uncatalogued_item_count"], 1)

    def test_cashier_can_remove_an_uncatalogued_object_before_confirming_sale(self):
        unknown_line = UncataloguedBasketLine.objects.create(
            session=self.session,
            detected_label="buzzer",
            quantity=1,
        )
        self.session.status = BasketSession.Status.CHECKOUT_PENDING
        self.session.selected_terminal = self.terminal
        self.session.save(update_fields=("status", "selected_terminal", "updated_at"))
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("ui:remove-uncatalogued-line", args=[self.session.id, unknown_line.id]),
            data={
                "expected_version": self.session.version,
                "reason": "Article vérifié hors catalogue",
            },
        )

        self.assertRedirects(response, reverse("ui:checkout-detail", args=[self.session.id]))
        self.assertFalse(UncataloguedBasketLine.objects.exists())

    def test_checkout_confirmation_decrements_stock(self):
        self.session.status = BasketSession.Status.CHECKOUT_PENDING
        self.session.selected_terminal = self.terminal
        self.session.save(update_fields=("status", "selected_terminal", "updated_at"))
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("ui:complete-checkout", args=[self.session.id]),
            data={
                "expected_version": self.session.version,
                "idempotency_key": str(uuid.uuid4()),
                "payment_method": "CASH",
                "payment_status": Sale.PaymentStatus.PAID,
            },
        )
        self.assertRedirects(response, reverse("ui:checkout"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(Sale.objects.count(), 1)
