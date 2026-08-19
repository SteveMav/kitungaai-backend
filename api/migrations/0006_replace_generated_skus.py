import re
import unicodedata

from django.db import migrations


GENERATED_SKU = re.compile(r"^KIT-\d{12}-\d+$")


def readable_sku(name, product_id):
    normalized = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    stem = re.sub(r"[^A-Z0-9]+", "-", normalized.upper()).strip("-")[:54] or "PRODUIT"
    return stem or f"PRODUIT-{product_id}"


def replace_generated_skus(apps, schema_editor):
    Product = apps.get_model("api", "Product")
    used = set(Product.objects.values_list("sku", flat=True))
    for product in Product.objects.order_by("id"):
        if not GENERATED_SKU.fullmatch(product.sku or ""):
            continue
        used.discard(product.sku)
        candidate = readable_sku(product.name, product.pk)
        if candidate in used:
            candidate = f"{candidate[:54]}-{product.pk}"
        product.sku = candidate
        product.save(update_fields=("sku",))
        used.add(candidate)


class Migration(migrations.Migration):
    dependencies = [("api", "0005_remove_product_barcodes")]

    operations = [migrations.RunPython(replace_generated_skus, migrations.RunPython.noop)]
