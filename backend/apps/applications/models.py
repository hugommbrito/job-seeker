"""Applications: the tracker's cards and the timeline of each.

An application keeps its own copy of the posting (``posting_snapshot``) and no foreign key to the
shared catalog, so a decision a person recorded survives any reset of collected data.

The date fields are calendar dates in the user's timezone, not instants: the 45-day clock and
"N quiet days" count days. Their ``_at`` names follow the implementation plan.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.tenancy.models import TenantModel

# Ontario's Employment Standards Act (in force since 2026-01-01, employers with 25 or more
# employees, publicly advertised postings): an applicant who was interviewed must be told
# whether a hiring decision has been made within 45 days of the last interview. A legal fact
# about the jurisdiction, not a preference, which is why it is a constant.
DECISION_NOTICE_DAYS = 45


class Stage(models.TextChoices):
    DISCOVERED = "discovered", "Discovered"
    SAVED = "saved", "Saved"
    PREPARING = "preparing", "Preparing"
    APPLIED = "applied", "Applied"
    RECRUITER = "recruiter", "Recruiter"
    INTERVIEWS = "interviews", "Interviews"
    OFFER = "offer", "Offer"
    ACCEPTED = "accepted", "Accepted"


class Outcome(models.TextChoices):
    """How an application ended without being accepted. The stage it reached is kept."""

    REJECTED = "rejected", "Rejected"
    GHOSTED = "ghosted", "Ghosted"
    WITHDRAWN = "withdrawn", "Withdrawn"


# Stages in which the applicant is waiting on the employer: the ones the 45-day clock and the
# quiet-days suggestion apply to.
AWAITING_EMPLOYER = (Stage.APPLIED, Stage.RECRUITER, Stage.INTERVIEWS)


class Application(TenantModel):
    company_name = models.CharField(max_length=200)
    role_title = models.CharField(max_length=300)
    stage = models.CharField(max_length=16, choices=Stage.choices, default=Stage.SAVED)
    # Empty while the application is open.
    outcome = models.CharField(max_length=16, choices=Outcome.choices, blank=True, default="")
    posting_url = models.URLField(max_length=2000, blank=True, default="")
    location = models.CharField(max_length=200, blank=True, default="")
    # Where the user found it ("referral", "company site", "capture"). Free text on purpose.
    source = models.CharField(max_length=100, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    applied_at = models.DateField(null=True, blank=True)
    # Derived from the interview events on the timeline, which only the user enters or confirms.
    last_interview_at = models.DateField(null=True, blank=True)
    decision_due_at = models.DateField(null=True, blank=True)
    next_action = models.CharField(max_length=300, blank=True, default="")
    next_action_due = models.DateField(null=True, blank=True)
    # The latest date on the timeline; "quiet days" are counted from it.
    last_activity_at = models.DateField()

    # A frozen copy of the posting as it was when the application was made.
    posting_snapshot = models.JSONField(default=dict, blank=True)
    # The capture it was made from. Losing it loses nothing: the snapshot is the record.
    user_posting = models.ForeignKey(
        "postings.UserPosting",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="applications",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(stage__in=Stage.values), name="applications_stage_valid"
            ),
            models.CheckConstraint(
                condition=models.Q(outcome__in=[*Outcome.values, ""]),
                name="applications_outcome_valid",
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["user", "stage"])]

    def __str__(self) -> str:
        # Not the company or the title: this ends up in logs and tracebacks.
        return f"application {self.pk}"

    @property
    def is_open(self) -> bool:
        return not self.outcome


class EventKind(models.TextChoices):
    CREATED = "created", "Created"
    STAGE_CHANGED = "stage_changed", "Stage changed"
    CLOSED = "closed", "Closed"
    REOPENED = "reopened", "Reopened"
    NOTE = "note", "Note"
    INTERVIEW = "interview", "Interview"


# Kinds the user writes and may edit. The others record what happened and are never rewritten.
USER_EVENT_KINDS = (EventKind.NOTE, EventKind.INTERVIEW)


class ApplicationEvent(TenantModel):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=16, choices=EventKind.choices)
    occurred_on = models.DateField()
    text = models.TextField(blank=True, default="")
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(kind__in=EventKind.values), name="applications_event_kind_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind} event {self.pk}"

    @property
    def editable(self) -> bool:
        return self.kind in USER_EVENT_KINDS


class Contact(TenantModel):
    """Someone at the company or agency, for one application."""

    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name="contacts")
    name = models.CharField(max_length=200)
    role = models.CharField(max_length=200, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=50, blank=True, default="")
    profile_url = models.URLField(max_length=500, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        # Not the name or the address: this ends up in logs.
        return f"contact {self.pk}"
