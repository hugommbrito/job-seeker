"""`/api/operations`: whether the background work is getting done. For the owner only.

`/health` answers "is the process up" and touches nothing. This answers the question that
matters once there is background work: did each scheduled task run, recently, and succeed.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.http import HttpRequest
from django.utils import timezone
from ninja import Router, Schema
from ninja.errors import HttpError

from apps.accounts.demo import demo_denied
from apps.accounts.models import Role, User
from apps.operations.models import RunOutcome, TaskRun

router = Router(tags=["operations"])

# A scheduled task is overdue once its last success is older than this many intervals.
OVERDUE_AFTER_INTERVALS = 2


class TaskStatus(Schema):
    name: str
    interval_seconds: int
    last_started_at: datetime | None
    last_outcome: RunOutcome | None
    last_error: str
    last_counts: dict[str, int]
    last_success_at: datetime | None
    runs_last_day: int
    failures_last_day: int
    overdue: bool


class OperationsOut(Schema):
    now: datetime
    tasks: list[TaskStatus]


def require_owner(request: HttpRequest) -> None:
    user = request.user
    if not isinstance(user, User) or user.role != Role.OWNER:
        raise HttpError(403, "Only the owner can see this.")


def task_status(name: str, interval: timedelta, now: datetime) -> TaskStatus:
    runs = TaskRun.objects.filter(name=name)
    last = runs.order_by("-started_at").first()
    last_success = (
        runs.filter(outcome=RunOutcome.OK)
        .order_by("-finished_at")
        .values_list("finished_at", flat=True)
    ).first()
    recent = runs.filter(started_at__gte=now - timedelta(days=1))
    return TaskStatus(
        name=name,
        interval_seconds=int(interval.total_seconds()),
        last_started_at=last.started_at if last else None,
        last_outcome=RunOutcome(last.outcome) if last else None,
        last_error=last.error if last else "",
        last_counts=last.counts if last else {},
        last_success_at=last_success,
        runs_last_day=recent.count(),
        failures_last_day=recent.filter(outcome=RunOutcome.ERROR).count(),
        # Never having succeeded counts as overdue: right after a first deploy that is expected
        # for a moment; any later, beat or the worker is not running.
        overdue=last_success is None or now - last_success > interval * OVERDUE_AFTER_INTERVALS,
    )


@router.get("", response=OperationsOut)
@demo_denied
def operations(request: HttpRequest) -> OperationsOut:
    require_owner(request)
    now = timezone.now()
    return OperationsOut(
        now=now,
        tasks=[
            task_status(name, spec["interval"], now)
            for name, spec in sorted(settings.SCHEDULED_TASKS.items())
        ],
    )
