import secrets

from django.core.management.base import BaseCommand, CommandError

from apps.devices.models import BasketDevice


class Command(BaseCommand):
    help = "Crée ou renouvelle les identifiants d'une Raspberry de panier."

    def add_arguments(self, parser):
        parser.add_argument("device_code")
        parser.add_argument("matrix_id", type=int)
        parser.add_argument("--rotate", action="store_true")

    def handle(self, *args, **options):
        device = BasketDevice.objects.filter(device_code=options["device_code"]).first()
        if device and not options["rotate"]:
            raise CommandError("L'équipement existe déjà. Utilisez --rotate pour renouveler son secret.")
        if device is None:
            device = BasketDevice(device_code=options["device_code"], matrix_id=options["matrix_id"])
        else:
            device.matrix_id = options["matrix_id"]
            device.enabled = True

        secret = secrets.token_urlsafe(32)
        device.set_secret(secret)
        device.full_clean()
        device.save()
        self.stdout.write(f"device_code={device.device_code}")
        self.stdout.write(f"matrix_id={device.matrix_id}")
        self.stdout.write(f"secret={secret}")
        self.stdout.write(self.style.WARNING("Ce secret ne sera plus affiché."))
