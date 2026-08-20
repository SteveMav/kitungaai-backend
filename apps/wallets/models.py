import uuid
from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class Customer(models.Model):
    customer_code = models.CharField(max_length=32, unique=True)
    display_name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("display_name", "customer_code")

    def __str__(self):
        return f"{self.display_name} ({self.customer_code})"


class Wallet(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.PROTECT, related_name="wallet")
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(balance__gte=0), name="wallets_balance_nonnegative"),
        ]

    def __str__(self):
        return f"Wallet {self.customer.customer_code}"


class RfidCard(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="rfid_cards")
    uid = models.CharField(max_length=64, unique=True)
    is_active = models.BooleanField(default=True)
    issued_at = models.DateTimeField(auto_now_add=True)
    disabled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("uid",)

    def save(self, *args, **kwargs):
        self.uid = "".join(self.uid.strip().upper().split())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.uid} → {self.customer}"


class RfidEnrollmentRequest(models.Model):
    """A card observed by a trusted Pi but not yet assigned by an administrator."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        APPROVED = "APPROVED", "Acceptée"
        REJECTED = "REJECTED", "Refusée"

    uid = models.CharField(max_length=64, unique=True)
    device = models.ForeignKey(
        "devices.BasketDevice",
        on_delete=models.PROTECT,
        related_name="rfid_enrollment_requests",
    )
    status = models.CharField(max_length=16, choices=Status, default=Status.PENDING)
    seen_count = models.PositiveIntegerField(default=1)
    requested_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now=True)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        related_name="rfid_enrollment_requests",
        null=True,
        blank=True,
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_rfid_enrollment_requests",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ("-last_seen_at", "-id")
        indexes = [
            models.Index(fields=("status", "last_seen_at")),
            models.Index(fields=("device", "status")),
        ]
        permissions = [
            ("approve_rfid_enrollment", "Peut accepter une demande d'enrôlement RFID"),
        ]

    def save(self, *args, **kwargs):
        self.uid = "".join(self.uid.strip().upper().split())
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.uid} [{self.status}]"


class WalletTransaction(models.Model):
    class Kind(models.TextChoices):
        TOP_UP = "TOP_UP", "Rechargement"
        RFID_PAYMENT = "RFID_PAYMENT", "Paiement RFID"

    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="transactions")
    sale = models.OneToOneField(
        "checkout.Sale",
        on_delete=models.PROTECT,
        related_name="wallet_transaction",
        null=True,
        blank=True,
    )
    kind = models.CharField(max_length=24, choices=Kind)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_after = models.DecimalField(max_digits=14, decimal_places=2)
    idempotency_key = models.UUIDField(unique=True, null=True, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="wallet_transactions",
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(condition=~models.Q(amount=0), name="wallets_transaction_nonzero"),
        ]
        indexes = [models.Index(fields=("wallet", "created_at"))]

    def __str__(self):
        return f"{self.wallet.customer.customer_code}: {self.amount:+.2f}"


class RfidPaymentRequest(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Confirmation attendue"
        INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS", "Solde insuffisant"
        APPROVED = "APPROVED", "Confirmée"
        REJECTED = "REJECTED", "Refusée"
        CANCELLED = "CANCELLED", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.OneToOneField(
        "baskets.BasketSession",
        on_delete=models.PROTECT,
        related_name="rfid_payment_request",
    )
    device = models.ForeignKey(
        "devices.BasketDevice",
        on_delete=models.PROTECT,
        related_name="rfid_payment_requests",
    )
    card = models.ForeignKey(RfidCard, on_delete=models.PROTECT, related_name="payment_requests")
    wallet = models.ForeignKey(Wallet, on_delete=models.PROTECT, related_name="payment_requests")
    sale = models.OneToOneField(
        "checkout.Sale",
        on_delete=models.PROTECT,
        related_name="rfid_payment_request",
        null=True,
        blank=True,
    )
    idempotency_key = models.UUIDField(unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    balance_snapshot = models.DecimalField(max_digits=14, decimal_places=2)
    session_version = models.PositiveIntegerField()
    status = models.CharField(max_length=24, choices=Status, default=Status.PENDING)
    requested_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviewed_rfid_payments",
        null=True,
        blank=True,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-requested_at",)
        indexes = [models.Index(fields=("status", "requested_at"))]

    def __str__(self):
        return f"{self.session_id}: {self.amount:.2f} FC [{self.status}]"
