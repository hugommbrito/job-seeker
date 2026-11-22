"""Signing in and out through the API, as a browser would."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.contrib.auth.hashers import identify_hasher
from django.test import Client, RequestFactory

from apps.accounts import throttle
from apps.accounts.models import LoginThrottle, Role, Session, User
from apps.accounts.session_backend import hash_session_key
from tests.conftest import PASSWORD

pytestmark = pytest.mark.django_db

EMAIL = "person@example.test"


@pytest.fixture
def user() -> User:
    # Through the real path, so the password is hashed by the configured hasher.
    return User.objects.create_user(email=EMAIL, password=PASSWORD, role=Role.MEMBER)


@pytest.fixture
def browser() -> Client:
    """A client that enforces CSRF like a browser-facing server does, with the cookie set."""
    client = Client(enforce_csrf_checks=True)
    assert client.get("/api/auth/csrf").status_code == 204
    return client


def _post(client: Client, path: str, data: dict | None = None, **extra):
    return client.post(
        path,
        data=data or {},
        content_type="application/json",
        headers={"X-CSRFToken": client.cookies["csrftoken"].value},
        **extra,
    )


def _login(client: Client, email: str = EMAIL, password: str = PASSWORD, **extra):
    return _post(client, "/api/auth/login", {"email": email, "password": password}, **extra)


def test_passwords_are_hashed_with_argon2(user):
    assert identify_hasher(user.password).algorithm == "argon2"


def test_sign_in_returns_the_user_and_sets_a_locked_down_session_cookie(user, browser):
    response = _login(browser)
    assert response.status_code == 200
    assert response.json() == {"email": EMAIL, "role": "member"}
    cookie = response.cookies["sessionid"]
    assert cookie["httponly"]
    assert cookie["secure"]
    assert cookie["samesite"] == "Lax"
    assert browser.get("/api/auth/me").json() == {"email": EMAIL, "role": "member"}


def test_the_email_is_not_case_sensitive(user, browser):
    assert _login(browser, email="  Person@Example.TEST ").status_code == 200


def test_a_wrong_password_and_an_unknown_email_get_the_same_answer(user, browser):
    wrong_password = _login(browser, password="not the password")
    unknown_email = _login(browser, email="nobody@example.test")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert "sessionid" not in browser.cookies


def test_sign_in_without_the_csrf_token_is_refused(user):
    client = Client(enforce_csrf_checks=True)
    client.get("/api/auth/csrf")
    response = client.post(
        "/api/auth/login",
        data={"email": EMAIL, "password": PASSWORD},
        content_type="application/json",
    )
    assert response.status_code == 403
    assert "sessionid" not in client.cookies


def test_sign_out_ends_the_session_and_needs_the_csrf_token(user, browser):
    _login(browser)
    without_token = browser.post("/api/auth/logout", content_type="application/json")
    assert without_token.status_code == 403
    assert browser.get("/api/auth/me").status_code == 200

    assert _post(browser, "/api/auth/logout").status_code == 204
    assert browser.get("/api/auth/me").status_code == 401
    assert not Session.objects.exists()


def test_who_am_i_needs_a_session():
    assert Client().get("/api/auth/me").status_code == 401


def test_a_made_up_session_cookie_is_not_a_session(user):
    client = Client()
    client.cookies["sessionid"] = "a" * 32
    assert client.get("/api/auth/me").status_code == 401


def test_the_session_table_holds_a_hash_and_not_the_key(user, browser):
    _login(browser)
    key = browser.cookies["sessionid"].value
    stored = list(Session.objects.values_list("session_key", flat=True))
    assert stored == [hash_session_key(key)]
    assert key not in stored


def test_a_stolen_table_row_cannot_be_used_as_a_cookie(user, browser):
    _login(browser)
    stolen = Session.objects.get().session_key
    thief = Client()
    thief.cookies["sessionid"] = stolen
    assert thief.get("/api/auth/me").status_code == 401


def test_signing_in_rotates_the_session_key(user, browser):
    browser.get("/api/auth/me")
    _login(browser)
    first = browser.cookies["sessionid"].value
    _post(browser, "/api/auth/logout")
    _login(browser)
    assert browser.cookies["sessionid"].value != first


def test_there_is_no_sign_up_route(browser):
    for path in ("/api/auth/register", "/api/auth/signup", "/api/users"):
        payload = {"email": "new@example.test", "password": PASSWORD}
        assert _post(browser, path, payload).status_code == 404
    assert not User.objects.exists()


# --- Throttling


def test_repeated_failures_lock_the_pair_out_even_for_the_right_password(user, browser, settings):
    for _ in range(settings.LOGIN_MAX_FAILURES_PER_EMAIL_AND_IP):
        assert _login(browser, password="wrong").status_code == 401
    locked = _login(browser)
    assert locked.status_code == 429
    assert int(locked["Retry-After"]) > 0
    assert "sessionid" not in browser.cookies


def test_a_lockout_from_one_address_does_not_lock_out_another(user, browser, settings):
    for _ in range(settings.LOGIN_MAX_FAILURES_PER_EMAIL_AND_IP):
        _login(browser, password="wrong", REMOTE_ADDR="203.0.113.7")
    assert _login(browser, REMOTE_ADDR="203.0.113.7").status_code == 429
    assert _login(browser, REMOTE_ADDR="203.0.113.8").status_code == 200


def test_guesses_spread_over_many_addresses_still_hit_the_per_email_limit(user, browser, settings):
    for index in range(settings.LOGIN_MAX_FAILURES_PER_EMAIL):
        _login(browser, password="wrong", REMOTE_ADDR=f"198.51.100.{index}")
    assert _login(browser, REMOTE_ADDR="198.51.100.250").status_code == 429


def test_one_address_trying_many_emails_hits_the_per_address_limit(user, browser, settings):
    for index in range(settings.LOGIN_MAX_FAILURES_PER_IP):
        _login(browser, email=f"guess{index}@example.test", password="wrong")
    assert _login(browser).status_code == 429


def test_the_lockout_ends_with_the_window(user, browser, settings):
    for _ in range(settings.LOGIN_MAX_FAILURES_PER_EMAIL_AND_IP):
        _login(browser, password="wrong")
    assert _login(browser).status_code == 429
    for row in LoginThrottle.objects.all():
        row.window_start -= timedelta(seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS + 1)
        row.save()
    assert _login(browser).status_code == 200


def test_a_success_forgives_earlier_typos(user, browser, settings):
    limit = settings.LOGIN_MAX_FAILURES_PER_EMAIL_AND_IP
    for _ in range(limit - 1):
        _login(browser, password="wrong")
    assert _login(browser).status_code == 200
    _post(browser, "/api/auth/logout")
    for _ in range(limit - 1):
        assert _login(browser, password="wrong").status_code == 401
    assert _login(browser).status_code == 200


def test_the_throttle_table_stores_neither_emails_nor_addresses(user, browser):
    _login(browser, password="wrong", REMOTE_ADDR="203.0.113.7")
    keys = list(LoginThrottle.objects.values_list("key", flat=True))
    assert len(keys) == 3
    for key in keys:
        assert EMAIL not in key
        assert "203.0.113.7" not in key
        assert len(key) == 64


def test_finished_windows_are_cleared(user, browser, settings):
    _login(browser, password="wrong")
    assert throttle.clear_expired() == 0
    LoginThrottle.objects.update(
        window_start=LoginThrottle.objects.first().window_start
        - timedelta(seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS + 1)
    )
    assert throttle.clear_expired() == 3


def _request(remote: str, forwarded: str | None = None):
    headers = {"X-Forwarded-For": forwarded} if forwarded else {}
    return RequestFactory().get("/", REMOTE_ADDR=remote, headers=headers)


def test_forwarded_for_is_ignored_without_a_trusted_proxy(settings):
    settings.TRUSTED_PROXY_COUNT = 0
    assert throttle.client_address(_request("10.0.0.1", "1.2.3.4")) == "10.0.0.1"


def test_forwarded_for_is_read_from_the_right_by_the_number_of_trusted_proxies(settings):
    # The leftmost entries are whatever the client chose to send.
    settings.TRUSTED_PROXY_COUNT = 1
    assert throttle.client_address(_request("10.0.0.1", "6.6.6.6, 203.0.113.9")) == "203.0.113.9"
    settings.TRUSTED_PROXY_COUNT = 2
    assert (
        throttle.client_address(_request("10.0.0.1", "6.6.6.6, 203.0.113.9, 10.0.0.2"))
        == "203.0.113.9"
    )
    # Fewer entries than proxies means the header did not come through them.
    assert throttle.client_address(_request("10.0.0.1", "203.0.113.9")) == "10.0.0.1"
