from django.db import migrations


def seed_legacy_labels(apps, schema_editor):
    Product = apps.get_model("api", "Product")
    VisionLabel = apps.get_model("catalog", "VisionLabel")
    for product in Product.objects.iterator(chunk_size=200):
        label = product.name.strip().lower()
        if label:
            VisionLabel.objects.get_or_create(
                label=label,
                model_version="",
                defaults={"product_id": product.pk, "is_active": product.is_active},
            )


def remove_seeded_labels(apps, schema_editor):
    Product = apps.get_model("api", "Product")
    VisionLabel = apps.get_model("catalog", "VisionLabel")
    labels = [name.strip().lower() for name in Product.objects.values_list("name", flat=True)]
    VisionLabel.objects.filter(model_version="", label__in=labels).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("api", "0004_product_sku_required"),
        ("catalog", "0001_initial"),
    ]

    operations = [migrations.RunPython(seed_legacy_labels, remove_seeded_labels)]
