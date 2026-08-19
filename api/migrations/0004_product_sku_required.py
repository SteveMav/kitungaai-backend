from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("api", "0003_product_sku_backfill")]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="sku",
            field=models.CharField(max_length=64, unique=True, verbose_name="SKU"),
        ),
    ]
