import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def generate_sale_number():
    return f"KIT-{timezone.now():%Y%m%d}-{uuid.uuid4().hex[:10].upper()}"


class MatrixScanEvent(models.Model):
    class Result(models.TextChoices):
        SELECTED = "SELECTED", "Panier sélectionné"
        UNKNOWN_MATRIX = "UNKNOWN_MATRIX", "Matrice inconnue"
        NO_OPEN_SESSION = "NO_OPEN_SESSION", "Aucune session ouverte"
        ALREADY_SELECTED = "ALREADY_SELECTED", "Déjà sélectionné"
        QUALITY_REJECTED = "QUALITY_REJECTED", "Qualité insuffisante"
        VERSION_CONFLICT = "VERSION_CONFLICT", "Conflit de version"

    terminal = models.ForeignKey(
        "devices.CheckoutTerminal",
        on_delete=models.PROTECT,
        related_name="scan_events",
    )
    event_id = models.UUIDField()
    matrix_id = models.PositiveSmallIntegerField(
        validators=(MinValueValidator(1), MaxValueValidator(4095))
    )
    frame_errors = models.PositiveSmallIntegerField(default=0)
    copy_disagreements = models.PositiveSmallIntegerField(default=0)
    cell_contrast = models.DecimalField(max_digits=7, decimal_places=4, null=True, blank=True)
    session = models.ForeignKey(
        "baskets.BasketSession",
        on_delete=models.PROTECT,
        related_name="scan_events",
        null=True,
        blank=True,
    )
    result = models.CharField(max_length=24, choices=Result)
    resulting_version = models.PositiveIntegerField(null=True, blank=True)
    scanned_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-received_at",)
        constraints = [
            models.UniqueConstraint(fields=("terminal", "event_id"), name="checkout_unique_terminal_scan"),
            models.CheckConstraint(
                condition=models.Q(matrix_id__gte=1, matrix_id__lte=4095),
                name="checkout_matrix_id_1_4095",
            ),
        ]
        indexes = [
            models.Index(fields=("matrix_id", "received_at")),
            models.Index(fields=("result", "received_at")),
        ]

    def __str__(self):
        return f"{self.terminal.terminal_code}/{self.event_id}: {self.result}"


class Sale(models.Model):
    class PaymentStatus(models.TextChoices):
        PENDING = "PENDING", "En attente"
        PAID = "PAID", "Payé"
        FAILED = "FAILED", "Échoué"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sale_number = models.CharField(max_length=40, unique=True, default=generate_sale_number, editable=False)
    session = models.OneToOneField(
        "baskets.BasketSession",
        on_delete=models.PROTECT,
        related_name="sale",
    )
    cashier = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="sales",
        null=True,
        blank=True,
    )
    payment_device = models.ForeignKey(
        "devices.BasketDevice",
        on_delete=models.PROTECT,
        related_name="rfid_sales",
        null=True,
        blank=True,
    )
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    payment_method = models.CharField(max_length=32)
    payment_status = models.CharField(max_length=16, choices=PaymentStatus)
    idempotency_key = models.UUIDField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        permissions = [("complete_sale", "Peut finaliser une vente")]

    def __str__(self):
        return self.sale_number


class SaleLine(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("api.Product", on_delete=models.PROTECT, related_name="sale_lines")
    product_sku = models.CharField(max_length=64)
    product_name = models.CharField(max_length=255)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    quantity = models.PositiveIntegerField()
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ("id",)
        constraints = [
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="checkout_sale_quantity_positive"),
        ]

    def __str__(self):
        return f"{self.quantity} × {self.product_name}"


class StockMovement(models.Model):
    class Type(models.TextChoices):
        SALE = "SALE", "Vente"
        ADJUSTMENT = "ADJUSTMENT", "Ajustement"

    product = models.ForeignKey("api.Product", on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=16, choices=Type)
    quantity = models.IntegerField()
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name="stock_movements", null=True, blank=True)
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="stock_movements",
        null=True,
        blank=True,
    )
    reason = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.CheckConstraint(condition=~models.Q(quantity=0), name="checkout_stock_movement_nonzero"),
        ]
        indexes = [models.Index(fields=("product", "created_at"))]

    def __str__(self):
        return f"{self.product.sku}: {self.quantity:+d}"
