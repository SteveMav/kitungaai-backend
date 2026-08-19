from django.db import migrations


YOLO_LABEL_TO_PRODUCT_SKU = {
    "arduino-mega": "ARDUINO-MEGA",
    "esp32-cam": "ESP32-CAM",
    "water-sensor": "CAPTEUR-D-EAU",
    "humidity-sensor": "CAPTEUR-D-HUMIDITE",
    "rfid-scanner": "RFID",
    "breadboard": "BREADBOARD",
    "motor-driver": "DRIVER-MONITOR",
    "lcd-display": "LCD-DISPLAY",
    "ir-sensor": "CAPTEUR-INFRAROUGE",
    "sonar-sensor": "ULTRASON",
}


def add_yolo_label_mappings(apps, schema_editor):
    Product = apps.get_model("api", "Product")
    VisionLabel = apps.get_model("catalog", "VisionLabel")

    for label, sku in YOLO_LABEL_TO_PRODUCT_SKU.items():
        product = Product.objects.filter(sku=sku).first()
        if product is None:
            continue
        VisionLabel.objects.update_or_create(
            label=label,
            model_version="",
            defaults={"product": product, "is_active": product.is_active},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0002_seed_legacy_vision_labels"),
    ]

    operations = [
        migrations.RunPython(add_yolo_label_mappings, migrations.RunPython.noop),
    ]
