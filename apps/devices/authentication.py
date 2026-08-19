from dataclasses import dataclass

from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed

from .models import BasketDevice, CheckoutTerminal


class UnauthorizedDevice(AuthenticationFailed):
    default_code = "unauthorized_device"


class UnauthorizedTerminal(AuthenticationFailed):
    default_code = "unauthorized_terminal"


@dataclass(frozen=True)
class HardwarePrincipal:
    code: str
    kind: str

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False


def _authorization_parts(request):
    raw = get_authorization_header(request).decode("utf-8", errors="ignore").strip()
    if not raw:
        return "", ""
    scheme, separator, credentials = raw.partition(" ")
    if not separator:
        return "", ""
    return scheme, credentials.strip()


class BasketDeviceAuthentication(BaseAuthentication):
    def authenticate(self, request):
        kwargs = request.parser_context.get("kwargs", {}) if request.parser_context else {}
        device_code = kwargs.get("device_code") or kwargs.get("device_id") or request.headers.get("X-Device-Code")
        scheme, credentials = _authorization_parts(request)
        raw_secret = request.headers.get("X-Device-Secret", "")
        if scheme.lower() == "device":
            raw_secret = credentials

        if not device_code or not raw_secret:
            raise UnauthorizedDevice()

        try:
            device = BasketDevice.objects.get(device_code=device_code, enabled=True)
        except BasketDevice.DoesNotExist as exc:
            raise UnauthorizedDevice() from exc
        if not device.check_secret(raw_secret):
            raise UnauthorizedDevice()
        return HardwarePrincipal(device.device_code, "device"), device

    def authenticate_header(self, request):
        return "Device"


class CheckoutTerminalAuthentication(BaseAuthentication):
    def authenticate(self, request):
        scheme, credentials = _authorization_parts(request)
        terminal_code = request.headers.get("X-Terminal-Code", "")
        raw_secret = request.headers.get("X-Terminal-Secret", "")

        if scheme.lower() == "terminal":
            terminal_code, separator, raw_secret = credentials.partition(":")
            if not separator:
                raise UnauthorizedTerminal()

        if not terminal_code or not raw_secret:
            raise UnauthorizedTerminal()

        try:
            terminal = CheckoutTerminal.objects.get(terminal_code=terminal_code, enabled=True)
        except CheckoutTerminal.DoesNotExist as exc:
            raise UnauthorizedTerminal() from exc
        if not terminal.check_secret(raw_secret):
            raise UnauthorizedTerminal()
        return HardwarePrincipal(terminal.terminal_code, "terminal"), terminal

    def authenticate_header(self, request):
        return "Terminal"
