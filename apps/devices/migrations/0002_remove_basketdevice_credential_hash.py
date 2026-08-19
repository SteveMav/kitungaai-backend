from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("devices", "0001_initial")]

    operations = [
        migrations.RemoveField(
            model_name="basketdevice",
            name="credential_hash",
        ),
    ]
