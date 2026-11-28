"""`tenant_context`: the one place that says who a block of code runs as."""

from __future__ import annotations

import psycopg
import pytest
from django.db import DatabaseError, connection, connections, transaction
from django.http import HttpResponse
from django.test import RequestFactory

from apps.profiles.models import Profile
from apps.tenancy.context import (
    TenantContextError,
    active_user_id,
    current_user_id,
    tenant_context,
)
from apps.tenancy.middleware import TenantContextMiddleware

pytestmark = pytest.mark.django_db


def _setting() -> str | None:
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_setting('app.user_id', true)")
        return cursor.fetchone()[0]


def test_sets_the_user_inside_and_clears_it_after(make_user):
    user = make_user()
    assert not _setting()
    with tenant_context(user.pk):
        assert _setting() == str(user.pk)
        assert current_user_id() == user.pk
    assert not _setting()
    assert active_user_id() is None


def test_clears_the_user_after_an_error(make_user):
    user = make_user()

    def write_then_fail() -> None:
        with tenant_context(user.pk):
            Profile.objects.create(timezone="UTC")
            raise RuntimeError("after the write")

    with pytest.raises(RuntimeError, match="after the write"):
        write_then_fail()
    assert not _setting()
    assert active_user_id() is None
    with tenant_context(user.pk):
        assert not Profile.objects.exists(), "the failed block's write was kept"


def test_reentering_for_the_same_user_is_allowed(make_user):
    user = make_user()
    with tenant_context(user.pk), tenant_context(user.pk):
        assert current_user_id() == user.pk
    assert not _setting()


def test_nesting_another_user_is_refused(make_user):
    first, second = make_user(), make_user()
    with tenant_context(first.pk):
        with pytest.raises(TenantContextError), tenant_context(second.pk):
            pass
        assert _setting() == str(first.pk), "the refused switch must leave the outer user"


@pytest.mark.parametrize("bad", [None, "7", 7.0, True])
def test_refuses_anything_but_an_integer_id(bad):
    with pytest.raises(TenantContextError), tenant_context(bad):
        pass


def test_current_user_id_fails_outside_a_context():
    with pytest.raises(TenantContextError):
        current_user_id()


def test_a_tenant_row_takes_its_owner_from_the_context(make_user):
    user = make_user()
    with tenant_context(user.pk):
        profile = Profile.objects.create(timezone="UTC")
    assert profile.user_id == user.pk


def test_saving_a_tenant_row_outside_a_context_fails_loudly():
    with pytest.raises(TenantContextError):
        Profile(timezone="UTC").save()


def test_a_row_cannot_be_written_for_another_user(make_user):
    first, second = make_user(), make_user()
    with tenant_context(first.pk):
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            Profile.objects.create(user=second, timezone="UTC")
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            Profile.objects.bulk_create([Profile(user=second, timezone="UTC")])


def test_a_row_cannot_be_given_away(make_user):
    first, second = make_user(), make_user()
    with tenant_context(first.pk):
        Profile.objects.create(timezone="UTC")
        with pytest.raises(DatabaseError, match="row-level security"), transaction.atomic():
            Profile.objects.update(user=second)


def _middleware(view):
    return TenantContextMiddleware(view)


def test_middleware_runs_the_view_as_the_signed_in_user(make_user):
    user = make_user()
    seen = {}

    def view(request):
        seen["user"] = active_user_id()
        return HttpResponse()

    request = RequestFactory().get("/")
    request.user = user
    _middleware(view)(request)
    assert seen["user"] == user.pk
    assert not _setting()


def test_middleware_gives_anonymous_requests_no_context():
    from django.contrib.auth.models import AnonymousUser

    seen = {}

    def view(request):
        seen["user"] = active_user_id()
        return HttpResponse()

    request = RequestFactory().get("/")
    request.user = AnonymousUser()
    _middleware(view)(request)
    assert seen["user"] is None


def test_middleware_discards_the_work_of_a_request_that_ends_in_a_server_error(make_user):
    user = make_user()

    def view(request):
        Profile.objects.create(timezone="UTC")
        return HttpResponse(status=500)

    request = RequestFactory().get("/")
    request.user = user
    assert _middleware(view)(request).status_code == 500
    with tenant_context(user.pk):
        assert not Profile.objects.exists()


def test_middleware_keeps_the_work_of_a_successful_request(make_user):
    user = make_user()

    def view(request):
        Profile.objects.create(timezone="UTC")
        return HttpResponse(status=201)

    request = RequestFactory().get("/")
    request.user = user
    _middleware(view)(request)
    with tenant_context(user.pk):
        assert Profile.objects.count() == 1


def test_isolation_holds_across_real_transactions_and_connections():
    """The same guarantees with nothing wrapped in a test transaction.

    Every other test runs inside one transaction that is rolled back at the end. This one
    commits for real, on its own connections, to show that the user does not linger on a
    connection after commit and that committed rows of two users stay apart.
    """
    params = connections["default"].get_connection_params()
    dsn = {
        key: params[key] for key in ("host", "port", "dbname", "user", "password") if key in params
    }

    def scalar(conn, sql, *args):
        return conn.execute(sql, args).fetchone()[0]

    with psycopg.connect(**dsn) as writer, psycopg.connect(**dsn) as reader:
        assert scalar(writer, "SELECT current_user") == "app"
        ids = []
        try:
            for index in range(2):
                ids.append(
                    scalar(
                        writer,
                        "INSERT INTO accounts_user (email, password, role) "
                        "VALUES (%s, '!', 'member') RETURNING id",
                        f"committed{index}@example.test",
                    )
                )
            writer.commit()

            for user_id in ids:
                writer.execute("SELECT set_config('app.user_id', %s, true)", (str(user_id),))
                writer.execute(
                    "INSERT INTO profiles_profile (user_id, timezone, hard, notify, home_label) "
                    "VALUES (%s, 'UTC', '{}', '{}', '')",
                    (user_id,),
                )
                writer.commit()
                # The setting was local to the transaction that just ended.
                assert not scalar(writer, "SELECT current_setting('app.user_id', true)")
                assert scalar(writer, "SELECT count(*) FROM profiles_profile") == 0
                writer.commit()

            # A different connection that never named a user sees nothing either.
            assert scalar(reader, "SELECT count(*) FROM profiles_profile") == 0
            reader.commit()

            reader.execute("SELECT set_config('app.user_id', %s, true)", (str(ids[0]),))
            assert reader.execute("SELECT user_id FROM profiles_profile").fetchall() == [(ids[0],)]
            reader.commit()
        finally:
            writer.rollback()
            for user_id in ids:
                # Deleting the user cascades to the profile, but the cascade is subject to the
                # policy too, so it runs as that user.
                writer.execute("SELECT set_config('app.user_id', %s, true)", (str(user_id),))
                writer.execute("DELETE FROM profiles_profile WHERE user_id = %s", (user_id,))
                writer.execute("DELETE FROM accounts_user WHERE id = %s", (user_id,))
                writer.commit()
