"""Hand-written SQL for migrations: the parts of the schema Django does not model.

Django generates table migrations. Grants and row-level security go through the helpers below,
so there is one definition of the policy and one place to audit.

Roles, passwords and extensions are created by ``infra/postgres/bootstrap.sh``, because they
need a superuser and secrets that a migration must not contain.
"""

from __future__ import annotations

import re

from django.db import migrations

# The role every service except `migrate` connects as.
APP_ROLE = "app"

POLICY_NAME = "tenant_isolation"

# NULLIF: once a session has used the setting, Postgres reports it as '' instead of NULL after
# the transaction ends, and ''::bigint would raise instead of matching nothing.
# The sub-select lets the planner evaluate the setting once per query instead of once per row.
TENANT_PREDICATE = "user_id = (SELECT NULLIF(current_setting('app.user_id', true), '')::bigint)"

_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")


def _identifier(name: str) -> str:
    if not _IDENTIFIER.match(name):
        raise ValueError(f"Not a plain SQL identifier: {name!r}")
    return f'"{name}"'


def enable_tenant_rls(table: str) -> migrations.RunSQL:
    """Enable and force row-level security on a tenant table and add the isolation policy.

    FORCE makes the policy apply to the table owner too, so a query that accidentally runs as
    the owner is filtered like any other. The policy has no role list, so it applies to every
    role; USING hides other users' rows and WITH CHECK refuses to write one.
    """
    ident = _identifier(table)
    return migrations.RunSQL(
        sql=[
            f"ALTER TABLE {ident} ENABLE ROW LEVEL SECURITY",
            f"ALTER TABLE {ident} FORCE ROW LEVEL SECURITY",
            f"CREATE POLICY {POLICY_NAME} ON {ident} "
            f"USING ({TENANT_PREDICATE}) WITH CHECK ({TENANT_PREDICATE})",
        ],
        reverse_sql=[
            f"DROP POLICY IF EXISTS {POLICY_NAME} ON {ident}",
            f"ALTER TABLE {ident} NO FORCE ROW LEVEL SECURITY",
            f"ALTER TABLE {ident} DISABLE ROW LEVEL SECURITY",
        ],
    )


def tenant_key(table: str) -> migrations.RunSQL:
    """Let other tenant tables reference this one together with its owner: UNIQUE (id, user_id).

    The primary key is already unique; this exists only as the target of
    ``same_tenant_foreign_key``. Add it in the migration that creates the parent table.
    """
    ident = _identifier(table)
    name = _identifier(f"{table}_tenant_key")
    return migrations.RunSQL(
        sql=f"ALTER TABLE {ident} ADD CONSTRAINT {name} UNIQUE (id, user_id)",
        reverse_sql=f"ALTER TABLE {ident} DROP CONSTRAINT IF EXISTS {name}",
    )


def same_tenant_foreign_key(table: str, column: str, parent: str) -> migrations.RunSQL:
    """Make ``table.column`` point only at a ``parent`` row owned by the same user.

    Postgres checks foreign keys without applying row-level security, so the plain key Django
    creates would accept a row of user A that points at a row of user B, and would tell A, by
    succeeding, that B's row exists. Matching the pair (id, user_id) closes both. A NULL in the
    column skips the check, as it does for the plain key.
    """
    ident, parent_ident = _identifier(table), _identifier(parent)
    column_ident = _identifier(column)
    name = _identifier(f"{table}_{column}_same_tenant")
    return migrations.RunSQL(
        sql=(
            f"ALTER TABLE {ident} ADD CONSTRAINT {name} "
            f"FOREIGN KEY ({column_ident}, user_id) REFERENCES {parent_ident} (id, user_id) "
            "DEFERRABLE INITIALLY DEFERRED"
        ),
        reverse_sql=f"ALTER TABLE {ident} DROP CONSTRAINT IF EXISTS {name}",
    )


def grant_app_privileges() -> migrations.RunSQL:
    """Give the app role data access, and nothing that changes the schema.

    Default privileges cover tables created by later migrations; the explicit grants cover the
    ones that already exist, whatever order the apps migrate in.
    """
    role = _identifier(APP_ROLE)
    return migrations.RunSQL(
        sql=[
            f"GRANT USAGE ON SCHEMA public TO {role}",
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}",
            f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {role}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public "
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {role}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO {role}",
            # The migration history decides what the schema is; the app may read it, not edit it.
            f"REVOKE INSERT, UPDATE, DELETE ON django_migrations FROM {role}",
        ],
        reverse_sql=[
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM {role}",
            f"ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM {role}",
            f"REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM {role}",
            f"REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {role}",
            f"REVOKE USAGE ON SCHEMA public FROM {role}",
        ],
    )


def require_extension(name: str) -> migrations.RunSQL:
    """Fail the migration with a clear message when a bootstrap extension is missing.

    The migrator role cannot create `vector`, so the migration checks instead of creating.
    """
    _identifier(name)  # validates the name before it is placed in the statement below
    return migrations.RunSQL(
        sql=f"""
            DO $$
            BEGIN
                IF NOT EXISTS (SELECT FROM pg_extension WHERE extname = '{name}') THEN
                    RAISE EXCEPTION 'extension {name} is not installed; '
                        'run infra/postgres/bootstrap.sh as a superuser first';
                END IF;
            END
            $$;
        """,
        reverse_sql=migrations.RunSQL.noop,
    )
