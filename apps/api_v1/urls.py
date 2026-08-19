from django.urls import path

from apps.baskets.views import DetectionEventView
from apps.checkout.views import (
    CancelBasketView,
    CashierSessionView,
    CompleteSaleView,
    CorrectLineView,
    MatrixScanView,
    ReleaseBasketView,
)
from apps.dashboard.views import DashboardStatsView
from apps.devices.views import CommandAckView, DeviceStateView, HeartbeatView


app_name = "api_v1"

urlpatterns = [
    path("devices/<str:device_code>/heartbeat", HeartbeatView.as_view(), name="device-heartbeat"),
    path("devices/<str:device_code>/events", DetectionEventView.as_view(), name="device-events"),
    path(
        "devices/<str:device_code>/commands/<uuid:command_id>/ack",
        CommandAckView.as_view(),
        name="device-command-ack",
    ),
    path("devices/<str:device_code>/state", DeviceStateView.as_view(), name="device-state"),
    path("checkout/scans", MatrixScanView.as_view(), name="checkout-scans"),
    path("cashier/sessions/<uuid:session_id>", CashierSessionView.as_view(), name="cashier-session"),
    path(
        "cashier/sessions/<uuid:session_id>/lines/<int:line_id>",
        CorrectLineView.as_view(),
        name="cashier-correct-line",
    ),
    path(
        "cashier/sessions/<uuid:session_id>/complete",
        CompleteSaleView.as_view(),
        name="cashier-complete",
    ),
    path(
        "cashier/sessions/<uuid:session_id>/release",
        ReleaseBasketView.as_view(),
        name="cashier-release",
    ),
    path(
        "cashier/sessions/<uuid:session_id>/cancel",
        CancelBasketView.as_view(),
        name="cashier-cancel",
    ),
    path("dashboard/stats", DashboardStatsView.as_view(), name="dashboard-stats"),
]
