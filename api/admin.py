from django.contrib import admin
from .models import Product, BasketSession


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('id', 'sku', 'name', 'price', 'stock', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('sku', 'name')


@admin.register(BasketSession)
class BasketSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'device_id', 'status', 'created_at', 'updated_at')
    list_filter = ('status',)
    search_fields = ('device_id',)
