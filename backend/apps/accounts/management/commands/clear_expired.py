"""Delete expired sessions and finished sign-in throttle windows. Safe to run at any time."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.accounts import throttle
from apps.accounts.session_backend import SessionStore


class Command(BaseCommand):
    help = "Delete expired sessions and finished sign-in throttle windows."

    def handle(self, *args: Any, **options: Any) -> None:
        SessionStore.clear_expired()
        removed = throttle.clear_expired()
        self.stdout.write(f"Expired sessions cleared; {removed} throttle window(s) removed.")
