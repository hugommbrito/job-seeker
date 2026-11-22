"""Which class every database table belongs to.

The catalog meta-test compares this with what is really in the database (pg_catalog) and fails
on any table it cannot place, so a new table cannot ship without a decision about who may read
it. Tenant and catalog tables are derived from the model base classes; framework tables are
listed by hand because they are not ours to subclass.
"""

from __future__ import annotations

from django.apps import apps

from apps.tenancy.models import CatalogModel, TenantModel

# Django's own tables and the authentication tables. None holds per-user application data, and
# none is exposed through the API.
FRAMEWORK_TABLES = frozenset(
    {
        "django_migrations",
        "django_content_type",
        "auth_permission",
        "auth_group",
        "auth_group_permissions",
        "accounts_user",
        "accounts_session",
        "accounts_loginthrottle",
    }
)


def tenant_models() -> list[type[TenantModel]]:
    return [model for model in apps.get_models() if issubclass(model, TenantModel)]


def tenant_tables() -> frozenset[str]:
    return frozenset(model._meta.db_table for model in tenant_models())


def catalog_tables() -> frozenset[str]:
    return frozenset(
        model._meta.db_table for model in apps.get_models() if issubclass(model, CatalogModel)
    )


def classify(table: str) -> str | None:
    """Return 'tenant', 'catalog' or 'framework', or None for a table nobody has classified."""
    classes = [
        name
        for name, tables in (
            ("tenant", tenant_tables()),
            ("catalog", catalog_tables()),
            ("framework", FRAMEWORK_TABLES),
        )
        if table in tables
    ]
    if len(classes) > 1:
        raise ValueError(f"Table {table} is classified more than once: {classes}")
    return classes[0] if classes else None
