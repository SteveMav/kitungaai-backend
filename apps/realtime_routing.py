from django.urls import re_path

from .realtime_consumers import (
    BasketDisplayConsumer,
    CashierTerminalConsumer,
    RfidEnrollmentConsumer,
    RfidPaymentConsumer,
)


websocket_urlpatterns = [
    re_path(
        r"^ws/v1/cashier/terminals/(?P<terminal_code>[A-Za-z0-9._-]{2,64})/$",
        CashierTerminalConsumer.as_asgi(),
    ),
    re_path(r"^ws/v1/baskets/(?P<matrix_id>[1-9][0-9]{0,3})/$", BasketDisplayConsumer.as_asgi()),
    re_path(r"^ws/v1/rfid-enrollments/$", RfidEnrollmentConsumer.as_asgi()),
    re_path(r"^ws/v1/rfid-payments/$", RfidPaymentConsumer.as_asgi()),
]
