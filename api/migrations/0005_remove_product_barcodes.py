from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("api", "0004_product_sku_required")]

    operations = [
        migrations.RemoveField(model_name="product", name="barcode_image"),
        migrations.RemoveField(model_name="product", name="barcode"),
    ]
