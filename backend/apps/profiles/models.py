"""A user's own settings. The first tenant table.

Phase 0 needed one real per-user table so that row-level security, the meta-test and the
isolation suite run against something that ships (docs/adr/0003). Phase 1's first-run wizard
fills in the rest: filters, home location, notification preferences, and the user's tracks.

The JSON fields are validated on every read by the shapes in apps.profiles.settings; no profile
is ever defined in code (project rule 3).
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.tenancy.models import TenantModel

DEFAULT_TIMEZONE = "America/Toronto"


class Profile(TenantModel):
    # IANA name. Reminders and quiet hours are computed in the user's own timezone.
    timezone = models.CharField(max_length=64, default=DEFAULT_TIMEZONE)
    # apps.profiles.settings.HardFilters and NotifySettings.
    hard = models.JSONField(default=dict, blank=True)
    notify = models.JSONField(default=dict, blank=True)
    # Where the user commutes from: entered in the app only, never logged, never in a fixture.
    home_label = models.CharField(max_length=100, blank=True, default="")
    home_latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    home_longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    # When the first-run wizard was finished.
    onboarded_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["user"], name="profiles_profile_one_per_user"),
        ]


class Track(TenantModel):
    """A kind of role the user is after. A posting is judged against the track it fits best."""

    name = models.CharField(max_length=100)
    target_titles = models.JSONField(default=list, blank=True)
    summary = models.TextField(blank=True, default="")
    # apps.profiles.settings.TrackFilters.
    filter_overrides = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"track {self.pk}"
