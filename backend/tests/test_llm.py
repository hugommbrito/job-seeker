"""The model gateway, with every network call replaced: the SDK talks to a mock transport."""

from __future__ import annotations

import io
import json
from datetime import timedelta
from decimal import Decimal

import anthropic
import httpx2
import pydantic
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.accounts.models import Role
from apps.llm import gateway as gateway_module
from apps.llm.checks import model_secret_problems
from apps.llm.gateway import (
    FALLBACK_BETA,
    AnthropicGateway,
    GatewayRequest,
    GatewayResult,
    Usage,
    gateway_key,
    get_gateway,
)
from apps.llm.models import CallOutcome, LlmCall
from apps.llm.pricing import estimate
from apps.llm.service import ModelTask, run_task
from apps.llm.spike import run_spike
from apps.tenancy.context import tenant_context
from tests.fakes import FakeGateway


class Answer(pydantic.BaseModel):
    city: str


TASK = ModelTask(name="extractor", prompt_version="test-v1", system="Find the city.", output=Answer)


def message(text='{"city": "Toronto"}', *, stop_reason="end_turn", content=None, **usage):
    return {
        "id": "msg_test",
        "type": "message",
        "role": "assistant",
        "model": "claude-opus-5-5",
        "content": content if content is not None else [{"type": "text", "text": text}],
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "stop_details": usage.pop("stop_details", None),
        "usage": {
            "input_tokens": 100,
            "output_tokens": 20,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
            **usage,
        },
    }


def mocked(handler) -> AnthropicGateway:
    client = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return AnthropicGateway("http://gateway.test", "test-key", http_client=client)


def request(**overrides) -> GatewayRequest:
    fields = {
        "model": "extractor",
        "system": "Find the city.",
        "content": "<posting>The office is in Toronto.</posting>",
        "output": Answer,
        "effort": "low",
        "max_tokens": 16000,
        **overrides,
    }
    return GatewayRequest(**fields)


# --- The gateway itself


def test_the_request_asks_for_what_the_plan_says():
    seen = []

    def handler(http_request):
        seen.append(http_request)
        return httpx2.Response(200, json=message())

    result = mocked(handler).run(request())
    assert result.outcome == CallOutcome.OK
    assert result.output == Answer(city="Toronto")
    assert result.usage == Usage(input_tokens=100, output_tokens=20)

    sent = seen[0]
    assert sent.url.path == "/v1/messages"
    # SDK 2.x sends the key as a bearer token, which LiteLLM accepts like x-api-key.
    assert "test-key" in (sent.headers.get("authorization", "") + sent.headers.get("x-api-key", ""))
    body = json.loads(sent.content)
    assert body["model"] == "extractor"
    assert body["thinking"] == {"type": "adaptive"}
    assert body["output_config"]["effort"] == "low"
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert body["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert body["messages"] == [
        {"role": "user", "content": "<posting>The office is in Toronto.</posting>"}
    ]
    # No sampling parameters, and nothing that would let the model act.
    for absent in ("temperature", "top_p", "top_k", "tools", "tool_choice"):
        assert absent not in body


@pytest.mark.parametrize(
    ("response", "outcome", "error"),
    [
        (
            message(
                "",
                stop_reason="refusal",
                content=[],
                stop_details={"type": "refusal", "category": "cyber"},
            ),
            CallOutcome.REFUSED,
            "refusal_cyber",
        ),
        (message('{"city": "Tor', stop_reason="max_tokens"), CallOutcome.TRUNCATED, "max_tokens"),
        (message('{"town": "Toronto"}'), CallOutcome.INVALID, "schema"),
        (message("not json at all"), CallOutcome.INVALID, "schema"),
        (
            message(content=[{"type": "thinking", "thinking": "", "signature": "x"}]),
            CallOutcome.INVALID,
            "no_text",
        ),
    ],
)
def test_the_stop_reason_is_read_before_the_answer(response, outcome, error):
    result = mocked(lambda _request: httpx2.Response(200, json=response)).run(request())
    assert result.outcome == outcome
    assert result.error == error
    assert result.output is None
    # A failed call was still billed, so its usage is kept.
    assert result.usage.input_tokens == 100


def test_errors_are_outcomes_not_exceptions():
    failing = mocked(lambda _request: httpx2.Response(500, json={"error": {"type": "api_error"}}))
    assert failing.run(request()).error == "http_500"

    def unreachable(_request):
        raise httpx2.ConnectError("refused")

    result = mocked(unreachable).run(request())
    assert result.outcome == CallOutcome.ERROR
    assert result.error == "connection"


