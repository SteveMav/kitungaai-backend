import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class BasketSession(models.Model):
    class Status(models.TextChoices):
        OPEN = "OPEN", "Ouvert"
        CHECKOUT_PENDING = "CHECKOUT_PENDING", "À vérifier en caisse"
        COMPLETED = "COMPLETED", "Terminé"
        CANCELLED = "CANCELLED", "Annulé"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(
        "devices.BasketDevice",
        on_delete=models.PROTECT,
        related_name="sessions",
    )
    customer = models.ForeignKey(
        "wallets.Customer",
        on_delete=models.PROTECT,
        related_name="basket_sessions",
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=24, choices=Status, default=Status.OPEN)
    version = models.PositiveIntegerField(default=1)
    selected_terminal = models.ForeignKey(
        "devices.CheckoutTerminal",
        on_delete=models.PROTECT,
        related_name="selected_sessions",
        null=True,
        blank=True,
    )
    opened_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    checkout_started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-opened_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("device",),
                condition=models.Q(status__in=("OPEN", "CHECKOUT_PENDING")),
                name="baskets_one_active_session_per_device",
            ),
        ]
        indexes = [
            models.Index(fields=("device", "status")),
            models.Index(fields=("status", "updated_at")),
        ]
        permissions = [
            ("correct_basket", "Peut corriger les lignes d'un panier"),
            ("release_basket", "Peut libérer un panier de la caisse"),
            ("cancel_basket", "Peut annuler un panier"),
        ]

    def __str__(self):
        return f"{self.device.device_code} / {self.id} [{self.status}]"


class BasketLine(models.Model):
    session = models.ForeignKey(BasketSession, on_delete=models.CASCADE, related_name="lines")
    product = models.ForeignKey("api.Product", on_delete=models.PROTECT, related_name="v1_basket_lines")
    quantity = models.PositiveIntegerField(validators=(MinValueValidator(1), MaxValueValidator(999)))
    unit_price_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("session", "product"),
                name="baskets_unique_product_per_session",
            ),
            models.CheckConstraint(condition=models.Q(quantity__gt=0), name="baskets_line_quantity_positive"),
        ]

    @property
    def subtotal(self):
        return self.unit_price_snapshot * self.quantity

    def __str__(self):
        return f"{self.quantity} × {self.product.name}"


class DetectionEvent(models.Model):
    class Action(models.TextChoices):
        ITEM_ADDED = "ITEM_ADDED", "Article ajouté"
        ITEM_REMOVED = "ITEM_REMOVED", "Article retiré"

    class Result(models.TextChoices):
        APPLIED = "APPLIED", "Appliqué"
        UNKNOWN_LABEL = "UNKNOWN_LABEL", "Label inconnu"
        BASKET_LOCKED = "BASKET_LOCKED", "Panier verrouillé"
        RESET_PENDING = "RESET_PENDING", "Reset en attente"
        INVALID_REMOVAL = "INVALID_REMOVAL", "Retrait invalide"
        VERSION_CONFLICT = "VERSION_CONFLICT", "Conflit de version"

    id = models.BigAutoField(primary_key=True)
    device = models.ForeignKey("devices.BasketDevice", on_delete=models.PROTECT, related_name="events")
    session = models.ForeignKey(
        BasketSession,
        on_delete=models.PROTECT,
        related_name="events",
        null=True,
        blank=True,
    )
    event_id = models.UUIDField()
    boot_id = models.CharField(max_length=96)
    sequence = models.PositiveBigIntegerField()
    action = models.CharField(max_length=16, choices=Action)
    detected_label = models.CharField(max_length=128)
    confidence = models.DecimalField(max_digits=5, decimal_places=4)
    quantity = models.PositiveSmallIntegerField(validators=(MinValueValidator(1), MaxValueValidator(20)))
    model_version = models.CharField(max_length=64, blank=True)
    captured_at = models.DateTimeField()
    received_at = models.DateTimeField(auto_now_add=True)
    product = models.ForeignKey(
        "api.Product",
        on_delete=models.PROTECT,
        related_name="detection_events",
        null=True,
        blank=True,
    )
    result = models.CharField(max_length=24, choices=Result)
    resulting_version = models.PositiveIntegerField(null=True, blank=True)
    resulting_line_quantity = models.PositiveIntegerField(null=True, blank=True)
    is_legacy = models.BooleanField(default=False)

    class Meta:
        ordering = ("received_at", "id")
        constraints = [
            models.UniqueConstraint(fields=("device", "event_id"), name="baskets_unique_device_event"),
            models.CheckConstraint(
                condition=models.Q(confidence__gte=0, confidence__lte=1),
                name="baskets_confidence_0_1",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=20),
                name="baskets_event_quantity_1_20",
            ),
        ]
        indexes = [
            models.Index(fields=("device", "boot_id", "sequence")),
            models.Index(fields=("result", "received_at")),
        ]

    def __str__(self):
        return f"{self.device.device_code}/{self.event_id}: {self.result}"


class BasketCorrection(models.Model):
    session = models.ForeignKey(BasketSession, on_delete=models.PROTECT, related_name="corrections")
    line_id = models.BigIntegerField(null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="basket_corrections")
    action = models.CharField(max_length=32)
    reason = models.CharField(max_length=255)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")

    def __str__(self):
        return f"{self.session_id}: {self.action} par {self.author}"
