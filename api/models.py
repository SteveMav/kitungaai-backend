from django.db import models

# Dans backend/api/models.py
    
from django.db import models

class Product(models.Model):
    name = models.CharField(max_length=255)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    barcode = models.CharField(max_length=100, unique=True, blank=True, null=True)
    
    # 🌟 AJOUTE CETTE LIGNE :
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.price} Fc)"


class BasketSession(models.Model):
    """
    Modèle représentant une session de panier connecté.
    Permet de suivre l'état du panier (en cours, validé, annulé).
    """
    STATUS_CHOICES = [
        ('ACTIVE', 'En cours'),
        ('VALIDATED', 'Validé'),
        ('CANCELED', 'Annulé'),
    ]
    
    device_id = models.CharField(max_length=100, verbose_name="Identifiant de la Raspberry/PC IoT")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name="État du panier")
    products = models.ManyToManyField(Product, blank=True, related_name="baskets", verbose_name="Produits détectés")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Panier {self.id} - {self.device_id} ({self.status})"