"""What can happen to an application, in one place.

The API, the capture flow, the importer and the demo seed all go through these functions, so the
timeline and the derived dates (last interview, decision due, last activity) can never disagree
with what was recorded. Every function runs inside the caller's tenant context.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from django.db.models import Max
from django.utils import timezone

from apps.applications.models import (
    DECISION_NOTICE_DAYS,
    USER_EVENT_KINDS,
    Application,
    ApplicationEvent,
    EventKind,
    Outcome,
    Stage,
)
from apps.profiles.clock import user_today


@dataclass
class NewApplication:
    company_name: str
    role_title: str
    stage: str = Stage.SAVED
    outcome: str = ""
    posting_url: str = ""
    location: str = ""
    source: str = ""
    notes: str = ""
    applied_at: date | None = None
    next_action: str = ""
    next_action_due: date | None = None
    # A past interview the user states while recording an application after the fact.
    last_interview_at: date | None = None
    # When an application recorded after the fact was closed; today when not given.
    closed_on: date | None = None
    posting_snapshot: dict[str, Any] = field(default_factory=dict)


def _record(
    application: Application,
    kind: str,
    occurred_on: date,
    *,
    text: str = "",
    payload: dict[str, Any] | None = None,
) -> ApplicationEvent:
    return ApplicationEvent.objects.create(
        application=application,
        kind=kind,
        occurred_on=occurred_on,
        text=text,
        payload=payload or {},
    )


def refresh_derived_dates(application: Application) -> None:
    """Recompute the dates that come from the timeline and save them."""
    events = application.events.all()
    application.last_activity_at = (
        events.aggregate(latest=Max("occurred_on"))["latest"] or application.last_activity_at
    )
    last_interview = events.filter(kind=EventKind.INTERVIEW).aggregate(latest=Max("occurred_on"))[
        "latest"
    ]
    application.last_interview_at = last_interview
    application.decision_due_at = (
        last_interview + timedelta(days=DECISION_NOTICE_DAYS) if last_interview else None
    )
    application.save(
        update_fields=["last_activity_at", "last_interview_at", "decision_due_at", "updated_at"]
    )


def create_application(data: NewApplication) -> Application:
    today = user_today()
    applied_at = data.applied_at
    application = Application(
        company_name=data.company_name,
        role_title=data.role_title,
        stage=data.stage,
        outcome="",
        posting_url=data.posting_url,
        location=data.location,
        source=data.source,
        notes=data.notes,
        applied_at=applied_at,
        next_action=data.next_action,
        next_action_due=data.next_action_due,
        last_activity_at=today,
        posting_snapshot=data.posting_snapshot,
    )
    application.full_clean(exclude=["user"])
    application.save()
    # A past application is created with the dates it really had, so the timeline starts then.
    started = min(day for day in (today, applied_at) if day is not None)
    _record(application, EventKind.CREATED, started, payload={"stage": data.stage})
    if data.last_interview_at:
        _record(application, EventKind.INTERVIEW, data.last_interview_at)
    if data.outcome:
        close(application, data.outcome, on=data.closed_on)
    refresh_derived_dates(application)
    return application


def move_to_stage(application: Application, stage: str) -> Application:
    if stage not in Stage.values:
        raise ValueError(f"unknown stage {stage!r}")
    if application.stage == stage:
        return application
    previous = application.stage
    application.stage = stage
    today = user_today()
    if stage == Stage.APPLIED and application.applied_at is None:
        application.applied_at = today
    application.save(update_fields=["stage", "applied_at", "updated_at"])
    _record(application, EventKind.STAGE_CHANGED, today, payload={"from": previous, "to": stage})
    refresh_derived_dates(application)
    return application


def close(application: Application, outcome: str, on: date | None = None) -> Application:
    if outcome not in Outcome.values:
        raise ValueError(f"unknown outcome {outcome!r}")
    if application.outcome == outcome:
        return application
    application.outcome = outcome
    application.closed_at = timezone.now()
    application.save(update_fields=["outcome", "closed_at", "updated_at"])
    _record(application, EventKind.CLOSED, on or user_today(), payload={"outcome": outcome})
    refresh_derived_dates(application)
    return application


def reopen(application: Application) -> Application:
    if application.is_open:
        return application
    previous = application.outcome
    application.outcome = ""
    application.closed_at = None
    application.save(update_fields=["outcome", "closed_at", "updated_at"])
    _record(application, EventKind.REOPENED, user_today(), payload={"outcome": previous})
    refresh_derived_dates(application)
    return application


def add_event(
    application: Application, kind: str, occurred_on: date | None = None, text: str = ""
) -> ApplicationEvent:
    if kind not in USER_EVENT_KINDS:
        raise ValueError(f"{kind!r} events are recorded by the app, not added by hand")
    event = _record(application, kind, occurred_on or user_today(), text=text)
    refresh_derived_dates(application)
    return event


def update_event(
    event: ApplicationEvent, *, occurred_on: date | None = None, text: str | None = None
) -> ApplicationEvent:
    if not event.editable:
        raise ValueError("only notes and interviews can be edited")
    if occurred_on is not None:
        event.occurred_on = occurred_on
    if text is not None:
        event.text = text
    event.save(update_fields=["occurred_on", "text"])
    refresh_derived_dates(event.application)
    return event


def delete_event(event: ApplicationEvent) -> None:
    if not event.editable:
        raise ValueError("only notes and interviews can be deleted")
    application = event.application
    event.delete()
    refresh_derived_dates(application)
