"""Building the guest's synthetic tenant from demo/persona.json.

The persona is data, loaded through the same validation and importer as a user's own (project
rule 3: no profile is defined in code). Dates are written relative to the day of seeding, as
"-12d" or "+3d", so the demo never looks stale. Only the guest's own rows are touched.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.applications import importer
from apps.applications.models import Application
from apps.documents.models import Document
from apps.documents.store import document_store
from apps.documents.uploads import inspect
from apps.notifications.service import notify
from apps.profiles.models import Profile, Track
from apps.profiles.settings import HardFilters, NotifySettings, TrackFilters
from apps.tenancy import classification
from apps.tenancy.context import tenant_context

_RELATIVE = re.compile(r"^([+-]\d{1,4})d$")


def resolve_dates(value: Any, today: date) -> Any:
    """Turn every "-12d" in the structure into the ISO date twelve days before ``today``."""
    if isinstance(value, dict):
        return {key: resolve_dates(item, today) for key, item in value.items()}
    if isinstance(value, list):
        return [resolve_dates(item, today) for item in value]
    if isinstance(value, str) and (match := _RELATIVE.match(value)):
        return (today + timedelta(days=int(match[1]))).isoformat()
    return value


def load(path: Path, today: date) -> dict[str, Any]:
    data: dict[str, Any] = resolve_dates(json.loads(path.read_text(encoding="utf-8")), today)
    return data


def guest(email: str) -> User:
    """The guest account, created when missing. With no password, only the guest route signs
    it in."""
    user = User.objects.filter(email=email).first()
    if user is None:
        user = User(email=email, role=Role.DEMO, password=make_password(None))
        user.save()
    elif user.role != Role.DEMO:
        raise ValueError("The demo email belongs to an account that is not the guest.")
    return user


def rebuild(user: User, persona: dict[str, Any]) -> dict[str, int]:
    """Replace everything the guest owns with the persona. Runs as the guest."""
    counts: dict[str, int] = {}
    with tenant_context(user.pk), transaction.atomic():
        for model in classification.tenant_models():
            model._default_manager.all().delete()

        profile = persona.get("profile", {})
        home = profile.get("home")
        Profile.objects.create(
            timezone=profile.get("timezone", "America/Toronto"),
            hard=HardFilters.model_validate(profile.get("hard", {})).model_dump(mode="json"),
            notify=NotifySettings.model_validate(profile.get("notify", {})).model_dump(mode="json"),
            home_label=home["label"] if home else "",
            home_latitude=home["latitude"] if home else None,
            home_longitude=home["longitude"] if home else None,
            onboarded_at=timezone.now(),
        )
        for track in persona.get("tracks", []):
            Track.objects.create(
                name=track["name"],
                target_titles=track.get("target_titles", []),
                summary=track.get("summary", ""),
                filter_overrides=TrackFilters.model_validate(
                    track.get("filter_overrides", {})
                ).model_dump(mode="json", exclude_none=True),
            )

        rows, errors = importer.validate(persona.get("applications", []))
        if errors:
            raise ValueError("The demo persona is invalid: " + "; ".join(errors))
        counts["applications"] = importer.import_rows(rows).created
        applications = list(Application.objects.order_by("id"))

        for document in persona.get("documents", []):
            content = document["content"].encode()
            accepted = inspect(document["filename"], content)
            stored = Document.objects.create(
                application=applications[document["application"]],
                kind=document.get("kind", "other"),
                filename=accepted.filename,
                content_type=accepted.content_type,
                size=accepted.size,
                sha256=accepted.sha256,
            )
            document_store().save(stored, content)

        for number, item in enumerate(persona.get("notifications", [])):
            application = applications[item["application"]] if "application" in item else None
            notify(
                kind=item.get("kind", "demo"),
                dedupe_key=f"demo:{number}",
                title=item["title"],
                body=item.get("body", ""),
                link=f"/applications/{application.pk}" if application else "",
                application=application,
            )
        counts["notifications"] = len(persona.get("notifications", []))
    return counts
