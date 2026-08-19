from django.db import models

from api.models import Product as CatalogProduct


Product = CatalogProduct


class VisionLabel(models.Model):
    label = models.CharField(max_length=128)
    product = models.ForeignKey(
        "api.Product",
        on_delete=models.PROTECT,
        related_name="vision_labels",
    )
    model_version = models.CharField(
        max_length=64,
        blank=True,
        help_text="Vide signifie que le label est valable pour toutes les versions du modèle.",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("label", "model_version")
        constraints = [
            models.UniqueConstraint(
                fields=("label", "model_version"),
                name="catalog_unique_label_version",
            ),
        ]
        indexes = [models.Index(fields=("label", "is_active"))]

    def save(self, *args, **kwargs):
        self.label = self.label.strip().lower()
        self.model_version = self.model_version.strip()
        super().save(*args, **kwargs)

    def __str__(self):
        suffix = f" ({self.model_version})" if self.model_version else ""
        return f"{self.label}{suffix} → {self.product}"
