from rest_framework.throttling import SimpleRateThrottle

from .models import BasketDevice, CheckoutTerminal


class DeviceRateThrottle(SimpleRateThrottle):
    scope = "device"

    def get_cache_key(self, request, view):
        if not isinstance(request.auth, BasketDevice):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.auth.pk}


class TerminalRateThrottle(SimpleRateThrottle):
    scope = "terminal"

    def get_cache_key(self, request, view):
        if not isinstance(request.auth, CheckoutTerminal):
            return None
        return self.cache_format % {"scope": self.scope, "ident": request.auth.pk}
