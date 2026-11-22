"""Management commands."""

from __future__ import annotations

import io
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import LoginThrottle, Role, Session, User
from apps.accounts.session_backend import SessionStore, hash_session_key
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db


def _create(monkeypatch, email, password=PASSWORD, **options):
    monkeypatch.setattr("sys.stdin", io.StringIO(password + "\n"))
    out = io.StringIO()
    call_command("create_user", email, password_stdin=True, stdout=out, **options)
    return out.getvalue()


def test_create_user_creates_a_member_by_default(monkeypatch):
    output = _create(monkeypatch, "New.Person@Example.test")
    user = User.objects.get()
    assert user.email == "new.person@example.test"
    assert user.role == Role.MEMBER
    assert user.check_password(PASSWORD)
    assert "example.test" not in output, "the email must not be echoed"


@pytest.mark.parametrize("role", Role.values)
def test_create_user_accepts_every_role(monkeypatch, role):
    _create(monkeypatch, "someone@example.test", role=role)
    assert User.objects.get().role == role


def test_create_user_refuses_a_weak_password(monkeypatch):
    with pytest.raises(CommandError):
        _create(monkeypatch, "someone@example.test", password="password")
    assert not User.objects.exists()


def test_create_user_refuses_a_duplicate_whatever_its_case(monkeypatch):
    _create(monkeypatch, "someone@example.test")
    with pytest.raises(CommandError, match="already exists"):
        _create(monkeypatch, "SOMEONE@example.test")
    assert User.objects.count() == 1


def test_create_user_refuses_a_malformed_email(monkeypatch):
    with pytest.raises(CommandError):
        _create(monkeypatch, "not-an-email")
    assert not User.objects.exists()


def test_create_user_takes_no_password_argument():
    with pytest.raises((CommandError, TypeError, SystemExit)):
        call_command("create_user", "someone@example.test", "--password", PASSWORD)


def test_the_database_refuses_an_unknown_role():
    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.bulk_create([User(email="x@example.test", role="admin", password="!")])


def test_clear_expired_removes_only_what_has_expired(settings):
    live, dead = SessionStore(), SessionStore()
    for store in (live, dead):
        store["k"] = 1
        store.save()
    Session.objects.filter(session_key=hash_session_key(dead.session_key)).update(
        expire_date=timezone.now() - timedelta(minutes=1)
    )
    now = timezone.now()
    LoginThrottle.objects.create(key="fresh", failures=1, window_start=now)
    LoginThrottle.objects.create(
        key="stale",
        failures=9,
        window_start=now - timedelta(seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS + 1),
    )

    call_command("clear_expired", stdout=io.StringIO())

    assert list(Session.objects.values_list("session_key", flat=True)) == [
        hash_session_key(live.session_key)
    ]
    assert list(LoginThrottle.objects.values_list("key", flat=True)) == ["fresh"]
