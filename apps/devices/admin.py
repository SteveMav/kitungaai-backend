from django.contrib import admin

from .models import BasketDevice, CheckoutTerminal, DeviceCommand


@admin.register(BasketDevice)
class BasketDeviceAdmin(admin.ModelAdmin):
    list_display = ("device_code", "matrix_id", "enabled", "reset_state", "last_seen_at")
    list_filter = ("enabled", "reset_state")
    search_fields = ("device_code",)
    readonly_fields = ("last_seen_at", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(CheckoutTerminal)
class CheckoutTerminalAdmin(admin.ModelAdmin):
    list_display = ("terminal_code", "enabled", "last_seen_at")
    list_filter = ("enabled",)
    search_fields = ("terminal_code",)
    readonly_fields = ("credential_hash", "last_seen_at", "created_at", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(DeviceCommand)
class DeviceCommandAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "command_type", "session_id", "status", "created_at", "acknowledged_at")
    list_filter = ("command_type", "status")
    search_fields = ("device__device_code", "session_id")
    readonly_fields = ("id", "created_at", "acknowledged_at")