def test_refusal_fallbacks_are_sent_only_when_switched_on(settings):
    seen = []

    def handler(http_request):
        seen.append(http_request)
        return httpx2.Response(200, json=message())

    mocked(handler).run(request())
    assert "fallbacks" not in json.loads(seen[-1].content)

    settings.LLM_REFUSAL_FALLBACKS = True
    mocked(handler).run(request())
    assert json.loads(seen[-1].content)["fallbacks"] == "default"
    assert FALLBACK_BETA in seen[-1].headers["anthropic-beta"]


def test_the_key_comes_from_the_environment_or_a_file(monkeypatch, tmp_path, settings):
    monkeypatch.delenv("LLM_GATEWAY_KEY", raising=False)
    monkeypatch.delenv("LLM_GATEWAY_KEY_FILE", raising=False)
    assert gateway_key() is None
    settings.LLM_GATEWAY_URL = "http://gateway.test"
    assert get_gateway() is None

    secret = tmp_path / "key"
    secret.write_text("from-a-file\n")
    monkeypatch.setenv("LLM_GATEWAY_KEY_FILE", str(secret))
    assert gateway_key() == "from-a-file"
    assert isinstance(get_gateway(), AnthropicGateway)

    # A mounted file that is not there is an unconfigured gateway, not a crash.
    monkeypatch.setenv("LLM_GATEWAY_KEY_FILE", str(tmp_path / "missing"))
    assert gateway_key() is None
    monkeypatch.setenv("LLM_GATEWAY_KEY", "from-the-environment")
    assert gateway_key() == "from-the-environment"
    settings.LLM_GATEWAY_URL = ""
    assert get_gateway() is None


def test_cost_estimate():
    cost = estimate(
        "claude-opus-5-5",
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_write=0,
        cache_read=0,
    )
    assert cost == Decimal("6.000000")
    # An alias is priced as the configured model.
    assert estimate(
        "extractor", input_tokens=0, output_tokens=0, cache_write=0, cache_read=1_000_000
    ) == Decimal("0.200000")


# --- Running a task for a user


@pytest.fixture
def fake(monkeypatch):
    fake = FakeGateway()
    monkeypatch.setattr(gateway_module, "get_gateway", lambda: fake)
    return fake


def ok(city="Toronto") -> GatewayResult:
    return GatewayResult(
        CallOutcome.OK,
        output=Answer(city=city),
        model="claude-opus-5-5",
        usage=Usage(1000, 100),
        latency_ms=5,
    )


def _run(user, content="The office is in Toronto.", entity=("capture", 1)):
    return run_task(user_id=user.pk, task=TASK, entity=entity, content=content)


@pytest.mark.django_db
def test_an_answer_is_stored_and_reused(make_user, fake):
    user = make_user()
    fake.results = [ok()]
    first = _run(user)
    assert first.outcome == CallOutcome.OK
    assert first.output == Answer(city="Toronto")
    assert not first.reused
    # The retry is free: no second call reaches the gateway.
    second = _run(user)
    assert second.reused
    assert second.output == Answer(city="Toronto")
    assert len(fake.requests) == 1
    assert fake.requests[0].effort == "low"
    with tenant_context(user.pk):
        call = LlmCall.objects.get()
    assert call.response == {"city": "Toronto"}
    assert call.estimated_cost_usd == Decimal("0.006000")
    assert call.prompt_version == "test-v1"


@pytest.mark.django_db
def test_a_different_input_is_a_new_call(make_user, fake):
    user = make_user()
    fake.results = [ok(), ok("Ottawa")]
    _run(user)
    assert _run(user, content="The office is in Ottawa.").output == Answer(city="Ottawa")
    assert len(fake.requests) == 2


@pytest.mark.django_db
def test_another_users_stored_answer_is_never_reused(make_user, fake):
    a, b = make_user(), make_user()
    fake.results = [ok(), ok()]
    _run(a)
    assert not _run(b).reused
    assert len(fake.requests) == 2


@pytest.mark.django_db
def test_a_failure_is_recorded_and_returned_not_raised(make_user, fake):
    user = make_user()
    fake.results = [
        GatewayResult(
            CallOutcome.REFUSED, model="claude-opus-5-5", usage=Usage(10, 0), error="refusal_cyber"
        )
    ]
    result = _run(user)
    assert result.outcome == CallOutcome.REFUSED
    assert result.output is None
    with tenant_context(user.pk):
        call = LlmCall.objects.get()
    assert call.error == "refusal_cyber"
    assert call.response is None


@pytest.mark.django_db
def test_no_gateway_leaves_the_work_not_evaluated(make_user, monkeypatch):
    monkeypatch.setattr(gateway_module, "get_gateway", lambda: None)
    user = make_user()
    result = _run(user)
    assert result.outcome == CallOutcome.UNAVAILABLE
    with tenant_context(user.pk):
        assert LlmCall.objects.get().outcome == CallOutcome.UNAVAILABLE


