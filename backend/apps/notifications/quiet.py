"""Quiet hours, in the user's own timezone (the rental monitor used one fixed zone for all)."""

from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

from apps.profiles.settings import QuietHours


def in_quiet_hours(window: QuietHours | None, zone: ZoneInfo, now: datetime) -> bool:
    """Whether ``now`` falls in the window. A window may wrap midnight: 22:00 to 08:00."""
    if window is None or window.start == window.end:
        return False
    local: time = now.astimezone(zone).time().replace(second=0, microsecond=0)
    if window.start < window.end:
        return window.start <= local < window.end
    return local >= window.start or local < window.end
