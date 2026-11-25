"""The user's own calendar: reminders and timelines count days where the user lives."""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from apps.profiles.models import DEFAULT_TIMEZONE, Profile
from apps.tenancy.context import current_user_id


def zone(name: str) -> ZoneInfo:
    """Return the named zone, or the default when the stored name is not a zone (never fails)."""
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        return ZoneInfo(DEFAULT_TIMEZONE)


def user_zone() -> ZoneInfo:
    """The timezone of the user the current tenant context runs as."""
    name = (
        Profile.objects.filter(user_id=current_user_id()).values_list("timezone", flat=True).first()
    )
    return zone(name or DEFAULT_TIMEZONE)


def user_today(now: datetime | None = None) -> date:
    """Today's date for the current user, which is not the server's date near midnight."""
    return (now or datetime.now(tz=ZoneInfo("UTC"))).astimezone(user_zone()).date()
