from django.core.management.base import BaseCommand

from apps.devices.models import BasketDevice


class Command(BaseCommand):
    help = "Crée ou met à jour une Raspberry identifiée par son device_id."

    def add_arguments(self, parser):
        parser.add_argument("device_code")
        parser.add_argument("matrix_id", type=int)

    def handle(self, *args, **options):
        device = BasketDevice.objects.filter(device_code=options["device_code"]).first()
        if device is None:
            device = BasketDevice(device_code=options["device_code"], matrix_id=options["matrix_id"])
        else:
            device.matrix_id = options["matrix_id"]
            device.enabled = True

        device.full_clean()
        device.save()
        self.stdout.write(f"device_code={device.device_code}")
        self.stdout.write(f"matrix_id={device.matrix_id}")
        self.stdout.write(self.style.SUCCESS("Raspberry enregistrée."))
