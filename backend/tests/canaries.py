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
from apps.applications.models import Application, ApplicationEvent, Contact, EventKind
from apps.documents.models import Document, DocumentBlob
from apps.documents.store import document_store
from apps.llm.models import CallOutcome, LlmCall
from apps.notifications.models import (
    ChannelKind,
    Delivery,
    Notification,
    NotificationChannel,
)
from apps.postings.extraction import CaptureExtraction, verify
from apps.postings.models import CaptureSource, UserPosting
from apps.profiles.models import Profile, Track
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
    Profile.objects.create(user=user, timezone=canary, home_label=canary)


@seeds(Track)
def _tracks(user: User, canary: str) -> None:
    Track.objects.create(name=canary, target_titles=[canary], summary=canary)


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


@seeds(Contact)
def _contacts(user: User, canary: str) -> None:
    Contact.objects.create(
        application=_application("parent of a contact"), name=canary, notes=canary
    )


def _document(name: str, content: str) -> Document:
    document = Document.objects.create(
        application=_application("parent of a document"),
        filename=f"{name}.txt",
        content_type="text/plain",
        size=len(content),
        sha256="0" * 64,
    )
    document_store().save(document, content.encode())
    return document


@seeds(Document)
def _documents(user: User, canary: str) -> None:
    _document(canary, "a document")


@seeds(DocumentBlob)
def _document_blobs(user: User, canary: str) -> None:
    # The file's bytes, which only the download route serves.
    _document("a-document", canary)


@seeds(LlmCall)
def _llm_calls(user: User, canary: str) -> None:
    LlmCall.objects.create(
        task="extractor",
        entity_type="capture",
        entity_id=1,
        prompt_version="v1",
        input_hash="0" * 64,
        outcome=CallOutcome.OK,
        response={"title": canary},
    )


@seeds(UserPosting)
def _captures(user: User, canary: str) -> None:
    quoted = {"title": canary, "title_quote": canary}
    empty = dict.fromkeys(CaptureExtraction.model_fields)
    reading = CaptureExtraction.model_validate(
        {
            **empty,
            **{name: "" for name in empty if name.endswith("_quote")},
            **dict.fromkeys(
                (
                    "workplace_type",
                    "employment_type",
                    "salary_period",
                    "ai_screening",
                    "existing_vacancy",
                ),
                "unknown",
            ),
            "language": "en",
            **quoted,
        }
    )
    UserPosting.objects.create(
        source=CaptureSource.PASTE,
        title=canary,
        description_text=canary,
        extraction=verify(reading, canary),
    )


def _channel() -> NotificationChannel:
    channel, _ = NotificationChannel.objects.get_or_create(
        kind=ChannelKind.TELEGRAM, defaults={"config": {"chat_id": 1}}
    )
    return channel


@seeds(NotificationChannel)
def _channels(user: User, canary: str) -> None:
    channel = _channel()
    channel.config = {"chat_id": 1, "note": canary}
    channel.save()


@seeds(Notification)
def _notifications(user: User, canary: str) -> None:
    Notification.objects.create(kind="test", dedupe_key=canary, title=canary, body=canary)


@seeds(Delivery)
def _deliveries(user: User, canary: str) -> None:
    notification = Notification.objects.create(kind="test", dedupe_key=f"d-{canary}", title="t")
    Delivery.objects.create(notification=notification, channel=_channel(), last_error=canary)


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
