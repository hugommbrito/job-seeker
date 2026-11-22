from django.db import migrations

from apps.tenancy import sql


class Migration(migrations.Migration):
    """Database-level setup that every other migration relies on.

    Not a table migration: the tenancy app has no models of its own.
    """

    initial = True

    dependencies: list[tuple[str, str]] = []

    operations = [
        sql.require_extension("vector"),
        sql.require_extension("pg_trgm"),
        sql.grant_app_privileges(),
    ]
