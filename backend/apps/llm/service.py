"""Run one model task for one user and one entity, recording it whatever happens.

The order is what makes it safe and cheap:

1. In the user's tenant context: return the stored answer if this exact input was answered
   before (a retried task never pays twice), or stop if the account may not call the model or
   has reached its daily limit.
2. Outside any tenant context: the network call, because a tenant context is an open
   transaction.
3. In the tenant context again: store the outcome and the validated answer, before the caller
   acts on it.

Nothing here raises for a model failure. The caller gets an outcome and leaves the item marked
as not evaluated when it is not OK (project rule 8).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import cast

import pydantic
from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.llm import gateway as gateway_module
from apps.llm.gateway import GatewayRequest, GatewayResult
from apps.llm.models import BILLED, CallOutcome, LlmCall
from apps.llm.pricing import estimate
from apps.tenancy.context import tenant_context

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelTask:
    """What a task sends: its name in LLM_TASKS, a prompt version, a system prompt, a schema."""

    name: str
    prompt_version: str
    system: str
    output: type[pydantic.BaseModel]


@dataclass(frozen=True)
class TaskResult[OutputT: pydantic.BaseModel]:
    outcome: CallOutcome
    output: OutputT | None
    call_id: int | None
    # True when the stored answer was reused and no call was made.
    reused: bool = False


def input_hash(task: ModelTask, content: str) -> str:
    """Identifies an input: the prompt, the content and the schema asked for."""
    canonical = json.dumps(
        {
            "system": task.system,
            "content": content,
            "schema": task.output.model_json_schema(),
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _refusal(user_id: int) -> CallOutcome | None:
    """Why this user may not call the model now, or None. Runs in the user's tenant context."""
    role = User.objects.filter(pk=user_id).values_list("role", flat=True).first()
    if role is None or role == Role.DEMO:
        # The guest's data is synthetic and its budget is nobody's.
        return CallOutcome.DENIED
    since = timezone.now() - timedelta(days=1)
    recent = LlmCall.objects.filter(created_at__gte=since, outcome__in=BILLED).count()
    if recent >= settings.LLM_DAILY_CALLS_PER_USER:
        return CallOutcome.OVER_BUDGET
    return None


def _store(
    task: ModelTask,
    entity: tuple[str, int],
    digest: str,
    result: GatewayResult,
) -> LlmCall:
    usage = result.usage
    call = LlmCall(
        task=task.name,
        entity_type=entity[0],
        entity_id=entity[1],
        prompt_version=task.prompt_version,
        input_hash=digest,
        model=result.model,
        outcome=result.outcome,
        response=result.output.model_dump(mode="json") if result.output is not None else None,
        error=result.error,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=usage.cache_creation_input_tokens,
        cache_read_input_tokens=usage.cache_read_input_tokens,
        estimated_cost_usd=(
            estimate(
                result.model,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_write=usage.cache_creation_input_tokens,
                cache_read=usage.cache_read_input_tokens,
            )
            if result.outcome in BILLED
            else None
        ),
        latency_ms=result.latency_ms,
    )
    try:
        with transaction.atomic():
            call.save()
    except IntegrityError:
        # A concurrent run of the same task stored an answer for this input first. That answer
        # is the one used; this call is kept for its cost, without its answer.
        call.pk = None
        call.outcome = CallOutcome.DUPLICATE
        call.response = None
        call.save()
        return LlmCall.objects.get(
            task=task.name,
            entity_type=entity[0],
            entity_id=entity[1],
            prompt_version=task.prompt_version,
            input_hash=digest,
            outcome=CallOutcome.OK,
        )
    return call


def run_task[OutputT: pydantic.BaseModel](
    *,
    user_id: int,
    task: ModelTask,
    entity: tuple[str, int],
    content: str,
) -> TaskResult[OutputT]:
    """Run ``task`` over ``content`` for ``user_id``. Call it outside any tenant context."""
    digest = input_hash(task, content)
    output_type = cast(type[OutputT], task.output)

    with tenant_context(user_id):
        stored = LlmCall.objects.filter(
            task=task.name,
            entity_type=entity[0],
            entity_id=entity[1],
            prompt_version=task.prompt_version,
            input_hash=digest,
            outcome=CallOutcome.OK,
        ).first()
        if stored is not None and stored.response is not None:
            return TaskResult(
                CallOutcome.OK, output_type.model_validate(stored.response), stored.pk, reused=True
            )
        refusal = _refusal(user_id)
        if refusal is not None:
            call = _store(task, entity, digest, GatewayResult(refusal, error=refusal.value))
            return TaskResult(refusal, None, call.pk)

    gateway = gateway_module.get_gateway()
    if gateway is None:
        result = GatewayResult(CallOutcome.UNAVAILABLE, error="no_gateway")
    else:
        spec = settings.LLM_TASKS[task.name]
        result = gateway.run(
            GatewayRequest(
                model=spec["model"],
                system=task.system,
                content=content,
                output=task.output,
                effort=spec["effort"],
                max_tokens=spec["max_tokens"],
            )
        )

    with tenant_context(user_id):
        call = _store(task, entity, digest, result)
    # The task, the outcome and the reason only: never the content or the answer.
    logger.info("llm call %s: %s %s %s", call.pk, task.name, call.outcome, call.error)
    output = output_type.model_validate(call.response) if call.outcome == CallOutcome.OK else None
    return TaskResult(CallOutcome(call.outcome), output, call.pk)
