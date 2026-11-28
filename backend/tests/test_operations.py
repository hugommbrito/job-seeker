"""Background work: the Celery set-up, the run records and `/api/operations`."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.utils import timezone

from apps.accounts.models import LoginThrottle, Role
from apps.operations.models import RunOutcome, TaskRun
from apps.operations.runs import recorded
from apps.operations.tasks import housekeeping
from config.celery import app

pytestmark = pytest.mark.django_db


def test_every_scheduled_task_exists_and_is_in_the_beat_schedule():
    app.loader.import_default_modules()
    for name in settings.SCHEDULED_TASKS:
        assert name in app.tasks, f"{name} is scheduled but no task has that name"
        assert settings.CELERY_BEAT_SCHEDULE[name]["task"] == name


def test_tasks_survive_a_restart_instead_of_being_lost():
    assert app.conf.task_acks_late is True
    assert app.conf.task_reject_on_worker_lost is True
    assert app.conf.worker_prefetch_multiplier == 1
    assert app.conf.task_time_limit > app.conf.task_soft_time_limit


def test_a_run_records_its_counts():
    with recorded("example") as counts:
        counts["things"] = 3
    run = TaskRun.objects.get()
    assert run.outcome == RunOutcome.OK
    assert run.counts == {"things": 3}
    assert run.finished_at >= run.started_at


def test_a_failed_run_records_the_error_class_and_not_its_message():
    def fail() -> None:
        with recorded("example") as counts:
            counts["before"] = 1
            raise ValueError("private detail")

    with pytest.raises(ValueError, match="private detail"):
        fail()
    run = TaskRun.objects.get()
    assert run.outcome == RunOutcome.ERROR
    assert run.error == "ValueError"
    assert run.counts == {"before": 1}


def test_housekeeping_clears_what_has_expired():
    now = timezone.now()
    LoginThrottle.objects.create(key="old", failures=1, window_start=now - timedelta(days=1))
    TaskRun.objects.create(name="ancient", started_at=now - timedelta(days=60), outcome="ok")
    housekeeping.delay()
    assert not LoginThrottle.objects.filter(key="old").exists()
    assert not TaskRun.objects.filter(name="ancient").exists()
    run = TaskRun.objects.get(name="operations.housekeeping")
    assert run.outcome == RunOutcome.OK
    assert run.counts == {"throttle_windows": 1, "task_runs": 1}


def test_operations_is_for_the_owner(make_user, client_for):
    assert client_for(make_user(role=Role.MEMBER)).get("/api/operations").status_code == 403
    assert client_for(make_user(role=Role.DEMO)).get("/api/operations").status_code == 403
    response = client_for(make_user(role=Role.OWNER)).get("/api/operations")
    assert response.status_code == 200
    names = [task["name"] for task in response.json()["tasks"]]
    assert names == sorted(settings.SCHEDULED_TASKS)


def _status(client, name):
    tasks = client.get("/api/operations").json()["tasks"]
    return next(task for task in tasks if task["name"] == name)


def test_a_task_that_never_succeeded_or_stopped_succeeding_is_overdue(make_user, client_for):
    owner = client_for(make_user(role=Role.OWNER))
    name = "operations.housekeeping"
    assert _status(owner, name)["overdue"] is True

    now = timezone.now()
    TaskRun.objects.create(name=name, started_at=now, finished_at=now, outcome=RunOutcome.OK)
    status = _status(owner, name)
    assert status["overdue"] is False
    assert status["runs_last_day"] == 1

    TaskRun.objects.all().delete()
    long_ago = now - timedelta(days=3)
    TaskRun.objects.create(name=name, started_at=long_ago, finished_at=long_ago, outcome="ok")
    TaskRun.objects.create(name=name, started_at=now, finished_at=now, outcome=RunOutcome.ERROR)
    status = _status(owner, name)
    assert status["overdue"] is True
    assert status["last_outcome"] == "error"
    assert status["failures_last_day"] == 1
