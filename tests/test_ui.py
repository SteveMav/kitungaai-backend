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
from apps.wallets.models import Customer, RfidCard, RfidEnrollmentRequest, Wallet, WalletTransaction


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
        self.device = BasketDevice.objects.create(device_code="UI-PI-01", matrix_id=201)
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
            reverse("ui:invoices"),
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
        response = self.client.post(
            reverse("ui:rfid-card-register"),
            data={"uid": "AABBCCDD", "customer": "1"},
        )
        self.assertEqual(response.status_code, 403)
        response = self.client.post(
            reverse("ui:rfid-card-top-up", args=[1]),
            data={"amount": "5000", "reason": "Test"},
        )
        self.assertEqual(response.status_code, 403)

    def test_administrator_can_manage_registered_rfid_cards(self):
        first_customer = Customer.objects.create(
            customer_code="CUST-RFID-01",
            display_name="Premier client",
        )
        second_customer = Customer.objects.create(
            customer_code="CUST-RFID-02",
            display_name="Deuxième client",
        )
        enrollment = RfidEnrollmentRequest.objects.create(
            uid="AA BB CC DD",
            device=self.device,
        )
        self.client.force_login(self.user)

        added = self.client.post(
            reverse("ui:rfid-card-register"),
            data={"uid": "aa bb cc dd", "customer": first_customer.id},
        )
        self.assertRedirects(added, reverse("ui:rfid-enrollments"))
        card = RfidCard.objects.get(uid="AABBCCDD")
        enrollment.refresh_from_db()
        self.assertEqual(card.customer, first_customer)
        self.assertEqual(enrollment.status, RfidEnrollmentRequest.Status.APPROVED)

        topped_up = self.client.post(
            reverse("ui:rfid-card-top-up", args=[card.id]),
            data={"amount": "5000", "reason": "Dépôt test"},
        )
        self.assertRedirects(topped_up, reverse("ui:rfid-enrollments"))
        wallet = Wallet.objects.get(customer=first_customer)
        self.assertEqual(wallet.balance, 5000)
        self.assertTrue(
            WalletTransaction.objects.filter(
                wallet=wallet,
                kind=WalletTransaction.Kind.TOP_UP,
                amount=5000,
                created_by=self.user,
            ).exists()
        )

        page = self.client.get(reverse("ui:rfid-enrollments"))
        self.assertContains(page, "AABBCCDD")
        self.assertContains(page, "Premier client")
        self.assertContains(page, "Désactiver")

        reassigned = self.client.post(
            reverse("ui:rfid-card-reassign", args=[card.id]),
            data={"customer": second_customer.id},
        )
        self.assertRedirects(reassigned, reverse("ui:rfid-enrollments"))
        card.refresh_from_db()
        enrollment.refresh_from_db()
        self.assertEqual(card.customer, second_customer)
        self.assertEqual(enrollment.customer, second_customer)

        disabled = self.client.post(reverse("ui:rfid-card-toggle", args=[card.id]))
        self.assertRedirects(disabled, reverse("ui:rfid-enrollments"))
        card.refresh_from_db()
        self.assertFalse(card.is_active)
        self.assertIsNotNone(card.disabled_at)

        reactivated = self.client.post(reverse("ui:rfid-card-toggle", args=[card.id]))
        self.assertRedirects(reactivated, reverse("ui:rfid-enrollments"))
        card.refresh_from_db()
        self.assertTrue(card.is_active)
        self.assertIsNone(card.disabled_at)

        removed = self.client.post(reverse("ui:rfid-card-remove", args=[card.id]))
        self.assertRedirects(removed, reverse("ui:rfid-enrollments"))
        self.assertFalse(RfidCard.objects.filter(pk=card.id).exists())
        self.assertFalse(RfidEnrollmentRequest.objects.filter(uid="AABBCCDD").exists())

        self.client.logout()
        rescanned = self.client.post(
            reverse("iot-session-start", args=[self.device.device_code]),
            data={"rfid_uid": "AA BB CC DD"},
            content_type="application/json",
        )
        self.assertEqual(rescanned.status_code, 202)
        self.assertEqual(rescanned.json()["status"], "RFID_ENROLLMENT_PENDING")
        self.assertTrue(
            RfidEnrollmentRequest.objects.filter(
                uid="AABBCCDD",
                status=RfidEnrollmentRequest.Status.PENDING,
            ).exists()
        )

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
            },
        )
        self.assertRedirects(response, reverse("ui:checkout"))
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 8)
        self.assertEqual(Sale.objects.count(), 1)
        sale = Sale.objects.get()
        history = self.client.get(reverse("ui:invoice-detail", args=[sale.id]))
        self.assertContains(history, sale.sale_number)
        self.assertContains(history, "Arduino Mega")
        self.assertContains(history, "30000 FC")

    def test_backend_can_prepare_an_active_basket_for_manual_checkout(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse("ui:begin-manual-checkout", args=[self.session.id]),
            data={"expected_version": self.session.version},
        )

        self.assertRedirects(response, reverse("ui:checkout-detail", args=[self.session.id]))
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, BasketSession.Status.CHECKOUT_PENDING)
        self.assertIsNone(self.session.selected_terminal)
        checkout_page = self.client.get(reverse("ui:checkout-detail", args=[self.session.id]))
        self.assertContains(checkout_page, "Confirmer la vente")
