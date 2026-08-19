from django.contrib import admin

from .models import VisionLabel


@admin.register(VisionLabel)
class VisionLabelAdmin(admin.ModelAdmin):
    list_display = ("label", "model_version", "product", "is_active", "updated_at")
    list_filter = ("is_active", "model_version")
    search_fields = ("label", "product__name", "product__sku")
    autocomplete_fields = ("product",)
