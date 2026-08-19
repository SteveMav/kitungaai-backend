from django.apps import AppConfig


class CheckoutConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.checkout"
    verbose_name = "Passage en caisse"

    def ready(self):
        from . import signals  # noqa: F401
