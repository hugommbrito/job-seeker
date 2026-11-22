"""Acceptance checks against a real database. Read-only, safe to run on a deployed instance.

    manage.py verify

Phase 0 checks tenant isolation as the database actually enforces it: the role this process
connects as, the classification of every table, and the policy on every tenant table. Later
phases add their own checks here. It is run by hand after a deploy and never in CI.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.tenancy.catalog import catalog_problems, rows_visible_without_a_user
from apps.tenancy.checks import read_role_facts, role_problems
from apps.tenancy.context import active_user_id


class Command(BaseCommand):
    help = "Run the acceptance checks against the connected database (read-only)."

    def handle(self, *args: Any, **options: Any) -> None:
        if active_user_id() is not None:
            raise CommandError("verify must run outside a tenant context.")

        problems: list[str] = []

        facts = read_role_facts()
        problems += [str(message.msg) for message in role_problems(facts, settings.SERVICE_NAME)]
        self.stdout.write(
            f"role: superuser={facts.is_superuser} bypassrls={facts.bypasses_rls} "
            f"owned_tables={facts.owned_tables}"
        )

        problems += catalog_problems()

        for table, count in rows_visible_without_a_user().items():
            self.stdout.write(f"{table}: {count} row(s) visible with no user set")
            if count:
                problems.append(f"{table}: {count} row(s) readable without a tenant context")

        if problems:
            for problem in problems:
                self.stderr.write(self.style.ERROR(f"FAIL {problem}"))
            raise CommandError(f"{len(problems)} check(s) failed.")
        self.stdout.write(self.style.SUCCESS("verify: all checks passed"))
