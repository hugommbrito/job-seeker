"""The parts of a profile that differ between users, as validated shapes (project rule 3).

Stored as JSON and validated here on every read. A stored value that no longer validates is
logged and replaced by the defaults for that read, so one bad row cannot break a user's pages.
Phase 2 widens these shapes for ranking; anything it adds must keep old rows valid.
"""

from __future__ import annotations

import logging
from datetime import time
from decimal import Decimal
from typing import Annotated, Literal

import pydantic
from pydantic import Field, StringConstraints

logger = logging.getLogger(__name__)

Place = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=150)]

WorkplaceType = Literal["remote", "hybrid", "onsite"]
EmploymentType = Literal["full_time", "part_time", "contract", "temporary", "internship"]
Seniority = Literal[
    "intern", "junior", "intermediate", "senior", "staff", "principal", "manager", "director"
]


class Strict(pydantic.BaseModel):
    model_config = pydantic.ConfigDict(extra="forbid")


class SalaryFloor(Strict):
    amount: Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")] = "CAD"
    period: Literal["year", "month", "hour"] = "year"


class HardFilters(Strict):
    """What eliminates a posting outright. An empty list means "any"; nothing is assumed."""

    workplace_types: list[WorkplaceType] = Field(default_factory=list, max_length=3)
    locations: list[Place] = Field(default_factory=list, max_length=20)
    salary_floor: SalaryFloor | None = None
    seniority: list[Seniority] = Field(default_factory=list, max_length=8)
    employment_types: list[EmploymentType] = Field(default_factory=list, max_length=5)
    max_commute_km: Annotated[float, Field(gt=0, le=200)] | None = None


class QuietHours(Strict):
    """No pushed notification between these times, in the user's timezone. May wrap midnight."""

    start: time
    end: time


class NotifySettings(Strict):
    quiet_hours: QuietHours | None = Field(
        default_factory=lambda: QuietHours(start=time(22, 0), end=time(8, 0))
    )
    # After this many days without news on an application waiting for the employer, suggest a
    # follow-up or marking it as ghosted.
    follow_up_after_days: Annotated[int, Field(ge=3, le=90)] = 14
    remind_next_action: bool = True
    remind_decision_due: bool = True
    remind_quiet: bool = True


class TrackFilters(Strict):
    """A track's own filters, replacing the profile's where set."""

    workplace_types: list[WorkplaceType] | None = None
    locations: list[Place] | None = None
    seniority: list[Seniority] | None = None


def read[ShapeT: pydantic.BaseModel](shape: type[ShapeT], stored: object, where: str) -> ShapeT:
    """Validate a stored value, falling back to the defaults (and saying so in the log)."""
    try:
        return shape.model_validate(stored or {})
    except pydantic.ValidationError:
        # The row's id only: the value itself is the user's data.
        logger.warning("%s: stored %s is invalid; using the defaults", where, shape.__name__)
        return shape()
