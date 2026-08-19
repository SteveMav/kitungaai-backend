import logging

from django.db.backends.signals import connection_created
from django.dispatch import receiver


logger = logging.getLogger("kitunga")


@receiver(connection_created)
def configure_sqlite(sender, connection, **kwargs):
    if connection.vendor != "sqlite":
        return

    with connection.cursor() as cursor:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA busy_timeout = 20000")
        database_name = str(connection.settings_dict.get("NAME", ""))
        if database_name and "memory" not in database_name:
            try:
                cursor.execute("PRAGMA journal_mode = WAL")
            except Exception:
                logger.warning("sqlite_wal_not_enabled", exc_info=True)
