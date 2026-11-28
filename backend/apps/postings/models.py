"""Postings a user captured by hand. They never enter the shared catalog.

A capture is per-user data under row-level security (decision 27 in the planning log): a flag
on a shared table would be one missed predicate away from showing one person's capture to
another. Its fields follow the shape the shared postings will have in Phase 2.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.tenancy.models import TenantModel


class CaptureSource(models.TextChoices):
    PASTE = "paste", "Pasted text"
    URL = "url", "From a URL"


class ExtractionStatus(models.TextChoices):
    PENDING = "pending", "Being read"
    EXTRACTED = "extracted", "Read by the model"
    # The model was not asked, failed or refused. The user fills the fields in by hand.
    NOT_EVALUATED = "not_evaluated", "Not evaluated"


class WorkplaceType(models.TextChoices):
    REMOTE = "remote", "Remote"
    HYBRID = "hybrid", "Hybrid"
    ONSITE = "onsite", "On site"
    UNKNOWN = "unknown", "Unknown"


class EmploymentType(models.TextChoices):
    FULL_TIME = "full_time", "Full time"
    PART_TIME = "part_time", "Part time"
    CONTRACT = "contract", "Contract"
    TEMPORARY = "temporary", "Temporary"
    INTERNSHIP = "internship", "Internship"
    UNKNOWN = "unknown", "Unknown"


class SalaryPeriod(models.TextChoices):
    YEAR = "year", "Year"
    MONTH = "month", "Month"
    WEEK = "week", "Week"
    DAY = "day", "Day"
    HOUR = "hour", "Hour"
    UNKNOWN = "unknown", "Unknown"


class SalaryOrigin(models.TextChoices):
    """Where the salary came from: a source's structured field beats the posting's text."""

    STRUCTURED = "structured", "Structured field"
    TEXT = "text", "Posting text"
    NONE = "none", "Not stated"


class TriState(models.TextChoices):
    """A fact that may be undeterminable. Unknown never counts against a posting (rule 2)."""

    YES = "yes", "Yes"
    NO = "no", "No"
    UNKNOWN = "unknown", "Unknown"


class UserPosting(TenantModel):
    source = models.CharField(max_length=8, choices=CaptureSource.choices)
    url = models.URLField(max_length=2000, blank=True, default="")
    title = models.CharField(max_length=300, blank=True, default="")
    company_name = models.CharField(max_length=200, blank=True, default="")
    location_text = models.CharField(max_length=200, blank=True, default="")
    workplace_type = models.CharField(
        max_length=8, choices=WorkplaceType.choices, default=WorkplaceType.UNKNOWN
    )
    employment_type = models.CharField(
        max_length=12, choices=EmploymentType.choices, default=EmploymentType.UNKNOWN
    )
    # Untrusted text, kept as given and only ever rendered as text.
    description_text = models.TextField(blank=True, default="")
    salary_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_currency = models.CharField(max_length=3, blank=True, default="")
    salary_period = models.CharField(
        max_length=8, choices=SalaryPeriod.choices, default=SalaryPeriod.UNKNOWN
    )
    salary_origin = models.CharField(
        max_length=12, choices=SalaryOrigin.choices, default=SalaryOrigin.NONE
    )
    application_deadline = models.DateField(null=True, blank=True)
    language = models.CharField(max_length=8, blank=True, default="")
    ai_screening = models.CharField(
        max_length=8, choices=TriState.choices, default=TriState.UNKNOWN
    )
    existing_vacancy = models.CharField(
        max_length=8, choices=TriState.choices, default=TriState.UNKNOWN
    )
    # What a source returned for a URL capture, as received.
    raw = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, blank=True, default="")

    extraction_status = models.CharField(
        max_length=16, choices=ExtractionStatus.choices, default=ExtractionStatus.PENDING
    )
    # The model's proposal after the checks in apps.postings.extraction, for the review screen.
    extraction = models.JSONField(null=True, blank=True)
    # Why there is no proposal: an outcome of apps.llm, or "stalled". Machine-readable.
    extraction_error = models.CharField(max_length=32, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(source__in=CaptureSource.values),
                name="user_posting_source_valid",
            ),
            models.CheckConstraint(
                condition=models.Q(extraction_status__in=ExtractionStatus.values),
                name="user_posting_extraction_status_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"captured posting {self.pk}"
