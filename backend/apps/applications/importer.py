"""Importing applications that happened before the app, from a CSV or JSON file.

The same path loads the demo tenant, so real data never needs a seed script and the demo is
built the way a user's own history would be. A file is validated in full first: one bad row
imports nothing, and every bad row is reported with its number. A row that matches an existing
application (same company, role and applied date) is skipped, so importing twice is harmless.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date
from typing import Annotated, Any, Literal

import pydantic
from django.db import transaction
from pydantic import Field, StringConstraints

from apps.applications import services
from apps.applications.models import Application, Contact, Outcome, Stage

MAX_BYTES = 1024 * 1024
MAX_ROWS = 1000


def _web_url(value: str) -> str:
    if value and not value.lower().startswith(("https://", "http://")):
        raise ValueError("must be an http or https URL")
    return value


def _blank_to_none(value: object) -> object:
    return None if value == "" else value


Text = Annotated[str, StringConstraints(strip_whitespace=True)]
OptionalDate = Annotated[date | None, pydantic.BeforeValidator(_blank_to_none)]


class ImportedEvent(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    kind: Literal["note", "interview"]
    occurred_on: date
    text: Annotated[Text, Field(max_length=5000)] = ""


class ImportedContact(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")
    name: Annotated[Text, Field(min_length=1, max_length=200)]
    role: Annotated[Text, Field(max_length=200)] = ""
    email: Annotated[Text, Field(max_length=254)] = ""
    phone: Annotated[Text, Field(max_length=50)] = ""
    profile_url: Annotated[Text, Field(max_length=500), pydantic.AfterValidator(_web_url)] = ""
    notes: Annotated[str, Field(max_length=5000)] = ""


class ImportedApplication(pydantic.BaseModel):
    """One row. CSV files carry the plain fields; JSON may add events, contacts and a posting."""

    model_config = pydantic.ConfigDict(extra="forbid")

    company_name: Annotated[Text, Field(min_length=1, max_length=200)]
    role_title: Annotated[Text, Field(min_length=1, max_length=300)]
    stage: Stage = Stage.APPLIED
    outcome: Annotated[Outcome | None, pydantic.BeforeValidator(_blank_to_none)] = None
    posting_url: Annotated[Text, Field(max_length=2000), pydantic.AfterValidator(_web_url)] = ""
    location: Annotated[Text, Field(max_length=200)] = ""
    source: Annotated[Text, Field(max_length=100)] = ""
    notes: Annotated[str, Field(max_length=20000)] = ""
    applied_at: OptionalDate = None
    last_interview_at: OptionalDate = None
    closed_on: OptionalDate = None
    next_action: Annotated[Text, Field(max_length=300)] = ""
    next_action_due: OptionalDate = None
    events: list[ImportedEvent] = Field(default_factory=list, max_length=200)
    contacts: list[ImportedContact] = Field(default_factory=list, max_length=50)
    posting: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ImportResult:
    created: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)


class ImportRefused(ValueError):
    """The file cannot be read at all; the message says why and is safe to show."""


def parse(name: str, content: bytes) -> list[dict[str, Any]]:
    """The file's rows as dictionaries, from CSV (with a header row) or JSON."""
    if len(content) > MAX_BYTES:
        raise ImportRefused("The file is larger than 1 MB.")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise ImportRefused("The file is not UTF-8 text.") from error
    if name.lower().endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError as error:
            raise ImportRefused("The file is not valid JSON.") from error
        rows = data.get("applications") if isinstance(data, dict) else data
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ImportRefused('Expected a list of applications, or {"applications": [...]}.')
        return rows
    if name.lower().endswith(".csv"):
        reader = csv.DictReader(io.StringIO(text))
        # Empty cells are absent values; unknown columns are reported by validation.
        return [{key: value for key, value in row.items() if key} for row in reader]
    raise ImportRefused("Import a .csv or a .json file.")


def validate(rows: list[dict[str, Any]]) -> tuple[list[ImportedApplication], list[str]]:
    if len(rows) > MAX_ROWS:
        return [], [f"The file has {len(rows)} rows; the limit is {MAX_ROWS}."]
    valid, errors = [], []
    for number, row in enumerate(rows, start=1):
        try:
            valid.append(ImportedApplication.model_validate(row))
        except pydantic.ValidationError as error:
            for problem in error.errors(include_input=False, include_url=False):
                where = ".".join(str(part) for part in problem["loc"]) or "row"
                errors.append(f"Row {number}, {where}: {problem['msg']}")
    return valid, errors


def import_rows(rows: list[ImportedApplication]) -> ImportResult:
    """In a tenant context: create the applications, all or nothing."""
    result = ImportResult()
    with transaction.atomic():
        for row in rows:
            if Application.objects.filter(
                company_name=row.company_name, role_title=row.role_title, applied_at=row.applied_at
            ).exists():
                result.skipped += 1
                continue
            application = services.create_application(
                services.NewApplication(
                    company_name=row.company_name,
                    role_title=row.role_title,
                    stage=row.stage,
                    outcome=row.outcome or "",
                    posting_url=row.posting_url,
                    location=row.location,
                    source=row.source,
                    notes=row.notes,
                    applied_at=row.applied_at,
                    next_action=row.next_action,
                    next_action_due=row.next_action_due,
                    last_interview_at=row.last_interview_at,
                    closed_on=row.closed_on,
                    posting_snapshot=row.posting,
                )
            )
            for event in row.events:
                services.add_event(application, event.kind, event.occurred_on, event.text)
            for contact in row.contacts:
                Contact.objects.create(application=application, **contact.model_dump())
            result.created += 1
    return result


def import_file(name: str, content: bytes) -> ImportResult:
    """In a tenant context. Parse, validate in full, then import, or report every problem."""
    valid, errors = validate(parse(name, content))
    if errors:
        return ImportResult(errors=errors)
    return import_rows(valid)
