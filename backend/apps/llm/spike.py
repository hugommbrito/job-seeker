"""The gateway spike from the implementation plan (section 3.4), as a repeatable check.

Three things must work through LiteLLM's Anthropic-format endpoint, or the app moves to
LiteLLM's pass-through route with real model ids: structured output, prompt caching with a
non-zero cache read on the second call, and adaptive thinking with an explicit effort. Refusal
fallbacks are tried as well but do not decide anything: when the gateway rejects them, a refusal
is handled as a failure like any other (rule 8).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import anthropic
import pydantic

from apps.llm.gateway import FALLBACK_BETA


@dataclass(frozen=True)
class Check:
    name: str
    passed: bool
    detail: str
    # A failed gating check means the endpoint cannot be used as configured.
    gating: bool = True


class City(pydantic.BaseModel):
    city: str


# Long enough to pass every current model's minimum cacheable prefix, and byte-for-byte stable
# between the two calls, or the second could not read from the cache.
CACHED_PREFIX = "\n".join(
    f"Rubric line {number}: a requirement is met only when the posting quotes it verbatim."
    for number in range(1, 700)
)


def _text(response: Any) -> str:
    return next((block.text for block in response.content if block.type == "text"), "")


def _attempt(name: str, run: Callable[[], Check], gating: bool = True) -> Check:
    try:
        return run()
    except anthropic.APIStatusError as error:
        return Check(name, False, f"HTTP {error.status_code}", gating)
    except anthropic.APIConnectionError as error:
        return Check(name, False, type(error).__name__, gating)
    except pydantic.ValidationError:
        return Check(name, False, "answer did not match the schema", gating)


def run_spike(client: anthropic.Anthropic, model: str) -> list[Check]:
    def structured_output() -> Check:
        response = client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[
                {"role": "user", "content": "Which city is named here? 'The office is in Toronto.'"}
            ],
            output_config={
                "effort": "low",
                "format": {"type": "json_schema", "schema": anthropic.transform_schema(City)},
            },
        )
        answer = City.model_validate_json(_text(response))
        ok = response.stop_reason == "end_turn" and "toronto" in answer.city.lower()
        return Check("structured output", ok, f"stop_reason={response.stop_reason}")

    def caching() -> Check:
        reads = []
        for question in ("Reply with the word one.", "Reply with the word two."):
            response = client.messages.create(
                model=model,
                max_tokens=2000,
                system=[
                    {"type": "text", "text": CACHED_PREFIX, "cache_control": {"type": "ephemeral"}}
                ],
                messages=[{"role": "user", "content": question}],
                output_config={"effort": "low"},
            )
            reads.append(response.usage.cache_read_input_tokens or 0)
        return Check("prompt caching", reads[1] > 0, f"cache_read_input_tokens={reads}")

    def thinking() -> Check:
        response = client.messages.create(
            model=model,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            messages=[{"role": "user", "content": "Is 391 a prime number? Answer yes or no."}],
        )
        thought = any(block.type == "thinking" for block in response.content)
        return Check(
            "adaptive thinking with effort",
            response.stop_reason == "end_turn",
            f"stop_reason={response.stop_reason}, thinking block returned: {thought}",
        )

    def fallbacks() -> Check:
        response = client.beta.messages.create(
            model=model,
            max_tokens=2000,
            betas=[FALLBACK_BETA],
            fallbacks="default",
            output_config={"effort": "low"},
            messages=[{"role": "user", "content": "Reply with the word ok."}],
        )
        return Check(
            "refusal fallbacks (not gating)",
            response.stop_reason == "end_turn",
            f"accepted, stop_reason={response.stop_reason}",
            gating=False,
        )

    return [
        _attempt("structured output", structured_output),
        _attempt("prompt caching", caching),
        _attempt("adaptive thinking with effort", thinking),
        _attempt("refusal fallbacks (not gating)", fallbacks, gating=False),
    ]
