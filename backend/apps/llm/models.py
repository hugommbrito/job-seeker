"""Every model call, kept per user: what it cost, how it ended, and its validated answer.

The answer is stored before anything acts on it, keyed by (task, entity, prompt version, input
hash), so a retried task finds it and never pays for the same call twice. Content sent to the
model is not stored here; the entity it came from holds it.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.tenancy.models import TenantModel


class CallOutcome(models.TextChoices):
    OK = "ok", "Answered"
    REFUSED = "refused", "Refused by the model"
    TRUNCATED = "truncated", "Cut off at the token limit"
    INVALID = "invalid", "Answer did not match the schema"
    ERROR = "error", "Gateway or network error"
    # Answered, but a concurrent run of the same task had already stored an answer for this
    # input. Kept so that the call's cost is still counted.
    DUPLICATE = "duplicate", "Answered twice"
    # The three below never reached the model.
    UNAVAILABLE = "unavailable", "No gateway configured"
    OVER_BUDGET = "over_budget", "Daily limit reached"
    DENIED = "denied", "Not available to this account"


# Outcomes that reached the model and were billed, which is what the daily limit counts.
BILLED = (
    CallOutcome.OK,
    CallOutcome.REFUSED,
    CallOutcome.TRUNCATED,
    CallOutcome.INVALID,
    CallOutcome.DUPLICATE,
)


class LlmCall(TenantModel):
    task = models.CharField(max_length=32)
    entity_type = models.CharField(max_length=32)
    entity_id = models.BigIntegerField()
    prompt_version = models.CharField(max_length=32)
    input_hash = models.CharField(max_length=64)
    # The model the gateway reports, which may be an alias.
    model = models.CharField(max_length=100, blank=True, default="")
    outcome = models.CharField(max_length=16, choices=CallOutcome.choices)
    response = models.JSONField(null=True, blank=True)
    # A machine-readable reason for a failure (an HTTP status, a refusal category), never text
    # from the request or the answer.
    error = models.CharField(max_length=100, blank=True, default="")
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_creation_input_tokens = models.PositiveIntegerField(default=0)
    cache_read_input_tokens = models.PositiveIntegerField(default=0)
    estimated_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, null=True, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(outcome__in=CallOutcome.values), name="llm_call_outcome_valid"
            ),
            # One stored answer per input: what makes a retried task free.
            models.UniqueConstraint(
                fields=["user", "task", "entity_type", "entity_id", "prompt_version", "input_hash"],
                condition=models.Q(outcome="ok"),
                name="llm_call_one_answer_per_input",
            ),
        ]
        indexes: ClassVar = [models.Index(fields=["user", "created_at"])]

    def __str__(self) -> str:
        return f"{self.task} call {self.pk} ({self.outcome})"
