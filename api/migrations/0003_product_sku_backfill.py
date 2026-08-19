from django.db import migrations


def populate_skus(apps, schema_editor):
    Product = apps.get_model("api", "Product")
    for product in Product.objects.filter(sku__isnull=True).iterator(chunk_size=200):
        barcode = "".join(character for character in (product.barcode or "") if character.isalnum())
        stem = barcode[:45] or "PRODUCT"
        product.sku = f"KIT-{stem}-{product.pk}"
        product.save(update_fields=("sku",))


def clear_skus(apps, schema_editor):
    Product = apps.get_model("api", "Product")
    Product.objects.update(sku=None)


class Migration(migrations.Migration):
    dependencies = [("api", "0002_product_domain_expand")]

    operations = [migrations.RunPython(populate_skus, clear_skus)]
