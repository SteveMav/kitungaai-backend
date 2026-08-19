from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated, PermissionDenied, Throttled
from rest_framework.views import exception_handler as drf_exception_handler


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is None:
        return None

    if isinstance(exc, (AuthenticationFailed, NotAuthenticated)):
        error_code = getattr(exc, "default_code", "unauthorized")
        is_terminal = error_code == "unauthorized_terminal"
        response.data = {
            "status": "TERMINAL_UNAUTHORIZED" if is_terminal else "DEVICE_UNAUTHORIZED",
            "error": error_code,
            "message": (
                "Terminal authentication failed. Check terminal code and secret."
                if is_terminal
                else "Device authentication failed. Check device code and secret."
            ),
        }
    elif isinstance(exc, PermissionDenied):
        response.data = {"error": "forbidden"}
    elif isinstance(exc, Throttled):
        response.data = {"error": "rate_limited", "retry_after": exc.wait}
        response.status_code = status.HTTP_429_TOO_MANY_REQUESTS
    return response
