"""A user's own settings. The first tenant table.

Phase 0 needs one real per-user table so that row-level security, the meta-test and the
isolation suite run against something that ships, not against a test double. It starts with the
one field that already has a use; the first-run wizard adds the rest (filters, weights, home
location, notification preferences). See docs/adr/0003-first-tenant-table-in-phase-0.md.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.tenancy.models import TenantModel

DEFAULT_TIMEZONE = "America/Toronto"


class Profile(TenantModel):
    # IANA name. Reminders and quiet hours are computed in the user's own timezone.
    timezone = models.CharField(max_length=64, default=DEFAULT_TIMEZONE)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["user"], name="profiles_profile_one_per_user"),
        ]
