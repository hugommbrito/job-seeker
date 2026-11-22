"""What the database really enforces, read from pg_catalog and compared with the code's claims.

Used twice: by the test suite, and by `manage.py verify` against a deployed database. It trusts
neither the models nor the migrations; it asks Postgres.
"""

from __future__ import annotations

from typing import Any

from django.db import connection

from apps.tenancy import classification
from apps.tenancy.sql import POLICY_NAME


def _rows(sql: str, params: list[Any] | None = None) -> list[tuple[Any, ...]]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return list(cursor.fetchall())


def database_tables() -> set[str]:
    return {
        name
        for (name,) in _rows(
            """
            SELECT c.relname
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
            """
        )
    }


def _has_user_column(table: str) -> str | None:
    """Return 'NO', 'YES' (the column's nullability) or None when there is no such column."""
    rows = _rows(
        "SELECT is_nullable FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = %s AND column_name = 'user_id'",
        [table],
    )
    return rows[0][0] if rows else None


def catalog_problems() -> list[str]:
    """Return every way the database differs from the tenancy rules. Empty means sound."""
    problems: list[str] = []
    tables = database_tables()
    tenant = classification.tenant_tables()
    catalog = classification.catalog_tables()

    for table in sorted(tables):
        if classification.classify(table) is None:
            problems.append(f"{table}: not classified as tenant, catalog or framework")
    for table in sorted((tenant | catalog | classification.FRAMEWORK_TABLES) - tables):
        problems.append(f"{table}: classified but not in the database")
    if not tenant:
        problems.append("there is no tenant table, so isolation is not being exercised")

    flags = {
        name: (enabled, forced)
        for name, enabled, forced in _rows(
            """
            SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity
            FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public'
            """
        )
    }
    policies: dict[str, list[tuple[Any, ...]]] = {}
    for table, name, command, roles, using, check in _rows(
        "SELECT tablename, policyname, cmd, roles, qual, with_check "
        "FROM pg_policies WHERE schemaname = 'public'"
    ):
        policies.setdefault(table, []).append((name, command, roles, using, check))

    for table in sorted(tenant & tables):
        if flags.get(table) != (True, True):
            problems.append(f"{table}: row-level security is not enabled and forced")
        if _has_user_column(table) != "NO":
            problems.append(f"{table}: user_id must exist and be NOT NULL")
        found = policies.get(table, [])
        if [policy[0] for policy in found] != [POLICY_NAME]:
            problems.append(f"{table}: expected exactly one policy, named {POLICY_NAME}")
            continue
        _name, command, roles, using, check = found[0]
        if command != "ALL":
            problems.append(f"{table}: the policy must cover every command")
        if "public" not in roles:
            problems.append(f"{table}: the policy must apply to every role")
        if "app.user_id" not in (using or ""):
            problems.append(f"{table}: the policy does not filter reads by user")
        if "app.user_id" not in (check or ""):
            problems.append(f"{table}: the policy does not check writes")

    for table in sorted(set(policies) - tenant):
        problems.append(f"{table}: carries a policy but is not a tenant table")
    for table in sorted(catalog & tables):
        if _has_user_column(table) is not None:
            problems.append(f"{table}: a shared table must not have a user column")
    return problems


def rows_visible_without_a_user() -> dict[str, int]:
    """Count the tenant rows the current connection can read with no user set. All must be 0."""
    counts = {}
    for table in sorted(classification.tenant_tables() & database_tables()):
        counts[table] = _rows(f'SELECT count(*) FROM "{table}"')[0][0]  # noqa: S608
    return counts
