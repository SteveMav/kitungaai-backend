from django.contrib import admin

from .models import BasketCorrection, BasketLine, BasketSession, DetectionEvent, UncataloguedBasketLine


class BasketLineInline(admin.TabularInline):
    model = BasketLine
    extra = 0
    readonly_fields = ("product", "quantity", "unit_price_snapshot", "created_at", "updated_at")
    can_delete = False


class UncataloguedBasketLineInline(admin.TabularInline):
    model = UncataloguedBasketLine
    extra = 0
    readonly_fields = ("detected_label", "quantity", "created_at", "updated_at")
    can_delete = False


@admin.register(BasketSession)
class BasketSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "device", "status", "version", "selected_terminal", "opened_at", "updated_at")
    list_filter = ("status",)
    search_fields = ("id", "device__device_code")
    readonly_fields = (
        "id",
        "device",
        "status",
        "version",
        "selected_terminal",
        "opened_at",
        "updated_at",
        "checkout_started_at",
        "completed_at",
        "cancelled_at",
    )
    inlines = (BasketLineInline, UncataloguedBasketLineInline)


@admin.register(DetectionEvent)
class DetectionEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "device", "session", "action", "detected_label", "result", "received_at")
    list_filter = ("action", "result", "is_legacy")
    search_fields = ("event_id", "device__device_code", "detected_label", "boot_id")
    readonly_fields = tuple(field.name for field in DetectionEvent._meta.fields)


@admin.register(BasketCorrection)
class BasketCorrectionAdmin(admin.ModelAdmin):
    list_display = ("session", "line_id", "author", "action", "reason", "created_at")
    search_fields = ("session__id", "author__username", "reason")
    readonly_fields = tuple(field.name for field in BasketCorrection._meta.fields)
