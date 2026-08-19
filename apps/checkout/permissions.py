from rest_framework.permissions import BasePermission


ROLE_NAMES = {"Administrateur", "Caissier", "Superviseur"}


class CashierAccess(BasePermission):
    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (user.is_superuser or user.groups.filter(name__in=ROLE_NAMES).exists())
        )


class DjangoPermission(BasePermission):
    permission = None

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.has_perm(self.permission))


class CanCorrectBasket(DjangoPermission):
    permission = "baskets.correct_basket"


class CanReleaseBasket(DjangoPermission):
    permission = "baskets.release_basket"


class CanCancelBasket(DjangoPermission):
    permission = "baskets.cancel_basket"


class CanCompleteSale(DjangoPermission):
    permission = "checkout.complete_sale"
