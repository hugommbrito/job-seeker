"""The profile and tracks the first-run wizard and the settings page edit."""

from __future__ import annotations

import logging

import pytest

from apps.profiles.models import Profile
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db


@pytest.fixture
def member(make_user):
    return make_user()


@pytest.fixture
def client(member, client_for):
    return client_for(member)


def _patch(client, body):
    return client.patch("/api/profile", data=body, content_type="application/json")


def test_defaults_before_the_wizard_and_reading_creates_nothing(client, member):
    profile = client.get("/api/profile").json()
    assert profile["timezone"] == "America/Toronto"
    assert profile["onboarded"] is False
    assert profile["home"] is None
    assert profile["hard"] == {
        "workplace_types": [],
        "locations": [],
        "salary_floor": None,
        "seniority": [],
        "employment_types": [],
        "max_commute_km": None,
    }
    assert profile["notify"]["quiet_hours"] == {"start": "22:00:00", "end": "08:00:00"}
    assert profile["notify"]["follow_up_after_days"] == 14
    with tenant_context(member.pk):
        assert not Profile.objects.exists()


def test_the_wizard_saves_each_part(client):
    assert (
        _patch(client, {"timezone": "America/Vancouver"}).json()["timezone"] == "America/Vancouver"
    )
    hard = {
        "workplace_types": ["remote", "hybrid"],
        "locations": ["Toronto"],
        "salary_floor": {"amount": "90000", "currency": "CAD", "period": "year"},
        "max_commute_km": 25,
    }
    saved = _patch(client, {"hard": hard}).json()
    assert saved["hard"]["salary_floor"] == {
        "amount": "90000",
        "currency": "CAD",
        "period": "year",
    }
    home = {"label": "Union Station", "latitude": "43.645200", "longitude": "-79.380600"}
    assert _patch(client, {"home": home}).json()["home"] == home
    notify = {"quiet_hours": {"start": "21:30", "end": "07:00"}, "follow_up_after_days": 10}
    assert _patch(client, {"notify": notify}).json()["notify"]["follow_up_after_days"] == 10
    done = _patch(client, {"onboarded": True}).json()
    assert done["onboarded"] is True
    # Each write kept the others.
    assert done["timezone"] == "America/Vancouver"
    assert done["hard"]["locations"] == ["Toronto"]
    assert _patch(client, {"home": None}).json()["home"] is None


@pytest.mark.parametrize(
    "body",
    [
        {"timezone": "Mars/Olympus"},
        {"hard": {"workplace_types": ["moon"]}},
        {"hard": {"invented_rule": True}},
        {"hard": {"salary_floor": {"amount": "-5"}}},
        {"hard": {"max_commute_km": 0}},
        {"notify": {"follow_up_after_days": 1}},
        {"home": {"latitude": "91", "longitude": "0"}},
    ],
)
def test_invalid_settings_are_refused(client, body):
    assert _patch(client, body).status_code == 422


def test_a_stored_value_that_no_longer_validates_falls_back_to_the_defaults(client, member, caplog):
    with tenant_context(member.pk):
        Profile.objects.create(
            hard={"workplace_types": ["teleport"]}, notify={"follow_up_after_days": 0}
        )
    with caplog.at_level(logging.WARNING, logger="apps.profiles.settings"):
        profile = client.get("/api/profile").json()
    assert profile["hard"]["workplace_types"] == []
    assert profile["notify"]["follow_up_after_days"] == 14
    assert "teleport" not in caplog.text, "the stored value is the user's data, not for the log"
    assert "HardFilters is invalid" in caplog.text


def test_tracks(client):
    created = client.post(
        "/api/tracks",
        data={
            "name": "Data analysis",
            "target_titles": ["Data Analyst", "BI Analyst"],
            "summary": "Reporting and dashboards",
            "filter_overrides": {"workplace_types": ["remote"]},
        },
        content_type="application/json",
    )
    assert created.status_code == 201
    track = created.json()
    assert track["filter_overrides"] == {
        "workplace_types": ["remote"],
        "locations": None,
        "seniority": None,
    }
    edited = client.patch(
        f"/api/tracks/{track['id']}", data={"active": False}, content_type="application/json"
    ).json()
    assert edited["active"] is False
    assert edited["name"] == "Data analysis"
    assert [t["name"] for t in client.get("/api/tracks").json()] == ["Data analysis"]
    assert client.delete(f"/api/tracks/{track['id']}").status_code == 204
    assert client.get("/api/tracks").json() == []


def test_bad_tracks_are_refused(client):
    for body in (
        {"name": ""},
        {"name": "x", "target_titles": [""]},
        {"name": "x", "filter_overrides": {"bogus": 1}},
    ):
        assert (
            client.post("/api/tracks", data=body, content_type="application/json").status_code
            == 422
        )


def test_another_users_tracks_are_out_of_reach(client, make_user, client_for):
    other = client_for(make_user())
    theirs = other.post(
        "/api/tracks", data={"name": "Theirs"}, content_type="application/json"
    ).json()
    assert (
        client.patch(
            f"/api/tracks/{theirs['id']}", data={"name": "x"}, content_type="application/json"
        ).status_code
        == 404
    )
    assert client.delete(f"/api/tracks/{theirs['id']}").status_code == 404
    assert client.get("/api/tracks").json() == []
