"""The Celery application: background work for the worker and the schedule for beat.

Tasks are idempotent and acknowledged late, so a task cut short by a restart or a deploy runs
again instead of being lost. Celery only schedules and spaces the work; anything that must
survive a restart (a source's breaker, a reminder already sent) lives in the database.
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("jobseeker")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
