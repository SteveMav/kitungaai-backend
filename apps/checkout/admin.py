from django.contrib import admin

from .models import MatrixScanEvent, Sale, SaleLine, StockMovement


class SaleLineInline(admin.TabularInline):
    model = SaleLine
    extra = 0
    can_delete = False
    readonly_fields = ("product", "product_sku", "product_name", "unit_price", "quantity", "line_total")


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("sale_number", "session", "cashier", "total", "payment_status", "created_at")
    list_filter = ("payment_status", "payment_method")
    search_fields = ("sale_number", "session__id", "cashier__username")
    readonly_fields = tuple(field.name for field in Sale._meta.fields)
    inlines = (SaleLineInline,)


@admin.register(MatrixScanEvent)
class MatrixScanEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "terminal", "matrix_id", "session", "result", "received_at")
    list_filter = ("result", "terminal")
    search_fields = ("event_id", "terminal__terminal_code", "session__id")
    readonly_fields = tuple(field.name for field in MatrixScanEvent._meta.fields)


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("product", "movement_type", "quantity", "sale", "author", "created_at")
    list_filter = ("movement_type",)
    search_fields = ("product__sku", "sale__sale_number", "author__username")
    readonly_fields = tuple(field.name for field in StockMovement._meta.fields)
