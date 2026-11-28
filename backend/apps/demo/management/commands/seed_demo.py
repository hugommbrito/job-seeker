"""Rebuild the guest's synthetic tenant from demo/persona.json. Safe to run on every deploy.

manage.py seed_demo
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.demo.persona import guest, load, rebuild
from apps.tenancy.context import active_user_id


class Command(BaseCommand):
    help = "Rebuild the demo tenant from the synthetic persona in demo/."

    def handle(self, *args: Any, **options: Any) -> None:
        if active_user_id() is not None:
            raise CommandError("seed_demo must run outside a tenant context.")
        path = settings.DEMO_DIR / "persona.json"
        if not path.is_file():
            raise CommandError(f"No persona at {path}.")
        from django.utils import timezone

        persona = load(path, timezone.localdate())
        try:
            counts = rebuild(guest(settings.DEMO_EMAIL), persona)
        except ValueError as error:
            raise CommandError(str(error)) from error
        summary = ", ".join(f"{value} {name}" for name, value in counts.items())
        self.stdout.write(self.style.SUCCESS(f"Demo tenant rebuilt: {summary}."))
