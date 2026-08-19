from rest_framework import serializers
from .models import Product, BasketSession, BasketItem


class ProductSerializer(serializers.ModelSerializer):
    prix_formate = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id',
            'sku',
            'name',
            'price',
            'is_active',
            'prix_formate',
            'stock',
            'created_at',
            'updated_at'
        ]

    def get_prix_formate(self, obj):
        if obj.price is not None:
            formatted_price = int(obj.price) if obj.price % 1 == 0 else obj.price
            return f"{formatted_price} Fc"
        return "0 Fc"

class BasketItemSerializer(serializers.ModelSerializer):
    product_details = ProductSerializer(source='product', read_only=True)
    subtotal = serializers.SerializerMethodField()

    class Meta:
        model = BasketItem
        fields = [
            'id',
            'product',
            'product_details',
            'quantity',
            'subtotal'
        ]

    def get_subtotal(self, obj):
        if obj.product and obj.product.price:
            return obj.quantity * obj.product.price
        return 0


class BasketSessionSerializer(serializers.ModelSerializer):
    # La relation `items` correspond au related_name défini sur BasketItem.basket.
    items = BasketItemSerializer(many=True, read_only=True)
    total_price = serializers.SerializerMethodField()
    item_count = serializers.SerializerMethodField()

    class Meta:
        model = BasketSession
        fields = [
            'id',
            'device_id',
            'status',
            'items',
            'item_count',
            'total_price',
            'created_at',
            'updated_at'
        ]

    def get_total_price(self, obj):
        return sum(item.quantity * item.product.price for item in obj.items.all() if item.product and item.product.price)

    def get_item_count(self, obj):
        return sum(item.quantity for item in obj.items.all())
