from django.urls import path

from .iot import BasketStatusView, RfidPaymentView, SendDetectionView, StartSessionView


urlpatterns = [
    path(
        "devices/<str:device_code>/invoice/start/",
        StartSessionView.as_view(),
        name="iot-session-start",
    ),
    path(
        "devices/<str:device_code>/invoice/detections/",
        SendDetectionView.as_view(),
        name="iot-detection",
    ),
    path(
        "devices/<str:device_code>/invoice/status/",
        BasketStatusView.as_view(),
        name="iot-basket-status",
    ),
    path(
        "devices/<str:device_code>/invoice/rfid-payment/",
        RfidPaymentView.as_view(),
        name="iot-rfid-payment",
    ),
]
