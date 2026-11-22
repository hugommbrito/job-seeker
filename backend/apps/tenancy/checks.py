"""Refuse to run with a database role that row-level security does not bind.

Policies do not apply to superusers or to roles with BYPASSRLS, and the app must not be able to
alter the tables it reads. A wrong DSN would otherwise fail open and silently: every query would
keep working and simply see every tenant's rows.

The check is tagged `database`, so it runs for `manage.py check --database default` (which the
api container runs before starting gunicorn) and for `manage.py migrate`.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import CheckMessage, Error, Tags, register
from django.db import connections


@dataclass(frozen=True)
class RoleFacts:
    is_superuser: bool
    bypasses_rls: bool
    owned_tables: int


def read_role_facts(alias: str = "default") -> RoleFacts:
    with connections[alias].cursor() as cursor:
        cursor.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")
        is_superuser, bypasses_rls = cursor.fetchone()
        cursor.execute(
            "SELECT count(*) FROM pg_tables "
            "WHERE schemaname = 'public' AND tableowner = current_user"
        )
        (owned_tables,) = cursor.fetchone()
    return RoleFacts(bool(is_superuser), bool(bypasses_rls), int(owned_tables))


def role_problems(facts: RoleFacts, service_name: str) -> list[CheckMessage]:
    errors: list[CheckMessage] = []
    if facts.is_superuser:
        errors.append(
            Error(
                "The database role is a superuser, which row-level security does not apply to.",
                hint="Connect as `migrator` for migrations and as `app` for everything else.",
                id="tenancy.E001",
            )
        )

    # The migrate service is the one process that is meant to own the schema.
    if service_name == "migrate":
        return errors

    if facts.bypasses_rls:
        errors.append(
            Error(
                "The database role has BYPASSRLS, so tenant isolation would not be enforced.",
                hint="Point DATABASE_URL at the `app` role.",
                id="tenancy.E002",
            )
        )
    if facts.owned_tables:
        errors.append(
            Error(
                f"The database role owns {facts.owned_tables} table(s). Only the migrate "
                "service may connect as the schema owner.",
                hint="Point DATABASE_URL at the `app` role, or set SERVICE_NAME=migrate.",
                id="tenancy.E003",
            )
        )
    return errors


@register(Tags.database)
def check_database_role(
    *,
    app_configs: Sequence[AppConfig] | None,
    databases: Sequence[str] | None,
    **kwargs: Any,
) -> list[CheckMessage]:
    if not databases or "default" not in databases:
        return []
    return role_problems(read_role_facts(), settings.SERVICE_NAME)
