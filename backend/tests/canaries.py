"""Canary data for the isolation suite.

A canary is a unique string planted in one tenant's rows. If it ever shows up in a response to
somebody else, isolation is broken, whatever the cause.

Every tenant model must register a seeder here. The suite fails when one is missing, so a new
per-user table cannot be added without also being covered by the isolation checks.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date

from apps.accounts.models import User
from apps.applications.models import Application, ApplicationEvent, EventKind
from apps.profiles.models import Profile
from apps.tenancy.context import tenant_context
from apps.tenancy.models import TenantModel

Seeder = Callable[[User, str], None]

SEEDERS: dict[type[TenantModel], Seeder] = {}


def seeds(model: type[TenantModel]) -> Callable[[Seeder], Seeder]:
    def register(seeder: Seeder) -> Seeder:
        SEEDERS[model] = seeder
        return seeder

    return register


@seeds(Profile)
def _profile(user: User, canary: str) -> None:
    Profile.objects.create(user=user, timezone=canary)


def _application(name: str) -> Application:
    return Application.objects.create(
        company_name=name, role_title=name, last_activity_at=date(2026, 1, 5)
    )


@seeds(Application)
def _applications(user: User, canary: str) -> None:
    application = _application(canary)
    application.notes = canary
    application.posting_snapshot = {"description": canary}
    application.save()


@seeds(ApplicationEvent)
def _application_events(user: User, canary: str) -> None:
    ApplicationEvent.objects.create(
        application=_application("parent of an event"),
        kind=EventKind.NOTE,
        occurred_on=date(2026, 1, 5),
        text=canary,
    )


def planted_ids(users: Iterable[User]) -> dict[str, list[int]]:
    """The id of every tenant row the given users can see, by model name, for the route crawl."""
    ids: dict[str, list[int]] = defaultdict(list)
    for user in users:
        with tenant_context(user.pk):
            for model in SEEDERS:
                ids[model.__name__] += list(model.objects.values_list("pk", flat=True))
    return dict(ids)


def plant(user: User) -> list[str]:
    """Give the user one row in every tenant table and return the canaries written."""
    canaries = []
    with tenant_context(user.pk):
        for seeder in SEEDERS.values():
            canary = f"canary-{uuid.uuid4().hex}"
            seeder(user, canary)
            canaries.append(canary)
    return canaries