@pytest.mark.django_db
def test_the_demo_account_never_reaches_the_model(make_user, fake):
    result = _run(make_user(role=Role.DEMO))
    assert result.outcome == CallOutcome.DENIED
    assert fake.requests == []


@pytest.mark.django_db
def test_the_daily_limit(make_user, fake, settings):
    settings.LLM_DAILY_CALLS_PER_USER = 2
    user = make_user()
    fake.answer = lambda _request: ok()
    _run(user, content="one")
    _run(user, content="two")
    assert _run(user, content="three").outcome == CallOutcome.OVER_BUDGET
    assert len(fake.requests) == 2
    # Calls older than a day no longer count.
    with tenant_context(user.pk):
        LlmCall.objects.update(created_at=timezone.now() - timedelta(days=2))
    assert _run(user, content="three").outcome == CallOutcome.OK


@pytest.mark.django_db
def test_a_concurrent_duplicate_keeps_its_cost_and_the_first_answer(make_user, fake):
    user = make_user()

    # Simulates another run storing an answer between this run's lookup and its own store.
    def answer(_request):
        with tenant_context(user.pk):
            LlmCall.objects.create(
                task=TASK.name,
                entity_type="capture",
                entity_id=1,
                prompt_version=TASK.prompt_version,
                input_hash=_hash("The office is in Toronto."),
                outcome=CallOutcome.OK,
                response={"city": "First"},
            )
        return ok("Second")

    fake.answer = answer
    result = _run(user)
    assert result.output == Answer(city="First")
    with tenant_context(user.pk):
        outcomes = sorted(LlmCall.objects.values_list("outcome", flat=True))
    assert outcomes == [CallOutcome.DUPLICATE, CallOutcome.OK]


def _hash(content: str) -> str:
    from apps.llm.service import input_hash

    return input_hash(TASK, content)


# --- The api holds no model key


def test_the_api_refuses_to_start_with_a_model_key():
    assert model_secret_problems({}, "api", debug=False) == []
    found = model_secret_problems(
        {"LLM_GATEWAY_KEY": "x", "ANTHROPIC_API_KEY": "y"}, "api", debug=False
    )
    assert [problem.id for problem in found] == ["llm.E001"]
    assert "ANTHROPIC_API_KEY, LLM_GATEWAY_KEY" in found[0].msg
    assert model_secret_problems({"LLM_GATEWAY_KEY": "x"}, "worker", debug=False) == []
    assert [p.id for p in model_secret_problems({"LLM_GATEWAY_KEY": "x"}, "api", debug=True)] == [
        "llm.W001"
    ]


# --- The spike


def test_the_spike_passes_on_a_gateway_that_does_everything():
    calls = {"n": 0}

    def handler(http_request):
        body = json.loads(http_request.content)
        calls["n"] += 1
        if body.get("system"):
            # The second call with the long prefix reads it from the cache.
            read = 0 if calls["n"] == 2 else 4000
            return httpx2.Response(200, json=message("one", cache_read_input_tokens=read))
        if body.get("thinking"):
            return httpx2.Response(
                200,
                json=message(
                    content=[
                        {"type": "thinking", "thinking": "", "signature": "s"},
                        {"type": "text", "text": "yes"},
                    ]
                ),
            )
        return httpx2.Response(200, json=message())

    checks = run_spike(mocked(handler).client, "extractor")
    assert [(check.name, check.passed) for check in checks] == [
        ("structured output", True),
        ("prompt caching", True),
        ("adaptive thinking with effort", True),
        ("refusal fallbacks (not gating)", True),
    ]


def test_the_spike_reports_what_the_gateway_lacks():
    def handler(http_request):
        body = json.loads(http_request.content)
        if "fallbacks" in body:
            return httpx2.Response(400, json={"error": {"type": "invalid_request_error"}})
        return httpx2.Response(200, json=message())

    checks = {check.name: check for check in run_spike(mocked(handler).client, "extractor")}
    assert checks["structured output"].passed
    assert not checks["prompt caching"].passed
    assert checks["prompt caching"].detail == "cache_read_input_tokens=[0, 0]"
    assert not checks["refusal fallbacks (not gating)"].passed
    assert checks["refusal fallbacks (not gating)"].gating is False


def test_the_spike_command_needs_a_gateway(monkeypatch, settings):
    monkeypatch.delenv("LLM_GATEWAY_KEY", raising=False)
    monkeypatch.delenv("LLM_GATEWAY_KEY_FILE", raising=False)
    settings.LLM_GATEWAY_URL = ""
    with pytest.raises(CommandError, match="No gateway configured"):
        call_command("llm_spike", stdout=io.StringIO())
