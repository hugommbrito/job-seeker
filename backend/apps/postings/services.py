"""Turning a reviewed capture into an application."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.applications import services as applications
from apps.applications.models import Application
from apps.postings.models import SalaryOrigin, UserPosting


def content_hash(text: str) -> str:
    """Identifies a posting's text regardless of spacing, to spot the same posting twice."""
    return hashlib.sha256(" ".join(text.split()).encode()).hexdigest()


@dataclass
class ReviewedPosting:
    title: str
    company_name: str
    location_text: str = ""
    workplace_type: str = "unknown"
    employment_type: str = "unknown"
    salary_min: Decimal | None = None
    salary_max: Decimal | None = None
    salary_currency: str = ""
    salary_period: str = "unknown"
    application_deadline: date | None = None
    ai_screening: str = "unknown"
    existing_vacancy: str = "unknown"
    posting_url: str = ""


def snapshot(capture: UserPosting) -> dict[str, Any]:
    """The frozen copy an application keeps: it outlives any change to the capture itself."""

    def number(value: Decimal | None) -> str | None:
        # In cents, as the database stores it, whatever precision the input had.
        return str(Decimal(value).quantize(Decimal("0.01"))) if value is not None else None

    return {
        "source": capture.source,
        "url": capture.url,
        "title": capture.title,
        "company": capture.company_name,
        "location": capture.location_text,
        "workplace_type": capture.workplace_type,
        "employment_type": capture.employment_type,
        "salary": {
            "min": number(capture.salary_min),
            "max": number(capture.salary_max),
            "currency": capture.salary_currency,
            "period": capture.salary_period,
            "origin": capture.salary_origin,
        },
        "application_deadline": (
            capture.application_deadline.isoformat() if capture.application_deadline else None
        ),
        "language": capture.language,
        "ai_screening": capture.ai_screening,
        "existing_vacancy": capture.existing_vacancy,
        "description": capture.description_text,
        "captured_at": timezone.localtime(capture.created_at).isoformat(),
    }


def save_capture(
    capture: UserPosting, reviewed: ReviewedPosting, application: applications.NewApplication
) -> Application:
    """Store what the user confirmed on the capture, then create the application from it."""
    capture.title = reviewed.title
    capture.company_name = reviewed.company_name
    capture.location_text = reviewed.location_text
    capture.workplace_type = reviewed.workplace_type
    capture.employment_type = reviewed.employment_type
    capture.salary_min = reviewed.salary_min
    capture.salary_max = reviewed.salary_max
    capture.salary_currency = reviewed.salary_currency
    capture.salary_period = reviewed.salary_period
    if capture.salary_origin != SalaryOrigin.STRUCTURED:
        stated = reviewed.salary_min is not None or reviewed.salary_max is not None
        capture.salary_origin = SalaryOrigin.TEXT if stated else SalaryOrigin.NONE
    capture.application_deadline = reviewed.application_deadline
    capture.ai_screening = reviewed.ai_screening
    capture.existing_vacancy = reviewed.existing_vacancy
    if reviewed.posting_url:
        capture.url = reviewed.posting_url
    if capture.extraction and capture.extraction.get("language") in ("en", "fr"):
        capture.language = capture.extraction["language"]
    capture.full_clean(exclude=["user"])
    capture.save()

    application.company_name = reviewed.company_name
    application.role_title = reviewed.title
    application.location = application.location or reviewed.location_text
    application.posting_url = capture.url
    application.source = application.source or "capture"
    application.posting_snapshot = snapshot(capture)
    application.user_posting_id = capture.pk
    return applications.create_application(application)
