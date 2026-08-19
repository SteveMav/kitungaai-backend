from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver


@receiver(post_migrate)
def grant_wallet_permissions_to_administrators(sender, **kwargs):
    if sender.label != "wallets":
        return
    administrator, _ = Group.objects.get_or_create(name="Administrateur")
    permissions = Permission.objects.filter(content_type__app_label="wallets")
    administrator.permissions.add(*permissions)
