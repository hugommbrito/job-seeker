"""The tracker's API: applications, their stage and outcome, and their timeline.

Every query here relies on row-level security for isolation; the filters are for meaning, not
for safety. Reads are open to the demo account; every write is denied to it.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import F, Q, QuerySet
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Field, File, Query, Router, Schema, Status, UploadedFile
from ninja.errors import HttpError
from pydantic import AfterValidator, StringConstraints

from apps.accounts.demo import demo_denied, demo_readable
from apps.applications import importer, services
from apps.applications.models import (
    Application,
    ApplicationEvent,
    Contact,
    EventKind,
    Outcome,
    Stage,
)
from apps.documents.api import DocumentOut
from apps.documents.models import Document

router = Router(tags=["applications"])


def _web_url(value: str) -> str:
    # Rendered as a link in the client, so only web schemes: a "javascript:" URL in a card
    # would run in the page of whoever opens it.
    if value and not value.lower().startswith(("https://", "http://")):
        raise ValueError("must be an http or https URL")
    return value


def _email(value: str) -> str:
    if value:
        try:
            validate_email(value)
        except ValidationError as error:
            raise ValueError("is not an email address") from error
    return value


Text = Annotated[str, StringConstraints(strip_whitespace=True)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]
Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)]
WebUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=2000), AfterValidator(_web_url)
]


class ApplicationIn(Schema):
    company_name: Name
    role_title: Title
    stage: Stage = Stage.SAVED
    outcome: Outcome | None = None
    posting_url: WebUrl = ""
    location: Short = ""
    source: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] = ""
    notes: Annotated[str, StringConstraints(max_length=20000)] = ""
    applied_at: date | None = None
    next_action: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    next_action_due: date | None = None
    # For an application recorded after the fact: the last interview it had, and when it closed.
    last_interview_at: date | None = None
    closed_on: date | None = None


class ApplicationPatch(Schema):
    company_name: Name | None = None
    role_title: Title | None = None
    posting_url: WebUrl | None = None
    location: Short | None = None
    source: Annotated[str, StringConstraints(strip_whitespace=True, max_length=100)] | None = None
    notes: Annotated[str, StringConstraints(max_length=20000)] | None = None
    applied_at: date | None = None
    next_action: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = (
        None
    )
    next_action_due: date | None = None


class ApplicationOut(Schema):
    id: int
    company_name: str
    role_title: str
    stage: Stage
    outcome: Outcome | None
    posting_url: str
    location: str
    source: str
    notes: str
    applied_at: date | None
    last_interview_at: date | None
    decision_due_at: date | None
    next_action: str
    next_action_due: date | None
    last_activity_at: date
    created_at: datetime
    updated_at: datetime
    closed_at: datetime | None

    @staticmethod
    def resolve_outcome(obj: Application) -> str | None:
        return obj.outcome or None


class EventOut(Schema):
    id: int
    kind: EventKind
    occurred_on: date
    text: str
    payload: dict[str, Any]
    editable: bool
    created_at: datetime


Email = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=254), AfterValidator(_email)
]
ProfileUrl = Annotated[
    str, StringConstraints(strip_whitespace=True, max_length=500), AfterValidator(_web_url)
]
Phone = Annotated[str, StringConstraints(strip_whitespace=True, max_length=50)]
LongText = Annotated[str, StringConstraints(max_length=5000)]


class ContactIn(Schema):
    name: Name
    role: Short = ""
    email: Email = ""
    phone: Phone = ""
    profile_url: ProfileUrl = ""
    notes: LongText = ""


class ContactPatch(Schema):
    name: Name | None = None
    role: Short | None = None
    email: Email | None = None
    phone: Phone | None = None
    profile_url: ProfileUrl | None = None
    notes: LongText | None = None


class ContactOut(Schema):
    id: int
    name: str
    role: str
    email: str
    phone: str
    profile_url: str
    notes: str
    created_at: datetime


class ApplicationDetailOut(ApplicationOut):
    posting_snapshot: dict[str, Any]
    events: list[EventOut]
    contacts: list[ContactOut]
    documents: list[DocumentOut]

    @staticmethod
    def resolve_events(obj: Application) -> list[ApplicationEvent]:
        return list(obj.events.order_by("-occurred_on", "-created_at", "-id"))

    @staticmethod
    def resolve_contacts(obj: Application) -> list[Contact]:
        return list(obj.contacts.order_by("name", "id"))

    @staticmethod
    def resolve_documents(obj: Application) -> list[Document]:
        return list(obj.documents.order_by("-created_at", "-id"))


class StageIn(Schema):
    stage: Stage


class CloseIn(Schema):
    outcome: Outcome


class EventIn(Schema):
    kind: Literal["note", "interview"]
    occurred_on: date | None = None
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] = ""


class EventPatch(Schema):
    occurred_on: date | None = None
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=5000)] | None = None


class ApplicationFilters(Schema):
    status: Literal["open", "closed", "all"] = "all"
    stage: list[Stage] = Field(default_factory=list)
    q: Text = ""
    sort: Literal["updated", "company", "applied", "next_action"] = "updated"


# Applications without the date sort last whichever way the date runs.
SORTS: dict[str, list[Any]] = {
    "updated": ["-updated_at", "-id"],
    "company": ["company_name", "role_title", "id"],
    "applied": [F("applied_at").desc(nulls_last=True), "-id"],
    "next_action": [F("next_action_due").asc(nulls_last=True), "-updated_at", "id"],
}

_DATE_FIELDS = {"applied_at", "next_action_due"}


def _filtered(filters: ApplicationFilters) -> QuerySet[Application]:
    rows = Application.objects.all()
    if filters.status == "open":
        rows = rows.filter(outcome="")
    elif filters.status == "closed":
        rows = rows.exclude(outcome="")
    if filters.stage:
        rows = rows.filter(stage__in=filters.stage)
    if filters.q:
        rows = rows.filter(
            Q(company_name__icontains=filters.q) | Q(role_title__icontains=filters.q)
        )
    return rows.order_by(*SORTS[filters.sort])


def _application(application_id: int) -> Application:
    # Another user's id is indistinguishable from one that does not exist: row-level security
    # hides the row, so both are a 404.
    return get_object_or_404(Application, pk=application_id)


def _event(application_id: int, event_id: int) -> ApplicationEvent:
    return get_object_or_404(
        ApplicationEvent.objects.select_related("application"),
        pk=event_id,
        application_id=application_id,
    )


@router.get("", response=list[ApplicationOut])
@demo_readable
def list_applications(
    request: HttpRequest, filters: Query[ApplicationFilters]
) -> QuerySet[Application]:
    return _filtered(filters)[:1000]


@router.post("", response={201: ApplicationDetailOut})
@demo_denied
def create_application(request: HttpRequest, payload: ApplicationIn) -> Status[Application]:
    application = services.create_application(
        services.NewApplication(
            **payload.model_dump(exclude={"outcome"}), outcome=payload.outcome or ""
        )
    )
    return Status(201, application)


@router.get("/{int:application_id}", response=ApplicationDetailOut)
@demo_readable
def get_application(request: HttpRequest, application_id: int) -> Application:
    return _application(application_id)


@router.patch("/{int:application_id}", response=ApplicationDetailOut)
@demo_denied
def update_application(
    request: HttpRequest, application_id: int, payload: ApplicationPatch
) -> Application:
    application = _application(application_id)
    changes = payload.model_dump(exclude_unset=True)
    # A required text field cannot be cleared by sending null.
    for name in ("company_name", "role_title"):
        if name in changes and changes[name] is None:
            raise HttpError(422, f"{name} cannot be empty.")
    for name, value in changes.items():
        setattr(application, name, "" if value is None and name not in _DATE_FIELDS else value)
    application.full_clean(exclude=["user"])
    application.save()
    return application


@router.delete("/{int:application_id}", response={204: None})
@demo_denied
def delete_application(request: HttpRequest, application_id: int) -> Status[None]:
    _application(application_id).delete()
    return Status(204, None)


@router.post("/{int:application_id}/stage", response=ApplicationDetailOut)
@demo_denied
def move_application(request: HttpRequest, application_id: int, payload: StageIn) -> Application:
    return services.move_to_stage(_application(application_id), payload.stage)


@router.post("/{int:application_id}/close", response=ApplicationDetailOut)
@demo_denied
def close_application(request: HttpRequest, application_id: int, payload: CloseIn) -> Application:
    return services.close(_application(application_id), payload.outcome)


@router.post("/{int:application_id}/reopen", response=ApplicationDetailOut)
@demo_denied
def reopen_application(request: HttpRequest, application_id: int) -> Application:
    return services.reopen(_application(application_id))


@router.post("/{int:application_id}/events", response={201: EventOut})
@demo_denied
def add_event(
    request: HttpRequest, application_id: int, payload: EventIn
) -> Status[ApplicationEvent]:
    event = services.add_event(
        _application(application_id), payload.kind, payload.occurred_on, payload.text
    )
    return Status(201, event)


@router.patch("/{int:application_id}/events/{int:event_id}", response=EventOut)
@demo_denied
def update_event(
    request: HttpRequest, application_id: int, event_id: int, payload: EventPatch
) -> ApplicationEvent:
    event = _event(application_id, event_id)
    if not event.editable:
        raise HttpError(409, "Only notes and interviews can be edited.")
    return services.update_event(event, occurred_on=payload.occurred_on, text=payload.text)


@router.delete("/{int:application_id}/events/{int:event_id}", response={204: None})
@demo_denied
def delete_event(request: HttpRequest, application_id: int, event_id: int) -> Status[None]:
    event = _event(application_id, event_id)
    if not event.editable:
        raise HttpError(409, "Only notes and interviews can be deleted.")
    services.delete_event(event)
    return Status(204, None)


def _contact(application_id: int, contact_id: int) -> Contact:
    return get_object_or_404(Contact, pk=contact_id, application_id=application_id)


@router.post("/{int:application_id}/contacts", response={201: ContactOut})
@demo_denied
def add_contact(request: HttpRequest, application_id: int, payload: ContactIn) -> Status[Contact]:
    contact = Contact(application=_application(application_id), **payload.model_dump())
    contact.full_clean(exclude=["user"])
    contact.save()
    return Status(201, contact)


@router.patch("/{int:application_id}/contacts/{int:contact_id}", response=ContactOut)
@demo_denied
def update_contact(
    request: HttpRequest, application_id: int, contact_id: int, payload: ContactPatch
) -> Contact:
    contact = _contact(application_id, contact_id)
    changes = payload.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise HttpError(422, "name cannot be empty.")
    for name, value in changes.items():
        setattr(contact, name, value if value is not None else "")
    contact.full_clean(exclude=["user"])
    contact.save()
    return contact


@router.delete("/{int:application_id}/contacts/{int:contact_id}", response={204: None})
@demo_denied
def delete_contact(request: HttpRequest, application_id: int, contact_id: int) -> Status[None]:
    _contact(application_id, contact_id).delete()
    return Status(204, None)


class ImportOut(Schema):
    created: int
    skipped: int
    errors: list[str]


@router.post("/import", response={200: ImportOut, 422: ImportOut})
@demo_denied
def import_applications(request: HttpRequest, file: File[UploadedFile]) -> Status[ImportOut]:
    """Import past applications from a CSV or JSON file: every row, or none and why."""
    if file.size is not None and file.size > importer.MAX_BYTES:
        return Status(
            422, ImportOut(created=0, skipped=0, errors=["The file is larger than 1 MB."])
        )
    try:
        result = importer.import_file(file.name or "", file.read())
    except importer.ImportRefused as refusal:
        return Status(422, ImportOut(created=0, skipped=0, errors=[str(refusal)]))
    out = ImportOut(created=result.created, skipped=result.skipped, errors=result.errors)
    return Status(422 if result.errors else 200, out)
