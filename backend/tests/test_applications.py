"""The tracker's API: applications, stage and outcome, and the timeline."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest

from apps.applications.models import DECISION_NOTICE_DAYS, Application
from apps.profiles.clock import user_today
from apps.profiles.models import Profile
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def member(make_user):
    return make_user()


@pytest.fixture
def client(member, client_for):
    return client_for(member)


def _create(client, **fields):
    body = {"company_name": "Example Corp", "role_title": "Software Engineer", **fields}
    return client.post("/api/applications", data=body, content_type="application/json")


def _today(user) -> date:
    with tenant_context(user.pk):
        return user_today()


def test_create_with_defaults(client, member):
    response = _create(client)
    assert response.status_code == 201
    body = response.json()
    assert body["stage"] == "saved"
    assert body["outcome"] is None
    assert body["last_activity_at"] == _today(member).isoformat()
    assert [event["kind"] for event in body["events"]] == ["created"]
    assert body["events"][0]["editable"] is False


def test_a_past_application_keeps_its_own_dates(client):
    response = _create(
        client,
        stage="interviews",
        outcome="rejected",
        applied_at="2026-01-05",
        last_interview_at="2026-01-20",
        closed_on="2026-02-01",
    )
    body = response.json()
    assert body["outcome"] == "rejected"
    assert body["applied_at"] == "2026-01-05"
    assert body["last_interview_at"] == "2026-01-20"
    assert (
        body["decision_due_at"]
        == (date(2026, 1, 20) + timedelta(days=DECISION_NOTICE_DAYS)).isoformat()
    )
    timeline = [(event["kind"], event["occurred_on"]) for event in body["events"]]
    assert timeline == [
        ("closed", "2026-02-01"),
        ("interview", "2026-01-20"),
        ("created", "2026-01-05"),
    ]
    assert body["last_activity_at"] == "2026-02-01"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("company_name", ""),
        ("company_name", "   "),
        ("role_title", "x" * 301),
        ("posting_url", "javascript:alert(1)"),
        ("posting_url", "ftp://example.org/job"),
        ("stage", "hired"),
        ("outcome", "lost"),
    ],
)
def test_create_rejects_bad_input(client, field, value):
    assert _create(client, **{field: value}).status_code == 422
    assert not Application.objects.exists()


def test_text_is_stored_as_given_and_trimmed(client):
    body = _create(client, company_name="  <b>Acme</b> & Co  ").json()
    # Stored as text; the client renders it as text. Nothing is escaped or stripped here.
    assert body["company_name"] == "<b>Acme</b> & Co"


def test_list_filters_and_sorts(client):
    _create(client, company_name="Alpha", stage="applied", applied_at="2026-01-02")
    _create(client, company_name="Beta", stage="interviews", applied_at="2026-01-09")
    _create(client, company_name="Gamma", outcome="ghosted")
    _create(client, company_name="Delta", role_title="Data Analyst")

    def names(query: str) -> list[str]:
        return [row["company_name"] for row in client.get(f"/api/applications?{query}").json()]

    assert names("sort=company") == ["Alpha", "Beta", "Delta", "Gamma"]
    assert names("status=open&sort=company") == ["Alpha", "Beta", "Delta"]
    assert names("status=closed") == ["Gamma"]
    assert names("stage=applied&stage=interviews&sort=company") == ["Alpha", "Beta"]
    assert names("q=analyst") == ["Delta"]
    assert names("q=GAM") == ["Gamma"]
    # Applications without the date sort last.
    by_applied = names("sort=applied")
    assert by_applied[:2] == ["Beta", "Alpha"]
    assert set(by_applied[2:]) == {"Delta", "Gamma"}
    assert client.get("/api/applications?status=everything").status_code == 422


def test_moving_records_the_change_and_dates_the_application(client, member):
    application = _create(client).json()
    response = client.post(
        f"/api/applications/{application['id']}/stage",
        data={"stage": "applied"},
        content_type="application/json",
    )
    body = response.json()
    assert body["stage"] == "applied"
    assert body["applied_at"] == _today(member).isoformat()
    change = body["events"][0]
    assert change["kind"] == "stage_changed"
    assert change["payload"] == {"from": "saved", "to": "applied"}

    # Moving to the same stage records nothing.
    again = client.post(
        f"/api/applications/{application['id']}/stage",
        data={"stage": "applied"},
        content_type="application/json",
    ).json()
    assert len(again["events"]) == len(body["events"])


def test_closing_and_reopening(client):
    application = _create(client, stage="interviews").json()
    closed = client.post(
        f"/api/applications/{application['id']}/close",
        data={"outcome": "withdrawn"},
        content_type="application/json",
    ).json()
    assert closed["outcome"] == "withdrawn"
    assert closed["closed_at"] is not None
    # The stage reached is kept: it is what the funnel will count.
    assert closed["stage"] == "interviews"

    reopened = client.post(f"/api/applications/{application['id']}/reopen").json()
    assert reopened["outcome"] is None
    assert reopened["closed_at"] is None
    assert [event["kind"] for event in reopened["events"]][:2] == ["reopened", "closed"]


def test_interviews_drive_the_decision_clock(client):
    application = _create(client, stage="interviews").json()
    url = f"/api/applications/{application['id']}/events"
    first = client.post(
        url,
        data={"kind": "interview", "occurred_on": "2026-03-02"},
        content_type="application/json",
    )
    assert first.status_code == 201
    client.post(
        url,
        data={"kind": "interview", "occurred_on": "2026-03-10"},
        content_type="application/json",
    )
    detail = client.get(f"/api/applications/{application['id']}").json()
    assert detail["last_interview_at"] == "2026-03-10"
    assert detail["decision_due_at"] == "2026-04-24"

    # Correcting the later interview's date moves the clock with it.
    later = next(e for e in detail["events"] if e["occurred_on"] == "2026-03-10")
    edited = client.patch(
        f"{url}/{later['id']}", data={"occurred_on": "2026-03-01"}, content_type="application/json"
    )
    assert edited.status_code == 200
    detail = client.get(f"/api/applications/{application['id']}").json()
    assert detail["last_interview_at"] == "2026-03-02"

    # Deleting the last interview stops the clock.
    for event in detail["events"]:
        if event["kind"] == "interview":
            assert client.delete(f"{url}/{event['id']}").status_code == 204
    detail = client.get(f"/api/applications/{application['id']}").json()
    assert detail["last_interview_at"] is None
    assert detail["decision_due_at"] is None


def test_notes_are_activity(client, member):
    application = _create(client).json()
    response = client.post(
        f"/api/applications/{application['id']}/events",
        data={
            "kind": "note",
            "text": "Followed up with the recruiter",
            "occurred_on": "2027-01-04",
        },
        content_type="application/json",
    )
    assert response.json()["text"] == "Followed up with the recruiter"
    detail = client.get(f"/api/applications/{application['id']}").json()
    assert detail["last_activity_at"] == "2027-01-04"


def test_recorded_events_cannot_be_edited_or_added_by_hand(client):
    application = _create(client).json()
    created = application["events"][0]
    url = f"/api/applications/{application['id']}/events"
    assert (
        client.patch(f"{url}/{created['id']}", data={"text": "x"}, content_type="application/json")
    ).status_code == 409
    assert client.delete(f"{url}/{created['id']}").status_code == 409
    assert (
        client.post(url, data={"kind": "stage_changed"}, content_type="application/json")
    ).status_code == 422


def test_update_fields(client):
    application = _create(client, posting_url="https://example.org/job").json()
    url = f"/api/applications/{application['id']}"
    response = client.patch(
        url,
        data={
            "next_action": "Send the portfolio",
            "next_action_due": "2026-05-01",
            "posting_url": "",
        },
        content_type="application/json",
    )
    body = response.json()
    assert body["next_action"] == "Send the portfolio"
    assert body["next_action_due"] == "2026-05-01"
    assert body["posting_url"] == ""
    cleared = client.patch(url, data={"next_action_due": None}, content_type="application/json")
    assert cleared.json()["next_action_due"] is None
    refused = client.patch(url, data={"company_name": None}, content_type="application/json")
    assert refused.status_code == 422


def test_delete_removes_the_timeline_too(client, member):
    application = _create(client).json()
    assert client.delete(f"/api/applications/{application['id']}").status_code == 204
    assert client.get(f"/api/applications/{application['id']}").status_code == 404
    with tenant_context(member.pk):
        assert not Application.objects.exists()


def test_another_users_application_is_not_found(client, make_user, client_for):
    other = client_for(make_user())
    theirs = _create(other).json()
    event = theirs["events"][0]
    base = f"/api/applications/{theirs['id']}"
    assert client.get(base).status_code == 404
    assert (
        client.patch(base, data={"notes": "x"}, content_type="application/json").status_code == 404
    )
    assert client.delete(base).status_code == 404
    for action, body in (("stage", {"stage": "offer"}), ("close", {"outcome": "rejected"})):
        response = client.post(f"{base}/{action}", data=body, content_type="application/json")
        assert response.status_code == 404
    assert client.post(f"{base}/reopen").status_code == 404
    note = {"kind": "note", "text": "x"}
    assert (
        client.post(f"{base}/events", data=note, content_type="application/json").status_code == 404
    )
    assert client.delete(f"{base}/events/{event['id']}").status_code == 404
    # Untouched.
    assert other.get(base).json()["events"] == theirs["events"]


def test_an_event_is_found_only_under_its_own_application(client):
    first, second = _create(client).json(), _create(client).json()
    event = first["events"][0]
    assert (
        client.delete(f"/api/applications/{second['id']}/events/{event['id']}").status_code == 404
    )


def test_today_is_the_users_date_not_the_servers(make_user):
    user = make_user()
    late_evening_in_toronto = datetime(2026, 3, 3, 3, 30, tzinfo=UTC)
    with tenant_context(user.pk):
        assert user_today(late_evening_in_toronto) == date(2026, 3, 2)
        Profile.objects.create(timezone="Asia/Tokyo")
        assert user_today(late_evening_in_toronto) == date(2026, 3, 3)
        Profile.objects.update(timezone="Not/AZone")
        # A bad stored value falls back to the default instead of failing every request.
        assert user_today(late_evening_in_toronto) == date(2026, 3, 2)
