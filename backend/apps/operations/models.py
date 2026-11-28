"""Records of background work, so "is work getting done" has an answer.

A catalog table: it belongs to nobody and holds no user data. A run records counts and, when it
fails, the exception's class name only, because a message can quote what it failed on.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.tenancy.models import CatalogModel


class RunOutcome(models.TextChoices):
    RUNNING = "running", "Running"
    OK = "ok", "OK"
    ERROR = "error", "Error"


class TaskRun(CatalogModel):
    name = models.CharField(max_length=100)
    started_at = models.DateTimeField()
    finished_at = models.DateTimeField(null=True, blank=True)
    outcome = models.CharField(
        max_length=16, choices=RunOutcome.choices, default=RunOutcome.RUNNING
    )
    counts = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        indexes: ClassVar = [models.Index(fields=["name", "-started_at"])]

    def __str__(self) -> str:
        return f"{self.name} at {self.started_at:%Y-%m-%d %H:%M} ({self.outcome})"
