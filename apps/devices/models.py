import uuid
import hashlib
import secrets

from django.contrib.auth.hashers import check_password
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models


hardware_code_validator = RegexValidator(
    regex=r"^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$",
    message="Utilisez 2 à 64 caractères alphanumériques, point, tiret ou soulignement.",
)


class CredentialMixin(models.Model):
    credential_hash = models.CharField(max_length=128, editable=False)

    class Meta:
        abstract = True

    def set_secret(self, raw_secret):
        if not raw_secret or len(raw_secret) < 24:
            raise ValueError("Un secret matériel doit contenir au moins 24 caractères.")
        digest = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
        self.credential_hash = f"sha256${digest}"

    def check_secret(self, raw_secret):
        if not raw_secret:
            return False
        if self.credential_hash.startswith("sha256$"):
            candidate = hashlib.sha256(raw_secret.encode("utf-8")).hexdigest()
            return secrets.compare_digest(self.credential_hash, f"sha256${candidate}")
        return check_password(raw_secret, self.credential_hash)


class BasketDevice(models.Model):
    class ResetState(models.TextChoices):
        READY = "READY", "Prêt"
        PENDING = "PENDING", "Réinitialisation attendue"

    device_code = models.CharField(max_length=64, unique=True, validators=(hardware_code_validator,))
    matrix_id = models.PositiveSmallIntegerField(
        unique=True,
        validators=(MinValueValidator(1), MaxValueValidator(4095)),
    )
    enabled = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    firmware_version = models.CharField(max_length=64, blank=True)
    last_boot_id = models.CharField(max_length=96, blank=True)
    reset_state = models.CharField(max_length=16, choices=ResetState, default=ResetState.READY)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("matrix_id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(matrix_id__gte=1, matrix_id__lte=4095),
                name="devices_matrix_id_1_4095",
            ),
        ]

    def __str__(self):
        return f"{self.device_code} (matrice {self.matrix_id})"


class CheckoutTerminal(CredentialMixin):
    terminal_code = models.CharField(max_length=64, unique=True, validators=(hardware_code_validator,))
    enabled = models.BooleanField(default=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("terminal_code",)

    def __str__(self):
        return self.terminal_code


class DeviceCommand(models.Model):
    class Type(models.TextChoices):
        RESET_SESSION = "RESET_SESSION", "Réinitialiser la session"

    class Status(models.TextChoices):
        PENDING = "PENDING", "En attente"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acquittée"
        CANCELLED = "CANCELLED", "Annulée"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device = models.ForeignKey(BasketDevice, on_delete=models.PROTECT, related_name="commands")
    command_type = models.CharField(max_length=32, choices=Type)
    session_id = models.UUIDField(db_index=True)
    status = models.CharField(max_length=16, choices=Status, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at",)
        constraints = [
            models.UniqueConstraint(
                fields=("device", "command_type", "session_id"),
                name="devices_unique_command_session",
            ),
        ]
        indexes = [models.Index(fields=("device", "status", "created_at"))]

    def __str__(self):
        return f"{self.device.device_code}: {self.command_type} [{self.status}]"
