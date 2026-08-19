from django.db import models


class Product(models.Model):
    sku = models.CharField(max_length=64, unique=True, verbose_name="SKU")
    name = models.CharField(max_length=255, unique=True, verbose_name="Nom du produit")
    price = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="Prix (FC/$)")
    stock = models.PositiveIntegerField(default=0, verbose_name="Stock disponible")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dernière modification")
    is_active = models.BooleanField(default=True, verbose_name="Actif")

    class Meta:
        verbose_name = "Produit"
        verbose_name_plural = "Produits"
        ordering = ['name']

    @property
    def current_price(self):
        return self.price

    @property
    def stock_quantity(self):
        return self.stock

    def __str__(self):
        return f"{self.name} - {self.price} (Stock: {self.stock})"


class BasketSession(models.Model):
    STATUS_CHOICES = [
        ('ACTIVE', 'Actif'),
        ('COMPLETED', 'Terminé'),
        ('CANCELLED', 'Annulé'),
    ]

    device_id = models.CharField(max_length=100, verbose_name="Identifiant du panier/Pi")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='ACTIVE', verbose_name="Statut")

    # Relation vers Product via la table intermédiaire BasketItem
    products = models.ManyToManyField(
        Product,
        through='BasketItem',
        related_name='baskets',
        blank=True,
        verbose_name="Produits"
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Date de création")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Dernière mise à jour")

    class Meta:
        verbose_name = "Session de panier"
        verbose_name_plural = "Sessions de paniers"
        ordering = ['-created_at']

    @property
    def total_price(self):
        """ Calcule le montant total cumulé de ce panier. """
        return sum(item.subtotal for item in self.items.all())

    @property
    def total_items(self):
        """ Compte le nombre total d'articles (avec leurs quantités respectives). """
        return sum(item.quantity for item in self.items.all())

    def __str__(self):
        return f"Panier {self.device_id} [{self.status}] - Total: {self.total_price}"


class BasketItem(models.Model):
    """ Table intermédiaire pour lier un Produit à un Panier avec sa Quantité. """
    basket = models.ForeignKey(BasketSession, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='basket_items')
    quantity = models.PositiveIntegerField(default=1, verbose_name="Quantité")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Article du panier"
        verbose_name_plural = "Articles du panier"
        unique_together = ('basket', 'product') # Garantit qu'un produit n'apparaît qu'une fois par panier

    @property
    def subtotal(self):
        """ Calcule le sous-total (Prix x Quantité). """
        return self.product.price * self.quantity

    def __str__(self):
        return f"{self.quantity} x {self.product.name} (Panier: {self.basket.device_id})"
