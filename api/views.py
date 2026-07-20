from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from .models import Product, BasketSession
from .serializers import BasketSessionSerializer
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

@api_view(['POST'])
def add_detection(request, device_id=None):
    # 1. Récupération flexible du device_id (depuis l'URL, le body, ou un autre nom de clé)
    if not device_id:
        device_id = request.data.get('device_id') or request.data.get('basket_id') or request.data.get('device')
    
    # Si après toutes ces vérifications on n'a rien, là on bloque
    if not device_id:
        return Response({"error": "L'identifiant du périphérique (device_id) est manquant."}, status=status.HTTP_400_BAD_REQUEST)
    
    # 2. Récupérer ou créer le panier actif pour ce périphérique
    basket, created = BasketSession.objects.get_or_create(
        device_id=device_id,
        status='ACTIVE', # Modifie par 'En cours' si c'est ce que tu as mis dans ton modèle
        defaults={'status': 'ACTIVE'}
    )
    
    # 3. Récupérer le produit (si présent)
    label = request.data.get('label') or request.data.get('barcode')
    
    # 🌟 CORRECTION : Si la Pi fait juste un "ensure-active", elle n'envoie pas de produit.
    # On valide le panier et on s'arrête ici sans renvoyer de 400.
    if not label:
        serializer = BasketSessionSerializer(basket)
        return Response({
            "message": "Panier actif vérifié/créé avec succès.",
            "code": basket.device_id, # Donne à la Pi le code qu'elle cherche
            "basket": serializer.data
        }, status=status.HTTP_200_OK)
        
    # 4. Si un produit est envoyé, on le cherche et on l'ajoute
    try:
        product = Product.objects.get(name=label)
    except Product.DoesNotExist:
        return Response({"error": f"Le produit '{label}' n'existe pas."}, status=status.HTTP_404_NOT_FOUND)
    
    # Ajout du produit au panier (adapte 'products' selon ton champ ManyToMany)
    basket.products.add(product)
    basket.save()
    
    # 5. Notification Temps Réel Frontend via WebSockets
    serializer = BasketSessionSerializer(basket)
    try:
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"basket_{device_id}",
            {
                "type": "basket_update",
                "status": "updated",
                "basket": serializer.data
            }
        )
    except Exception as e:
        print(f"Erreur d'envoi WebSocket: {e}")
    
    return Response({
        "message": f"Produit {product.name} ajouté avec succès.",
        "code": basket.device_id,
        "basket": serializer.data
    }, status=status.HTTP_200_OK)

from django.shortcuts import get_object_or_404
from .models import BasketSession
from .serializers import BasketSessionSerializer

@api_view(['GET'])
def get_basket(request, device_id):
    """
    Endpoint pour permettre au Frontend de récupérer les produits d'un panier spécifique.
    URL appelée : /api/basket/BASKET-777/
    """
    # On cherche le panier actif lié à ce device_id (ex: 'BASKET-777' ou 'KITUNGA-PI-001')
    # Si aucun panier actif n'est trouvé, on renvoie une erreur 404 propre
    basket = get_object_or_404(BasketSession, device_id=device_id, status='ACTIVE')
    
    serializer = BasketSessionSerializer(basket)
    return Response(serializer.data, status=status.HTTP_200_OK)

