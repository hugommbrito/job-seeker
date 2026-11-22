"""Sign-in throttling: a bounded number of failed attempts per time window.

Three counters are kept for every failure, each with its own limit (see settings): the email and
address together, the email alone, and the address alone. A request is refused while any of the
three is over its limit. Only failures count, and a success clears the pair counter, so someone
who mistypes once is not punished for it later.
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from django.utils.crypto import salted_hmac

from apps.accounts.models import LoginThrottle, normalise_email


def client_address(request: HttpRequest) -> str:
    """Return the address the request came from, as seen by the outermost trusted proxy.

    X-Forwarded-For is written by whoever sends the request, so only the entries appended by
    our own proxies can be believed: with N trusted proxies, that is the Nth from the right.
    """
    remote: str = request.META.get("REMOTE_ADDR", "")
    proxies = settings.TRUSTED_PROXY_COUNT
    if proxies <= 0:
        return remote
    forwarded: list[str] = [
        part.strip()
        for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")
        if part.strip()
    ]
    if len(forwarded) < proxies:
        return remote
    return forwarded[-proxies]


def _key(scope: str, value: str) -> str:
    # Keyed with the secret so the table cannot be used to test whether an address is known.
    return salted_hmac(
        "accounts.login-throttle", f"{scope}:{value}", algorithm="sha256"
    ).hexdigest()


def _counters(email: str, address: str) -> list[tuple[str, int]]:
    email = normalise_email(email)
    return [
        (_key("pair", f"{email}|{address}"), settings.LOGIN_MAX_FAILURES_PER_EMAIL_AND_IP),
        (_key("email", email), settings.LOGIN_MAX_FAILURES_PER_EMAIL),
        (_key("address", address), settings.LOGIN_MAX_FAILURES_PER_IP),
    ]


def _window() -> timedelta:
    return timedelta(seconds=settings.LOGIN_FAILURE_WINDOW_SECONDS)


def seconds_until_allowed(email: str, address: str) -> int:
    """Return 0 when a sign-in may be attempted, otherwise how long to wait."""
    now = timezone.now()
    limits = dict(_counters(email, address))
    wait = 0
    for row in LoginThrottle.objects.filter(key__in=limits):
        expires = row.window_start + _window()
        if row.failures >= limits[row.key] and expires > now:
            wait = max(wait, int((expires - now).total_seconds()) + 1)
    return wait


def record_failure(email: str, address: str) -> None:
    now = timezone.now()
    for key, _limit in _counters(email, address):
        with transaction.atomic():
            row, created = LoginThrottle.objects.select_for_update().get_or_create(
                key=key, defaults={"failures": 1, "window_start": now}
            )
            if created:
                continue
            if row.window_start + _window() <= now:
                row.failures, row.window_start = 1, now
            else:
                row.failures += 1
            row.save(update_fields=["failures", "window_start"])


def record_success(email: str, address: str) -> None:
    pair_key = _counters(email, address)[0][0]
    LoginThrottle.objects.filter(key=pair_key).delete()


def clear_expired() -> int:
    deleted, _ = LoginThrottle.objects.filter(window_start__lte=timezone.now() - _window()).delete()
    return deleted
