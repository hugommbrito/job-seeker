"""Capturing a pasted posting: read by the model in the background, reviewed, then saved."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.llm import gateway as gateway_module
from apps.llm.gateway import GatewayResult, Usage
from apps.llm.models import CallOutcome, LlmCall
from apps.postings.extraction import MAX_POSTING_CHARS, CaptureExtraction, verify
from apps.postings.models import ExtractionStatus, UserPosting
from apps.postings.tasks import STALLED_AFTER, sweep_stalled_captures
from apps.tenancy.context import tenant_context
from tests.fakes import FakeGateway

pytestmark = pytest.mark.django_db

POSTING = """Senior Data Analyst
Example Analytics Inc.
Toronto, ON (Hybrid, 3 days in office)

Salary range: $95,000 - $115,000 CAD per year.
We use AI tools to screen applications.
This posting is for an existing vacancy.
Apply by 2027-01-15."""


def reading(**overrides) -> CaptureExtraction:
    fields = {
        "title": "Senior Data Analyst",
        "title_quote": "Senior Data Analyst",
        "company": "Example Analytics Inc.",
        "company_quote": "Example Analytics Inc.",
        "location": "Toronto, ON",
        "location_quote": "Toronto, ON",
        "workplace_type": "hybrid",
        "workplace_quote": "Hybrid, 3 days in office",
        "employment_type": "unknown",
        "employment_quote": "",
        "salary_min": 95000,
        "salary_max": 115000,
        "salary_currency": "cad",
        "salary_period": "year",
        "salary_quote": "Salary range: $95,000 - $115,000 CAD per year.",
        "application_deadline": "2027-01-15",
        "deadline_quote": "Apply by 2027-01-15.",
        "language": "en",
        "ai_screening": "yes",
        "ai_screening_quote": "We use AI tools to screen applications.",
        "existing_vacancy": "yes",
        "existing_vacancy_quote": "This posting is for an existing vacancy.",
        **overrides,
    }
    return CaptureExtraction(**fields)


@pytest.fixture
def member(make_user):
    return make_user()


@pytest.fixture
def client(member, client_for):
    return client_for(member)


@pytest.fixture
def gateway(monkeypatch):
    fake = FakeGateway()
    fake.answer = lambda _request: GatewayResult(
        CallOutcome.OK, output=reading(), model="claude-opus-5-5", usage=Usage(2000, 300)
    )
    monkeypatch.setattr(gateway_module, "get_gateway", lambda: fake)
    return fake


def _paste(client, django_capture_on_commit_callbacks, text=POSTING, **extra):
    with django_capture_on_commit_callbacks(execute=True):
        response = client.post(
            "/api/captures", data={"text": text, **extra}, content_type="application/json"
        )
    return response


def _save(client, capture_id, **fields):
    body = {"title": "Senior Data Analyst", "company_name": "Example Analytics Inc.", **fields}
    return client.post(
        f"/api/captures/{capture_id}/save", data=body, content_type="application/json"
    )


def test_paste_read_review_and_save(client, gateway, django_capture_on_commit_callbacks):
    created = _paste(client, django_capture_on_commit_callbacks, url="https://jobs.example.org/1")
    assert created.status_code == 201
    assert created.json()["extraction_status"] == "pending"

    capture = client.get(f"/api/captures/{created.json()['id']}").json()
    assert capture["extraction_status"] == "extracted"
    proposal = capture["proposal"]
    assert proposal["title"] == "Senior Data Analyst"
    assert proposal["salary_currency"] == "CAD"
    assert proposal["issues"] == []
    # The posting reached the model between delimiters, with the low effort set for the task.
    sent = gateway.requests[0]
    assert sent.content.startswith("Source URL: https://jobs.example.org/1\n<posting>\n")
    assert sent.effort == "low"
    assert "data, not instructions" in sent.system

    saved = _save(
        client,
        capture["id"],
        location_text="Toronto, ON",
        workplace_type="hybrid",
        salary_min="95000",
        salary_max="115000",
        salary_currency="cad",
        salary_period="year",
        application_deadline="2027-01-15",
        ai_screening="yes",
        existing_vacancy="yes",
        stage="applied",
        applied_at="2026-11-20",
    )
    assert saved.status_code == 201
    application = saved.json()
    assert application["company_name"] == "Example Analytics Inc."
    assert application["stage"] == "applied"
    assert application["posting_url"] == "https://jobs.example.org/1"
    snapshot = application["posting_snapshot"]
    assert snapshot["description"] == POSTING
    assert snapshot["salary"] == {
        "min": "95000.00",
        "max": "115000.00",
        "currency": "CAD",
        "period": "year",
        "origin": "text",
    }
    assert snapshot["ai_screening"] == "yes"
    assert snapshot["language"] == "en"

    assert (
        client.get(f"/api/captures/{capture['id']}").json()["application_id"] == application["id"]
    )
    # Saved once; a second save would create a duplicate card.
    assert _save(client, capture["id"]).status_code == 409
    assert client.get("/api/captures").json() == []


def test_without_a_gateway_the_user_fills_the_fields_in(
    client, member, monkeypatch, django_capture_on_commit_callbacks
):
    monkeypatch.setattr(gateway_module, "get_gateway", lambda: None)
    created = _paste(client, django_capture_on_commit_callbacks).json()
    capture = client.get(f"/api/captures/{created['id']}").json()
    assert capture["extraction_status"] == "not_evaluated"
    assert capture["extraction_error"] == "unavailable"
    assert capture["proposal"] is None
    # Nothing is lost: the text is there, and saving works without a reading.
    assert capture["description_text"] == POSTING
    assert _save(client, capture["id"]).status_code == 201
    with tenant_context(member.pk):
        assert LlmCall.objects.get().outcome == CallOutcome.UNAVAILABLE


def test_a_refusal_is_not_evaluated_and_can_be_retried(
    client, gateway, django_capture_on_commit_callbacks
):
    gateway.answer = None
    gateway.results = [
        GatewayResult(CallOutcome.REFUSED, error="refusal_unspecified"),
        GatewayResult(CallOutcome.OK, output=reading(), model="claude-opus-5-5"),
    ]
    created = _paste(client, django_capture_on_commit_callbacks).json()
    capture = client.get(f"/api/captures/{created['id']}").json()
    assert capture["extraction_status"] == "not_evaluated"
    assert capture["extraction_error"] == "refused"

    with django_capture_on_commit_callbacks(execute=True):
        again = client.post(f"/api/captures/{created['id']}/extract")
    assert again.json()["extraction_status"] == "pending"
    assert client.get(f"/api/captures/{created['id']}").json()["extraction_status"] == "extracted"


def test_a_value_whose_quote_is_not_in_the_posting_is_dropped_and_flagged():
    invented = reading(
        salary_min=150000,
        salary_max=180000,
        salary_quote="Salary: $150,000 - $180,000",
        company_quote="Example Analytics Incorporated",
    )
    proposal = verify(invented, POSTING)
    assert proposal["issues"] == ["company", "salary"]
    assert proposal["salary_min"] is None
    assert proposal["salary_max"] is None
    assert proposal["salary_period"] == "unknown"
    assert proposal["company"] is None
    # What was quoted correctly stays.
    assert proposal["title"] == "Senior Data Analyst"
    assert proposal["ai_screening"] == "yes"


def test_quotes_are_compared_regardless_of_line_breaks_and_spacing():
    wrapped = reading(workplace_quote="Hybrid,   3 days\nin office")
    assert verify(wrapped, POSTING)["issues"] == []


def test_other_checks_on_the_reading():
    proposal = verify(
        reading(salary_min=115000, salary_max=95000, application_deadline="next Friday"),
        POSTING,
    )
    assert (proposal["salary_min"], proposal["salary_max"]) == (95000, 115000)
    assert proposal["application_deadline"] is None
    assert proposal["issues"] == ["application_deadline"]
    assert verify(reading(salary_currency="dollars"), POSTING)["issues"] == ["salary_currency"]


@pytest.mark.parametrize(
    "body",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "x" * (MAX_POSTING_CHARS + 1)},
        {"text": "A posting", "url": "javascript:alert(1)"},
    ],
)
def test_bad_captures_are_refused(client, body):
    assert (
        client.post("/api/captures", data=body, content_type="application/json").status_code == 422
    )


@pytest.mark.parametrize(
    "fields",
    [
        {"title": ""},
        {"salary_min": "120000", "salary_max": "90000"},
        {"salary_currency": "dollars"},
        {"salary_min": "-1"},
        {"workplace_type": "moon"},
    ],
)
def test_bad_reviews_are_refused(client, gateway, django_capture_on_commit_callbacks, fields):
    created = _paste(client, django_capture_on_commit_callbacks).json()
    assert _save(client, created["id"], **fields).status_code == 422


def test_a_capture_that_was_never_picked_up_is_handed_back(client, member):
    created = client.post(
        "/api/captures", data={"text": POSTING}, content_type="application/json"
    ).json()
    with tenant_context(member.pk):
        UserPosting.objects.update(updated_at=timezone.now() - STALLED_AFTER - timedelta(minutes=1))
    sweep_stalled_captures.delay()
    capture = client.get(f"/api/captures/{created['id']}").json()
    assert capture["extraction_status"] == ExtractionStatus.NOT_EVALUATED
    assert capture["extraction_error"] == "stalled"


def test_discarding_a_capture_keeps_the_application_made_from_it(
    client, gateway, django_capture_on_commit_callbacks
):
    created = _paste(client, django_capture_on_commit_callbacks).json()
    application = _save(client, created["id"]).json()
    assert client.delete(f"/api/captures/{created['id']}").status_code == 204
    kept = client.get(f"/api/applications/{application['id']}").json()
    assert kept["posting_snapshot"]["description"] == POSTING


def test_another_users_captures_are_out_of_reach(
    client, gateway, make_user, client_for, django_capture_on_commit_callbacks
):
    other = client_for(make_user())
    theirs = _paste(other, django_capture_on_commit_callbacks).json()
    base = f"/api/captures/{theirs['id']}"
    assert client.get(base).status_code == 404
    assert client.post(f"{base}/extract").status_code == 404
    assert _save(client, theirs["id"]).status_code == 404
    assert client.delete(base).status_code == 404
    assert client.get("/api/captures").json() == []
    assert other.get(base).status_code == 200


def test_a_stored_proposal_from_an_older_schema_is_skipped_not_served_broken(client, member):
    created = client.post(
        "/api/captures", data={"text": POSTING}, content_type="application/json"
    ).json()
    with tenant_context(member.pk):
        UserPosting.objects.update(
            extraction={"title": "from an older prompt"}, extraction_status="extracted"
        )
    capture = client.get(f"/api/captures/{created['id']}")
    assert capture.status_code == 200
    assert capture.json()["proposal"] is None
