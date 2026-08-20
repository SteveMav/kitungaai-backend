from django.contrib import admin, messages
from django import forms
from django.db import transaction
from django.utils.html import format_html
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse

from .models import (
    Customer,
    RfidCard,
    RfidEnrollmentRequest,
    RfidPaymentRequest,
    Wallet,
    WalletTransaction,
)
from .services import WalletError, credit_wallet


class WalletTopUpForm(forms.Form):
    amount = forms.DecimalField(min_value=1, max_digits=14, decimal_places=2, label="Montant (FC)")
    reason = forms.CharField(max_length=255, label="Motif")


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("customer_code", "display_name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("customer_code", "display_name")

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        Wallet.objects.get_or_create(customer=obj)


@admin.register(RfidCard)
class RfidCardAdmin(admin.ModelAdmin):
    list_display = ("uid", "customer", "is_active", "issued_at")
    list_filter = ("is_active",)
    search_fields = ("uid", "customer__customer_code", "customer__display_name")


@admin.register(RfidEnrollmentRequest)
class RfidEnrollmentRequestAdmin(admin.ModelAdmin):
    list_display = ("uid", "device", "status", "customer", "seen_count", "last_seen_at", "reviewed_by")
    list_filter = ("status", "device")
    search_fields = ("uid", "device__device_code", "customer__customer_code", "customer__display_name")
    readonly_fields = (
        "uid",
        "device",
        "status",
        "seen_count",
        "requested_at",
        "last_seen_at",
        "customer",
        "reviewed_by",
        "reviewed_at",
    )

    def has_add_permission(self, request):
        return False


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ("customer", "balance", "is_active", "updated_at", "top_up_link")
    list_filter = ("is_active",)
    search_fields = ("customer__customer_code", "customer__display_name")
    readonly_fields = ("balance", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False

    @admin.display(description="Action")
    def top_up_link(self, wallet):
        url = reverse("admin:wallets_wallet_top_up", args=(wallet.pk,))
        return format_html('<a href="{}">Recharger</a>', url)

    def get_urls(self):
        return [
            path("<int:wallet_id>/top-up/", self.admin_site.admin_view(self.top_up), name="wallets_wallet_top_up"),
        ] + super().get_urls()

    def top_up(self, request, wallet_id):
        wallet = get_object_or_404(Wallet.objects.select_related("customer"), pk=wallet_id)
        form = WalletTopUpForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                with transaction.atomic():
                    credit_wallet(
                        wallet_id=wallet.id,
                        amount=form.cleaned_data["amount"],
                        user=request.user,
                        reason=form.cleaned_data["reason"],
                    )
            except WalletError:
                form.add_error(None, "Ce portefeuille ne peut pas être rechargé.")
            else:
                self.message_user(request, "Portefeuille rechargé.", messages.SUCCESS)
                return redirect("admin:wallets_wallet_changelist")
        return render(
            request,
            "admin/wallets/wallet/top_up.html",
            {**self.admin_site.each_context(request), "wallet": wallet, "form": form},
        )


@admin.register(WalletTransaction)
class WalletTransactionAdmin(admin.ModelAdmin):
    list_display = ("wallet", "kind", "amount", "balance_after", "sale", "created_by", "created_at")
    list_filter = ("kind",)
    search_fields = ("wallet__customer__customer_code", "sale__sale_number", "reason")
    readonly_fields = tuple(field.name for field in WalletTransaction._meta.fields)

    def has_add_permission(self, request):
        return False


@admin.register(RfidPaymentRequest)
class RfidPaymentRequestAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "card", "amount", "balance_snapshot", "status", "requested_at")
    list_filter = ("status", "device")
    search_fields = ("card__uid", "card__customer__display_name", "session__id")
    readonly_fields = tuple(field.name for field in RfidPaymentRequest._meta.fields)

    def has_add_permission(self, request):
        return False
