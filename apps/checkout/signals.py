from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate
from django.dispatch import receiver


ROLE_PERMISSIONS = {
    "Caissier": {
        "correct_basket",
        "release_basket",
        "complete_sale",
        "view_basketsession",
        "view_basketline",
        "view_sale",
    },
    "Superviseur": {
        "correct_basket",
        "release_basket",
        "cancel_basket",
        "complete_sale",
        "view_basketsession",
        "view_basketline",
        "view_sale",
    },
}


@receiver(post_migrate)
def create_kitunga_roles(sender, **kwargs):
    if sender.label != "checkout":
        return

    relevant = Permission.objects.filter(content_type__app_label__in=("api", "catalog", "devices", "baskets", "checkout"))
    administrator, _ = Group.objects.get_or_create(name="Administrateur")
    administrator.permissions.set(relevant)

    for role_name, codenames in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role_name)
        group.permissions.set(relevant.filter(codename__in=codenames))
