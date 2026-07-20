from rest_framework import serializers
from .models import Product, BasketSession  # 🌟 Ajout de l'import du modèle BasketSession

class ProductSerializer(serializers.ModelSerializer):
    # Champ calculé pour afficher le prix en Francs Congolais (Fc)
    prix_formate = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = ['id', 'name', 'price', 'prix_formate', 'barcode']

    def get_prix_formate(self, obj):
        # Retourne le prix avec "Fc" juste après
        if obj.price is not None:
            return f"{obj.price} Fc"
        return "0 Fc"


# 🌟 AJOUT DE LA CLASSE MANQUANTE QUI COUPLAIT TON SERVEUR :
class BasketSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BasketSession
        fields = '__all__'  # Exporte tous les champs du panier (id, device_id, status, etc.)