from django.urls import path

from .iot import BasketStatusView, RfidPaymentView, SendDetectionView, StartSessionView


urlpatterns = [
    path("sessions/start/", StartSessionView.as_view(), name="iot-session-start"),
    path("baskets/<uuid:basket_id>/detections/", SendDetectionView.as_view(), name="iot-detection"),
    path("baskets/<uuid:basket_id>/status/", BasketStatusView.as_view(), name="iot-basket-status"),
    path("baskets/<uuid:basket_id>/rfid-payment/", RfidPaymentView.as_view(), name="iot-rfid-payment"),
]
