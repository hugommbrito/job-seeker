"""The demo tenant and the guest login: browse everything, change nothing, stay signed in."""

from __future__ import annotations

import io
from datetime import date

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client

from apps.accounts.models import Role, User
from apps.applications.models import Application
from apps.demo.persona import resolve_dates
from apps.documents.models import Document
from apps.notifications.models import Notification
from apps.profiles.models import Profile, Track
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db


def _seed():
    call_command("seed_demo", stdout=io.StringIO())
    return User.objects.get(role=Role.DEMO)


def test_relative_dates():
    today = date(2026, 11, 24)
    assert resolve_dates({"a": ["-1d", "+7d", "x"], "b": "-0d"}, today) == {
        "a": ["2026-11-23", "2026-12-01", "x"],
        "b": "2026-11-24",
    }


def test_seed_builds_the_persona_and_can_run_again():
    guest = _seed()
    _seed()
    with tenant_context(guest.pk):
        assert Application.objects.count() == 10
        assert Track.objects.count() == 2
        assert Document.objects.count() == 1
        assert Notification.objects.count() == 3
        profile = Profile.objects.get()
        assert profile.onboarded_at is not None
        assert profile.home_label.startswith("Union Station")
        overdue = Application.objects.get(company_name="Woodgrove Bank")
    assert overdue.decision_due_at < date.today()
    assert User.objects.filter(role=Role.DEMO).count() == 1


def test_seed_refuses_an_email_that_belongs_to_someone_real(make_user, settings):
    make_user(role=Role.MEMBER, email=settings.DEMO_EMAIL)
    with pytest.raises(CommandError, match="not the guest"):
        call_command("seed_demo", stdout=io.StringIO())


def test_the_seed_touches_no_one_else(make_user, client_for):
    member = make_user()
    _seed()
    assert client_for(member).get("/api/applications").json() == []


@pytest.fixture
def browser():
    client = Client(enforce_csrf_checks=True)
    client.get("/api/auth/csrf")
    return client


def _demo(client):
    return client.post("/api/auth/demo", headers={"X-CSRFToken": client.cookies["csrftoken"].value})


def test_the_guest_login_is_off_unless_enabled(browser, settings):
    settings.DEMO_LOGIN_ENABLED = False
    _seed()
    assert Client().get("/api/auth/options").json() == {"demo_login": False}
    assert _demo(browser).status_code == 404


def test_the_guest_browses_and_cannot_change_anything(browser, settings):
    settings.DEMO_LOGIN_ENABLED = True
    _seed()
    assert Client().get("/api/auth/options").json() == {"demo_login": True}
    signed_in = _demo(browser)
    assert signed_in.status_code == 200
    assert signed_in.json()["role"] == "demo"
    # A short session: nobody keeps the guest for days.
    assert browser.session.get_expiry_age() <= settings.DEMO_SESSION_SECONDS

    applications = browser.get("/api/applications").json()
    assert len(applications) == 10
    assert browser.get(f"/api/applications/{applications[0]['id']}").status_code == 200
    for path in ("/api/notifications", "/api/profile", "/api/tracks", "/api/captures"):
        assert browser.get(path).status_code == 200, path

    token = {"X-CSRFToken": browser.cookies["csrftoken"].value}
    refused = browser.post(
        "/api/applications",
        data={"company_name": "x", "role_title": "y"},
        content_type="application/json",
        headers=token,
    )
    assert refused.status_code == 403
    # Refused, not signed out.
    assert browser.get("/api/auth/me").json()["role"] == "demo"


def test_the_guest_login_needs_the_csrf_token_and_a_seeded_demo(settings):
    settings.DEMO_LOGIN_ENABLED = True
    client = Client(enforce_csrf_checks=True)
    client.get("/api/auth/csrf")
    assert client.post("/api/auth/demo").status_code == 403
    assert _demo(client).status_code == 503


def _fresh_browser():
    client = Client(enforce_csrf_checks=True)
    client.get("/api/auth/csrf")
    return client


def test_the_guest_login_is_limited_per_address(settings):
    settings.DEMO_LOGIN_ENABLED = True
    settings.DEMO_LOGINS_PER_ADDRESS = 2
    _seed()
    # A new browser each time, from the same address: what a script filling sessions does.
    assert _demo(_fresh_browser()).status_code == 200
    assert _demo(_fresh_browser()).status_code == 200
    limited = _demo(_fresh_browser())
    assert limited.status_code == 429
    assert int(limited["Retry-After"]) > 0
