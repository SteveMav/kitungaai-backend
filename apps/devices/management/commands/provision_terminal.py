import secrets

from django.core.management.base import BaseCommand, CommandError

from apps.devices.models import CheckoutTerminal


class Command(BaseCommand):
    help = "Crée ou renouvelle les identifiants d'un scanner de caisse."

    def add_arguments(self, parser):
        parser.add_argument("terminal_code")
        parser.add_argument("--rotate", action="store_true")

    def handle(self, *args, **options):
        terminal = CheckoutTerminal.objects.filter(terminal_code=options["terminal_code"]).first()
        if terminal and not options["rotate"]:
            raise CommandError("Le terminal existe déjà. Utilisez --rotate pour renouveler son secret.")
        if terminal is None:
            terminal = CheckoutTerminal(terminal_code=options["terminal_code"])
        else:
            terminal.enabled = True

        secret = secrets.token_urlsafe(32)
        terminal.set_secret(secret)
        terminal.full_clean()
        terminal.save()
        self.stdout.write(f"terminal_code={terminal.terminal_code}")
        self.stdout.write(f"secret={secret}")
        self.stdout.write(self.style.WARNING("Ce secret ne sera plus affiché."))
