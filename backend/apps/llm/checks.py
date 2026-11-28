"""The api must hold no model credential.

Only the worker calls the gateway; the api enqueues. A key in the api's environment would let a
bug in a request handler spend money or reach the model with a user's data, so the api refuses
to start with one, the same way it refuses a database role that could bypass row-level security.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from typing import Any

from django.apps import AppConfig
from django.conf import settings
from django.core.checks import CheckMessage, Error, Warning, register

MODEL_SECRETS = (
    "LLM_GATEWAY_KEY",
    "LLM_GATEWAY_KEY_FILE",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "LITELLM_MASTER_KEY",
)


def model_secret_problems(environ: dict[str, str], service: str, debug: bool) -> list[CheckMessage]:
    if service != "api":
        return []
    present = sorted(name for name in MODEL_SECRETS if environ.get(name))
    if not present:
        return []
    message = f"The api has model credentials in its environment: {', '.join(present)}."
    hint = "Give them to the worker only (docs/operations/deploy.md)."
    # A developer's .env may hold the worker's key; locally that is a warning, not a refusal.
    if debug:
        return [Warning(message, hint=hint, id="llm.W001")]
    return [Error(message, hint=hint, id="llm.E001")]


@register()
def check_no_model_key_in_api(
    *, app_configs: Sequence[AppConfig] | None, **kwargs: Any
) -> list[CheckMessage]:
    return model_secret_problems(dict(os.environ), settings.SERVICE_NAME, settings.DEBUG)
