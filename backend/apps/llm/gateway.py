"""The one place that talks to a model: the official Anthropic SDK, pointed at the LiteLLM gateway.

Each call asks for JSON matching a Pydantic model, with adaptive thinking and an explicit effort,
and no sampling parameters. The stop reason is read before the content: a refusal or a cut-off
answer is a failure with a reason, never a half-read result. The answer is validated here, after
that check, with the same model the schema came from.

No call made through this module carries tools, and its output is only ever data: posting and
email text is untrusted (project rule 6), and the worst an injected instruction can do is put a
wrong value in a field that code checks and a person reviews.

Only the worker calls this. The gateway key is read when a call is made, not at start-up, so a
missing key leaves model tasks "not evaluated" instead of stopping the process (rule 8).
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import anthropic
import pydantic
from django.conf import settings

from apps.llm.models import CallOutcome

logger = logging.getLogger(__name__)

# Server-side refusal fallbacks, sent only when LLM_REFUSAL_FALLBACKS is on: the gateway spike
# decides whether LiteLLM forwards them.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0


@dataclass(frozen=True)
class GatewayRequest:
    model: str
    system: str
    content: str
    output: type[pydantic.BaseModel]
    effort: str
    max_tokens: int


@dataclass(frozen=True)
class GatewayResult:
    outcome: CallOutcome
    output: pydantic.BaseModel | None = None
    model: str = ""
    usage: Usage = field(default_factory=Usage)
    latency_ms: int | None = None
    # Machine-readable only: a status, an exception class or a refusal category.
    error: str = ""


class Gateway(Protocol):
    def run(self, request: GatewayRequest) -> GatewayResult: ...


def gateway_key() -> str | None:
    """The worker's gateway key, from LLM_GATEWAY_KEY or the file LLM_GATEWAY_KEY_FILE names."""
    value = os.environ.get("LLM_GATEWAY_KEY", "").strip()
    if value:
        return value
    path = os.environ.get("LLM_GATEWAY_KEY_FILE", "").strip()
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip() or None
        except OSError:
            # A missing file is an unconfigured gateway, not a crash.
            return None
    return None


def _usage(raw: Any) -> Usage:
    return Usage(
        input_tokens=raw.input_tokens or 0,
        output_tokens=raw.output_tokens or 0,
        cache_creation_input_tokens=raw.cache_creation_input_tokens or 0,
        cache_read_input_tokens=raw.cache_read_input_tokens or 0,
    )


class AnthropicGateway:
    """Calls through LiteLLM's Anthropic-format endpoint with the official SDK."""

    def __init__(self, base_url: str, api_key: str, http_client: Any = None) -> None:
        self.client = anthropic.Anthropic(
            base_url=base_url,
            api_key=api_key,
            # The SDK's default is ten minutes with two retries; a hung call would hold a worker
            # for half an hour and look like nothing at all.
            timeout=settings.LLM_TIMEOUT_SECONDS,
            max_retries=1,
            http_client=http_client,
        )

    def _send(self, request: GatewayRequest) -> Any:
        system: Any = [
            # The stable part of the prompt, so it can be served from the cache.
            {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
        ]
        messages: Any = [{"role": "user", "content": request.content}]
        output_config: Any = {
            "effort": request.effort,
            "format": {"type": "json_schema", "schema": anthropic.transform_schema(request.output)},
        }
        if settings.LLM_REFUSAL_FALLBACKS:
            return self.client.beta.messages.create(
                model=request.model,
                max_tokens=request.max_tokens,
                system=system,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config=output_config,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        return self.client.messages.create(
            model=request.model,
            max_tokens=request.max_tokens,
            system=system,
            messages=messages,
            thinking={"type": "adaptive"},
            output_config=output_config,
        )

    def run(self, request: GatewayRequest) -> GatewayResult:
        started = time.monotonic()
        try:
            response = self._send(request)
        except anthropic.APITimeoutError:
            return GatewayResult(CallOutcome.ERROR, error="timeout")
        except anthropic.APIConnectionError:
            return GatewayResult(CallOutcome.ERROR, error="connection")
        except anthropic.APIStatusError as error:
            return GatewayResult(CallOutcome.ERROR, error=f"http_{error.status_code}")
        latency_ms = int((time.monotonic() - started) * 1000)
        model = response.model or request.model
        usage = _usage(response.usage)

        def finished(
            outcome: CallOutcome, *, error: str = "", output: pydantic.BaseModel | None = None
        ) -> GatewayResult:
            return GatewayResult(
                outcome, output=output, model=model, usage=usage, latency_ms=latency_ms, error=error
            )

        # The stop reason first: a declined or cut-off answer must not be read as an answer.
        if response.stop_reason == "refusal":
            category = getattr(response.stop_details, "category", None) or "unspecified"
            return finished(CallOutcome.REFUSED, error=f"refusal_{category}")
        if response.stop_reason == "max_tokens":
            return finished(CallOutcome.TRUNCATED, error="max_tokens")

        text = next((block.text for block in response.content if block.type == "text"), None)
        if text is None:
            return finished(CallOutcome.INVALID, error="no_text")
        try:
            output = request.output.model_validate_json(text)
        except pydantic.ValidationError:
            return finished(CallOutcome.INVALID, error="schema")
        return finished(CallOutcome.OK, output=output)


def get_gateway() -> Gateway | None:
    """The configured gateway, or None when there is no URL or no key."""
    key = gateway_key()
    if not settings.LLM_GATEWAY_URL or not key:
        return None
    return AnthropicGateway(settings.LLM_GATEWAY_URL, key)
