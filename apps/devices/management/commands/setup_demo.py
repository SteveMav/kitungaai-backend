import secrets
import uuid
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from api.models import Product
from apps.baskets.models import BasketLine, BasketSession
from apps.catalog.models import VisionLabel
from apps.checkout.models import MatrixScanEvent
from apps.checkout.services import select_basket_from_scan
from apps.devices.models import BasketDevice, CheckoutTerminal
from apps.devices.services import process_heartbeat


class Command(BaseCommand):
    help = "Prépare un compte et un panier de démonstration local sans code-barres."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo", help="Identifiant du compte de démonstration.")
        parser.add_argument("--password", required=True, help="Mot de passe du compte de démonstration.")
        parser.add_argument(
            "--checkout",
            action="store_true",
            help="Place directement le panier de démonstration dans la file de caisse.",
        )

    def handle(self, *args, **options):
        password = options["password"]
        if len(password) < 8:
            raise CommandError("Le mot de passe de démonstration doit contenir au moins 8 caractères.")

        user_model = get_user_model()
        user, _created = user_model.objects.get_or_create(username=options["username"])
        user.is_staff = True
        user.is_superuser = True
        user_fields = ["is_staff", "is_superuser"]
        if not user.check_password(password):
            user.set_password(password)
            user_fields.append("password")
        user.save(update_fields=user_fields)

        if not Product.objects.exists():
            Product.objects.bulk_create(
                [
                    Product(sku="ARD-MEGA", name="Arduino Mega", price=Decimal("15000"), stock=100),
                    Product(sku="ESP32-CAM", name="ESP32 Cam", price=Decimal("10000"), stock=50),
                    Product(sku="CAP-US", name="Capteur ultrason", price=Decimal("5000"), stock=75),
                ]
            )

        products = list(Product.objects.filter(is_active=True).order_by("name")[:2])
        if not products:
            raise CommandError("Aucun produit actif n'est disponible pour le panier de démonstration.")

        device, device_created = BasketDevice.objects.get_or_create(
            device_code="DEMO-PI-01",
            defaults={"matrix_id": 101, "enabled": True},
        )
        device_secret = None
        if device_created:
            device_secret = secrets.token_urlsafe(28)
            device.set_secret(device_secret)
            device.save(update_fields=("credential_hash",))

        terminal, terminal_created = CheckoutTerminal.objects.get_or_create(
            terminal_code="DEMO-CAISSE-01",
            defaults={"enabled": True},
        )
        terminal_secret = None
        if terminal_created:
            terminal_secret = secrets.token_urlsafe(28)
            terminal.set_secret(terminal_secret)
            terminal.save(update_fields=("credential_hash",))

        device, session, _command = process_heartbeat(
            device,
            {"firmware_version": "demo", "boot_id": "DEMO-BOOT"},
        )
        if session is None:
            raise CommandError("Le panier attend une réinitialisation et ne peut pas ouvrir de session.")

        if not session.lines.exists():
            for index, product in enumerate(products, start=1):
                VisionLabel.objects.get_or_create(
                    label=f"demo_{product.sku.lower().replace('-', '_')}",
                    model_version="",
                    defaults={"product": product, "is_active": True},
                )
                BasketLine.objects.create(
                    session=session,
                    product=product,
                    quantity=index,
                    unit_price_snapshot=product.price,
                )
            session.version += 1
            session.save(update_fields=("version", "updated_at"))

        if options["checkout"] and session.status == BasketSession.Status.OPEN:
            select_basket_from_scan(
                terminal,
                {
                    "event_id": uuid.uuid4(),
                    "matrix_id": device.matrix_id,
                    "frame_errors": 0,
                    "copy_disagreements": 0,
                    "cell_contrast": Decimal("1.0"),
                    "scanned_at": timezone.now(),
                },
            )

        self.stdout.write(self.style.SUCCESS("Démonstration Kitunga prête."))
        self.stdout.write(f"Compte : {user.username}")
        self.stdout.write(f"Page : http://127.0.0.1:8000/")
        self.stdout.write(f"Panier : matrice {device.matrix_id}, session {session.id}")
        if device_secret:
            self.stdout.write(f"Secret Raspberry Pi (affiché une seule fois) : {device_secret}")
        if terminal_secret:
            self.stdout.write(f"Secret caisse (affiché une seule fois) : {terminal_secret}")
