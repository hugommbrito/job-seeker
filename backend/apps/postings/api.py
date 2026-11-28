"""Capturing a posting by hand: paste it, let the model read it, review the fields, save.

Creating a capture only stores the text and queues the reading; the api never calls the model.
The review screen polls the capture until the reading is done or has failed. Either way the
user can fill the fields in and save: a model that is missing or wrong never blocks the flow.
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated

import pydantic
from django.db import transaction
from django.http import HttpRequest
from django.shortcuts import get_object_or_404
from ninja import Field, Router, Schema, Status
from ninja.errors import HttpError
from pydantic import StringConstraints, model_validator

from apps.accounts.demo import demo_denied, demo_readable
from apps.applications import services as applications
from apps.applications.api import ApplicationDetailOut, Name, Short, Title, WebUrl
from apps.applications.models import Application, Stage
from apps.postings import services
from apps.postings.extraction import MAX_POSTING_CHARS, CaptureExtraction
from apps.postings.models import (
    CaptureSource,
    EmploymentType,
    ExtractionStatus,
    SalaryPeriod,
    TriState,
    UserPosting,
    WorkplaceType,
)
from apps.postings.tasks import extract_capture
from apps.tenancy.context import current_user_id

logger = logging.getLogger(__name__)

router = Router(tags=["captures"])


class CaptureIn(Schema):
    text: Annotated[str, StringConstraints(strip_whitespace=True, max_length=MAX_POSTING_CHARS)]
    url: WebUrl = ""

    @model_validator(mode="after")
    def needs_text(self) -> CaptureIn:
        if not self.text:
            raise ValueError("Paste the posting's text.")
        return self


class Proposal(CaptureExtraction):
    """The model's reading after code checked its quotes; ``issues`` names what was dropped."""

    issues: list[str]


class CaptureOut(Schema):
    id: int
    source: CaptureSource
    url: str
    description_text: str
    extraction_status: ExtractionStatus
    extraction_error: str
    proposal: Proposal | None
    application_id: int | None
    created_at: datetime

    @staticmethod
    def resolve_proposal(obj: UserPosting) -> Proposal | None:
        # Stored JSON is validated on read. One written under an older schema is skipped, not
        # served broken: the user still has the text and can fill the fields in.
        if not obj.extraction:
            return None
        try:
            return Proposal.model_validate(obj.extraction)
        except pydantic.ValidationError:
            logger.warning("capture %s: stored proposal no longer matches its schema", obj.pk)
            return None

    @staticmethod
    def resolve_application_id(obj: UserPosting) -> int | None:
        return obj.applications.values_list("pk", flat=True).first()


Currency = Annotated[
    str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"^$|^[A-Za-z]{3}$")
]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]


class CaptureSaveIn(Schema):
    # The posting, as the user confirmed it.
    title: Title
    company_name: Name
    location_text: Short = ""
    workplace_type: WorkplaceType = WorkplaceType.UNKNOWN
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    salary_min: Money | None = None
    salary_max: Money | None = None
    salary_currency: Currency = ""
    salary_period: SalaryPeriod = SalaryPeriod.UNKNOWN
    application_deadline: date | None = None
    ai_screening: TriState = TriState.UNKNOWN
    existing_vacancy: TriState = TriState.UNKNOWN
    posting_url: WebUrl = ""
    # The application made from it.
    stage: Stage = Stage.SAVED
    applied_at: date | None = None
    next_action: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] = ""
    next_action_due: date | None = None
    notes: Annotated[str, StringConstraints(max_length=20000)] = ""

    @model_validator(mode="after")
    def range_in_order(self) -> CaptureSaveIn:
        if (
            self.salary_min is not None
            and self.salary_max is not None
            and self.salary_min > self.salary_max
        ):
            raise ValueError("The salary's minimum is above its maximum.")
        return self


def _capture(capture_id: int) -> UserPosting:
    return get_object_or_404(UserPosting, pk=capture_id)


def _queue_reading(capture: UserPosting) -> None:
    user_id, capture_id = current_user_id(), capture.pk
    # After commit, so the worker can see the row; robust, so a broker that is down costs the
    # reading (the sweeper hands the capture back as not evaluated), not the request.
    transaction.on_commit(lambda: extract_capture.delay(user_id, capture_id), robust=True)


@router.post("", response={201: CaptureOut})
@demo_denied
def create_capture(request: HttpRequest, payload: CaptureIn) -> Status[UserPosting]:
    capture = UserPosting.objects.create(
        source=CaptureSource.PASTE,
        url=payload.url,
        description_text=payload.text,
        content_hash=services.content_hash(payload.text),
    )
    _queue_reading(capture)
    return Status(201, capture)


@router.get("", response=list[CaptureOut])
@demo_readable
def list_drafts(request: HttpRequest) -> list[UserPosting]:
    """Captures not yet saved as an application, newest first."""
    return list(UserPosting.objects.filter(applications__isnull=True).order_by("-created_at")[:50])


@router.get("/{int:capture_id}", response=CaptureOut)
@demo_readable
def get_capture(request: HttpRequest, capture_id: int) -> UserPosting:
    return _capture(capture_id)


@router.post("/{int:capture_id}/extract", response=CaptureOut)
@demo_denied
def read_again(request: HttpRequest, capture_id: int) -> UserPosting:
    capture = _capture(capture_id)
    if capture.extraction_status == ExtractionStatus.PENDING:
        return capture
    capture.extraction_status = ExtractionStatus.PENDING
    capture.extraction_error = ""
    capture.save(update_fields=["extraction_status", "extraction_error", "updated_at"])
    _queue_reading(capture)
    return capture


@router.post("/{int:capture_id}/save", response={201: ApplicationDetailOut})
@demo_denied
def save_capture(
    request: HttpRequest, capture_id: int, payload: CaptureSaveIn
) -> Status[Application]:
    capture = _capture(capture_id)
    if capture.applications.exists():
        raise HttpError(409, "This posting has already been saved as an application.")
    application = services.save_capture(
        capture,
        services.ReviewedPosting(
            title=payload.title,
            company_name=payload.company_name,
            location_text=payload.location_text,
            workplace_type=payload.workplace_type,
            employment_type=payload.employment_type,
            salary_min=payload.salary_min,
            salary_max=payload.salary_max,
            salary_currency=payload.salary_currency,
            salary_period=payload.salary_period,
            application_deadline=payload.application_deadline,
            ai_screening=payload.ai_screening,
            existing_vacancy=payload.existing_vacancy,
            posting_url=payload.posting_url,
        ),
        applications.NewApplication(
            company_name=payload.company_name,
            role_title=payload.title,
            stage=payload.stage,
            applied_at=payload.applied_at,
            next_action=payload.next_action,
            next_action_due=payload.next_action_due,
            notes=payload.notes,
        ),
    )
    return Status(201, application)


@router.delete("/{int:capture_id}", response={204: None})
@demo_denied
def discard_capture(request: HttpRequest, capture_id: int) -> Status[None]:
    """Remove a capture. An application made from it keeps its own copy of the posting."""
    _capture(capture_id).delete()
    return Status(204, None)
