from django.contrib import admin
from .models import Product, BasketSession
from django.contrib import admin
from .models import Product

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    # On garde uniquement les champs réels de ton modèle
    list_display = ['name', 'price', 'barcode'] 
    
    # Si tu as ajouté la fonction display_price tout à l'heure, tu peux la mettre comme ceci :
    # list_display = ['name', 'price', 'barcode', 'display_price']

    # Si tu n'as pas d'autres champs à filtrer, tu peux carrément supprimer ou commenter la ligne list_filter
    # list_filter = []
    

@admin.register(BasketSession)
class BasketSessionAdmin(admin.ModelAdmin):
    # Les colonnes pour voir l'état des paniers
    list_display = ('id', 'device_id', 'status', 'created_at', 'updated_at')
    list_filter = ('status', 'created_at')
    search_fields = ('device_id',)
    # Permet d'afficher proprement la relation Plusieurs-à-Plusieurs avec les produits
    filter_horizontal = ('products',)

    
   