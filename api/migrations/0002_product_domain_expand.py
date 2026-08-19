import django.db.models.deletion
from django.db import migrations, models


def reconcile_legacy_sqlite_schema(apps, schema_editor):
    """Converge l'ancien schéma et la base pilote déjà modifiée sans DDL destructif."""
    connection = schema_editor.connection
    if connection.vendor != "sqlite":
        raise RuntimeError("Cette migration de convergence cible la base SQLite du pilote Kitunga.")

    with connection.cursor() as cursor:
        tables = set(connection.introspection.table_names(cursor))
        product_columns = {
            column.name
            for column in connection.introspection.get_table_description(cursor, "api_product")
        }

        if "stock" not in product_columns:
            cursor.execute(
                "ALTER TABLE api_product ADD COLUMN stock integer unsigned NOT NULL DEFAULT 0 CHECK (stock >= 0)"
            )
        if "barcode_image" not in product_columns:
            cursor.execute("ALTER TABLE api_product ADD COLUMN barcode_image varchar(100) NULL")
        if "updated_at" not in product_columns:
            cursor.execute("ALTER TABLE api_product ADD COLUMN updated_at datetime NULL")
            cursor.execute("UPDATE api_product SET updated_at = created_at WHERE updated_at IS NULL")

        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS api_product_name_unique ON api_product(name)"
        )

        if "api_basketitem" not in tables:
            cursor.execute(
                """
                CREATE TABLE api_basketitem (
                    id integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    quantity integer unsigned NOT NULL DEFAULT 1 CHECK (quantity >= 0),
                    added_at datetime NOT NULL,
                    basket_id bigint NOT NULL REFERENCES api_basketsession(id) DEFERRABLE INITIALLY DEFERRED,
                    product_id bigint NOT NULL REFERENCES api_product(id) DEFERRABLE INITIALLY DEFERRED
                )
                """
            )
            if "api_basketsession_products" in tables:
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO api_basketitem
                        (quantity, added_at, basket_id, product_id)
                    SELECT 1, CURRENT_TIMESTAMP, basketsession_id, product_id
                    FROM api_basketsession_products
                    """
                )
        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS api_basketitem_basket_product_unique "
            "ON api_basketitem(basket_id, product_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS api_basketitem_basket_id_idx ON api_basketitem(basket_id)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS api_basketitem_product_id_idx ON api_basketitem(product_id)"
        )


class Migration(migrations.Migration):
    dependencies = [("api", "0001_initial")]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[migrations.RunPython(reconcile_legacy_sqlite_schema, migrations.RunPython.noop)],
            state_operations=[
                migrations.AlterModelOptions(
                    name="product",
                    options={
                        "ordering": ["name"],
                        "verbose_name": "Produit",
                        "verbose_name_plural": "Produits",
                    },
                ),
                migrations.AlterModelOptions(
                    name="basketsession",
                    options={
                        "ordering": ["-created_at"],
                        "verbose_name": "Session de panier",
                        "verbose_name_plural": "Sessions de paniers",
                    },
                ),
                migrations.AlterField(
                    model_name="product",
                    name="name",
                    field=models.CharField(max_length=255, unique=True, verbose_name="Nom du produit"),
                ),
                migrations.AlterField(
                    model_name="product",
                    name="price",
                    field=models.DecimalField(decimal_places=2, max_digits=10, verbose_name="Prix (FC/$)"),
                ),
                migrations.AlterField(
                    model_name="product",
                    name="barcode",
                    field=models.CharField(blank=True, max_length=100, unique=True, verbose_name="Code-barres"),
                ),
                migrations.AlterField(
                    model_name="product",
                    name="created_at",
                    field=models.DateTimeField(auto_now_add=True, verbose_name="Date de création"),
                ),
                migrations.AddField(
                    model_name="product",
                    name="stock",
                    field=models.PositiveIntegerField(default=0, verbose_name="Stock disponible"),
                ),
                migrations.AddField(
                    model_name="product",
                    name="barcode_image",
                    field=models.ImageField(blank=True, null=True, upload_to="barcodes/", verbose_name="Image Code-barres"),
                ),
                migrations.AddField(
                    model_name="product",
                    name="updated_at",
                    field=models.DateTimeField(auto_now=True, verbose_name="Dernière modification"),
                ),
                migrations.AlterField(
                    model_name="basketsession",
                    name="device_id",
                    field=models.CharField(max_length=100, verbose_name="Identifiant du panier/Pi"),
                ),
                migrations.AlterField(
                    model_name="basketsession",
                    name="status",
                    field=models.CharField(
                        choices=[
                            ("ACTIVE", "Actif"),
                            ("COMPLETED", "Terminé"),
                            ("CANCELLED", "Annulé"),
                        ],
                        default="ACTIVE",
                        max_length=20,
                        verbose_name="Statut",
                    ),
                ),
                migrations.AlterField(
                    model_name="basketsession",
                    name="created_at",
                    field=models.DateTimeField(auto_now_add=True, verbose_name="Date de création"),
                ),
                migrations.AlterField(
                    model_name="basketsession",
                    name="updated_at",
                    field=models.DateTimeField(auto_now=True, verbose_name="Dernière mise à jour"),
                ),
                migrations.RemoveField(model_name="basketsession", name="products"),
                migrations.CreateModel(
                    name="BasketItem",
                    fields=[
                        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                        ("quantity", models.PositiveIntegerField(default=1, verbose_name="Quantité")),
                        ("added_at", models.DateTimeField(auto_now_add=True)),
                        (
                            "basket",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="items",
                                to="api.basketsession",
                            ),
                        ),
                        (
                            "product",
                            models.ForeignKey(
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name="basket_items",
                                to="api.product",
                            ),
                        ),
                    ],
                    options={
                        "verbose_name": "Article du panier",
                        "verbose_name_plural": "Articles du panier",
                        "unique_together": {("basket", "product")},
                    },
                ),
                migrations.AddField(
                    model_name="basketsession",
                    name="products",
                    field=models.ManyToManyField(
                        blank=True,
                        related_name="baskets",
                        through="api.BasketItem",
                        to="api.product",
                        verbose_name="Produits",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="product",
            name="is_active",
            field=models.BooleanField(default=True, verbose_name="Actif"),
        ),
        migrations.AddField(
            model_name="product",
            name="sku",
            field=models.CharField(
                blank=True,
                max_length=64,
                null=True,
                unique=True,
                verbose_name="SKU",
            ),
        ),
    ]
