from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from apps.checkout.models import Sale

from .models import RfidPaymentRequest


def _cancel_payment_request(session_id, sale=None):
    from .payment_services import cancel_rfid_payment_request_for_session

    cancel_rfid_payment_request_for_session(session_id=session_id, sale=sale)


@receiver(post_migrate)
def grant_wallet_permissions_to_administrators(sender, **kwargs):
    if sender.label != "wallets":
        return
    administrator, _ = Group.objects.get_or_create(name="Administrateur")
    permissions = Permission.objects.filter(content_type__app_label="wallets")
    administrator.permissions.add(*permissions)


@receiver(post_save, sender=Sale)
def cancel_pending_rfid_request_after_another_payment(sender, instance, created, **kwargs):
    if not created or instance.payment_method == "RFID":
        return
    _cancel_payment_request(instance.session_id, sale=instance)
