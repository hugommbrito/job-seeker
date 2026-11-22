"""Canary data for the isolation suite.

A canary is a unique string planted in one tenant's rows. If it ever shows up in a response to
somebody else, isolation is broken, whatever the cause.

Every tenant model must register a seeder here. The suite fails when one is missing, so a new
per-user table cannot be added without also being covered by the isolation checks.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable

from apps.accounts.models import User
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


def plant(user: User) -> list[str]:
    """Give the user one row in every tenant table and return the canaries written."""
    canaries = []
    with tenant_context(user.pk):
        for seeder in SEEDERS.values():
            canary = f"canary-{uuid.uuid4().hex}"
            seeder(user, canary)
            canaries.append(canary)
    return canaries
