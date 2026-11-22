"""Shared test setup.

The one unusual thing here is who the tests connect as. Row-level security does not bind the
table owner's superuser-like habits or anyone with BYPASSRLS, so a suite that ran as the owner
would pass without ever exercising a policy. The test database is therefore created and migrated
as `migrator`, and then every test runs as `app`, exactly like the deployed api.
"""

from __future__ import annotations

import itertools
import os
from collections.abc import Callable, Iterator
from typing import Any

import dj_database_url
import pytest
from django.contrib.auth.hashers import make_password
from django.db import connections
from django.test import Client

from apps.accounts.models import Role, User

PASSWORD = "correct horse battery staple 42"


def _credentials(url: str) -> dict[str, Any]:
    parsed = dj_database_url.parse(url)
    return {"USER": parsed["USER"], "PASSWORD": parsed["PASSWORD"]}


def _connect_as(credentials: dict[str, Any]) -> None:
    connection = connections["default"]
    connection.close()
    connection.settings_dict.update(credentials)


@pytest.fixture(scope="session")
def django_db_setup(
    request: pytest.FixtureRequest,
    django_test_environment: None,
    django_db_blocker: Any,
    django_db_keepdb: bool,
    django_db_createdb: bool,
) -> Iterator[None]:
    """Create and migrate the test database as the owner, then hand it to the tests as `app`."""
    from django.test.utils import setup_databases, teardown_databases

    owner_url = os.environ.get("MIGRATOR_DATABASE_URL")
    if not owner_url:
        raise pytest.UsageError(
            "MIGRATOR_DATABASE_URL is not set. The test database is created and migrated as the "
            "schema owner; see .env.example."
        )
    owner = _credentials(owner_url)
    app = {key: connections["default"].settings_dict[key] for key in ("USER", "PASSWORD")}
    keepdb = django_db_keepdb and not django_db_createdb
    verbosity = request.config.option.verbose

    with django_db_blocker.unblock():
        _connect_as(owner)
        config = setup_databases(verbosity=verbosity, interactive=False, keepdb=keepdb)
        _connect_as(app)

    yield

    if not keepdb:
        with django_db_blocker.unblock():
            _connect_as(owner)
            teardown_databases(config, verbosity=verbosity)


_password_hash: str | None = None


def _hashed_password() -> str:
    # Argon2 is slow on purpose. One hash is shared by every test user; the tests that care
    # about hashing go through the real sign-in path instead.
    global _password_hash
    if _password_hash is None:
        _password_hash = make_password(PASSWORD)
    return _password_hash


@pytest.fixture
def make_user(db: None) -> Callable[..., User]:
    counter = itertools.count(1)

    def make(role: str = Role.MEMBER, email: str | None = None) -> User:
        user = User(
            email=email or f"user{next(counter)}@example.test",
            role=role,
            password=_hashed_password(),
        )
        user.save()
        return user

    return make


@pytest.fixture
def client_for() -> Callable[[User], Client]:
    """Return a browser-like client already signed in as the given user."""

    def build(user: User) -> Client:
        client = Client()
        client.force_login(user)
        return client

    return build
