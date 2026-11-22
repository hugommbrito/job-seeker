"""The catalog meta-test: what the database really enforces, read from pg_catalog.

It does not trust the models or the migrations. It asks Postgres which tables exist, who owns
them and which policies they carry, and compares that with what the code claims.
"""

from __future__ import annotations

import io

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError, connection, transaction

from apps.tenancy import catalog, classification
from apps.tenancy.checks import RoleFacts
from apps.tenancy.sql import POLICY_NAME
from tests.canaries import plant

pytestmark = pytest.mark.django_db


def _rows(sql: str, params: list[object] | None = None) -> list[tuple]:
    with connection.cursor() as cursor:
        cursor.execute(sql, params or [])
        return cursor.fetchall()


def _execute(sql: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(sql)


# What Postgres says when a role lacks the right, as opposed to any other failure.
REFUSED = "must be owner|permission denied"


def _tables() -> set[str]:
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


def test_the_suite_runs_as_the_app_role():
    (user, is_superuser, bypasses_rls) = _rows(
        "SELECT current_user, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user"
    )[0]
    assert user == "app"
    assert not is_superuser
    assert not bypasses_rls


def test_the_app_role_owns_no_table():
    owners = dict(_rows("SELECT tablename, tableowner FROM pg_tables WHERE schemaname = 'public'"))
    assert owners, "no tables found; did the migrations run?"
    assert "app" not in set(owners.values())


def test_every_table_is_classified():
    unclassified = sorted(table for table in _tables() if classification.classify(table) is None)
    assert not unclassified, (
        f"Unclassified tables: {unclassified}. Inherit TenantModel or CatalogModel, or add the "
        "table to FRAMEWORK_TABLES in apps/tenancy/classification.py."
    )


def test_no_classification_is_stale():
    claimed = (
        classification.tenant_tables()
        | classification.catalog_tables()
        | classification.FRAMEWORK_TABLES
    )
    assert not sorted(claimed - _tables())


def test_there_is_at_least_one_tenant_table():
    # Without one, every check below would pass by having nothing to check.
    assert classification.tenant_tables()


def test_every_tenant_table_is_forced_and_has_the_policy():
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
    policies = {
        table: (name, command, roles, using, check)
        for table, name, command, roles, using, check in _rows(
            "SELECT tablename, policyname, cmd, roles, qual, with_check "
            "FROM pg_policies WHERE schemaname = 'public'"
        )
    }
    for table in classification.tenant_tables():
        assert flags[table] == (True, True), f"{table}: row-level security is not forced"
        assert table in policies, f"{table}: no policy"
        name, command, roles, using, check = policies[table]
        assert name == POLICY_NAME
        assert command == "ALL"
        assert "public" in roles, f"{table}: the policy must apply to every role"
        assert "app.user_id" in using
        assert "app.user_id" in (check or ""), f"{table}: writes are not checked"


def test_every_tenant_table_has_a_mandatory_user_column():
    for table in classification.tenant_tables():
        rows = _rows(
            "SELECT is_nullable FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = 'user_id'",
            [table],
        )
        assert rows == [("NO",)], f"{table}: user_id must exist and be NOT NULL"


def test_only_tenant_tables_carry_policies():
    with_policy = {table for (table,) in _rows("SELECT tablename FROM pg_policies")}
    assert with_policy == set(classification.tenant_tables())


def test_no_catalog_table_has_a_user_column():
    for table in classification.catalog_tables():
        rows = _rows(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s AND column_name = 'user_id'",
            [table],
        )
        assert not rows, f"{table}: a shared table must not have a user column"


def test_with_no_user_set_the_app_role_reads_no_tenant_rows(make_user):
    plant(make_user())
    plant(make_user())
    for table in classification.tenant_tables():
        assert _rows(f'SELECT count(*) FROM "{table}"') == [(0,)], table


def test_the_app_role_cannot_switch_row_level_security_off():
    for table in classification.tenant_tables():
        for statement in (
            f'ALTER TABLE "{table}" DISABLE ROW LEVEL SECURITY',
            f'ALTER TABLE "{table}" NO FORCE ROW LEVEL SECURITY',
            f'DROP POLICY {POLICY_NAME} ON "{table}"',
        ):
            with pytest.raises(DatabaseError, match=REFUSED), transaction.atomic():
                _execute(statement)


def test_the_app_role_cannot_rewrite_the_migration_history():
    with pytest.raises(DatabaseError, match=REFUSED), transaction.atomic():
        _execute("DELETE FROM django_migrations")


def test_the_app_role_cannot_change_the_schema():
    with pytest.raises(DatabaseError, match=REFUSED), transaction.atomic():
        _execute("CREATE TABLE smuggled (id int)")
    with pytest.raises(DatabaseError, match=REFUSED), transaction.atomic():
        _execute("ALTER TABLE accounts_user ADD COLUMN extra text")


# --- The same rules as one function, which `manage.py verify` runs on a deployed database


def test_the_catalog_has_no_problems():
    assert catalog.catalog_problems() == []


def test_an_unclassified_table_is_reported(monkeypatch):
    monkeypatch.setattr(
        classification,
        "FRAMEWORK_TABLES",
        classification.FRAMEWORK_TABLES - {"accounts_loginthrottle"},
    )
    assert catalog.catalog_problems() == [
        "accounts_loginthrottle: not classified as tenant, catalog or framework"
    ]


def test_a_tenant_table_without_protection_is_reported(monkeypatch):
    # Pretend a plain table is a tenant table: it has no policy, no forced security and no
    # user column, and each of those must be named.
    monkeypatch.setattr(
        classification,
        "FRAMEWORK_TABLES",
        classification.FRAMEWORK_TABLES - {"accounts_loginthrottle"},
    )
    real = classification.tenant_tables()
    monkeypatch.setattr(classification, "tenant_tables", lambda: real | {"accounts_loginthrottle"})
    problems = catalog.catalog_problems()
    assert "accounts_loginthrottle: row-level security is not enabled and forced" in problems
    assert "accounts_loginthrottle: user_id must exist and be NOT NULL" in problems
    assert any("expected exactly one policy" in problem for problem in problems)


def test_a_stale_classification_is_reported(monkeypatch):
    monkeypatch.setattr(
        classification, "FRAMEWORK_TABLES", classification.FRAMEWORK_TABLES | {"gone_table"}
    )
    assert catalog.catalog_problems() == ["gone_table: classified but not in the database"]


def test_verify_passes_on_a_sound_database(make_user):
    plant(make_user())
    out = io.StringIO()
    call_command("verify", stdout=out)
    assert "all checks passed" in out.getvalue()
    assert "profiles_profile: 0 row(s) visible with no user set" in out.getvalue()


def test_verify_fails_and_names_the_problem(monkeypatch):
    monkeypatch.setattr(
        classification, "FRAMEWORK_TABLES", classification.FRAMEWORK_TABLES | {"gone_table"}
    )
    err = io.StringIO()
    with pytest.raises(CommandError, match="1 check"):
        call_command("verify", stdout=io.StringIO(), stderr=err)
    assert "gone_table" in err.getvalue()


def test_verify_refuses_to_run_as_the_schema_owner(monkeypatch, settings):
    monkeypatch.setattr(
        "apps.operations.management.commands.verify.read_role_facts",
        lambda: RoleFacts(is_superuser=False, bypasses_rls=False, owned_tables=9),
    )
    with pytest.raises(CommandError):
        call_command("verify", stdout=io.StringIO(), stderr=io.StringIO())
