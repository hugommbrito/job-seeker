"""Scheduled upkeep that needs no user context."""

from __future__ import annotations

from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.accounts import throttle
from apps.accounts.session_backend import SessionStore
from apps.operations.models import TaskRun
from apps.operations.runs import recorded

# Long enough to see a pattern of failures, short enough that the table stays small.
TASK_RUN_RETENTION = timedelta(days=30)


@shared_task(name="operations.housekeeping")
def housekeeping() -> None:
    with recorded("operations.housekeeping") as counts:
        SessionStore.clear_expired()
        counts["throttle_windows"] = throttle.clear_expired()
        counts["task_runs"] = TaskRun.objects.filter(
            started_at__lt=timezone.now() - TASK_RUN_RETENTION
        ).delete()[0]
