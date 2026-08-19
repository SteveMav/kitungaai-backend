from django.db.models import Sum
from django.utils import timezone
from rest_framework.authentication import SessionAuthentication
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from api.models import Product
from apps.baskets.models import BasketSession, DetectionEvent
from apps.checkout.models import Sale
from apps.checkout.permissions import CashierAccess
from apps.devices.models import BasketDevice, DeviceCommand


class DashboardStatsView(APIView):
    authentication_classes = (SessionAuthentication,)
    permission_classes = (IsAuthenticated, CashierAccess)

    def get(self, request):
        today = timezone.localdate()
        revenue = (
            Sale.objects.filter(created_at__date=today, payment_status=Sale.PaymentStatus.PAID)
            .aggregate(total=Sum("total"))["total"]
            or 0
        )
        return Response(
            {
                "revenue_today": str(revenue),
                "open_baskets": BasketSession.objects.filter(status=BasketSession.Status.OPEN).count(),
                "checkout_pending": BasketSession.objects.filter(
                    status=BasketSession.Status.CHECKOUT_PENDING
                ).count(),
                "low_stock_products": Product.objects.filter(is_active=True, stock__lte=5).count(),
                "enabled_devices": BasketDevice.objects.filter(enabled=True).count(),
                "pending_resets": DeviceCommand.objects.filter(
                    status=DeviceCommand.Status.PENDING,
                    command_type=DeviceCommand.Type.RESET_SESSION,
                ).count(),
                "unknown_labels_today": DetectionEvent.objects.filter(
                    received_at__date=today,
                    result=DetectionEvent.Result.UNKNOWN_LABEL,
                ).count(),
            }
        )
