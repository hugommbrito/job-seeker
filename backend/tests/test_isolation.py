"""The canary isolation suite.

Tenant B is seeded with strings that exist nowhere else. Nothing tenant A, the demo account or an
anonymous visitor can do may ever produce one of them. The guest login may be switched on only
while this suite and the catalog meta-test pass.
"""

from __future__ import annotations

import json

import pytest
from django.db import connection
from django.test import Client

from apps.accounts.models import Role
from apps.applications.models import Application
from apps.tenancy import classification
from apps.tenancy.context import tenant_context
from tests.canaries import SEEDERS, plant, planted_ids
from tests.routes import all_routes

pytestmark = pytest.mark.django_db


def _columns(row) -> dict[str, object]:
    """Every stored column of a row, bytes included (model_to_dict skips non-editable ones)."""
    values = {}
    for field in row._meta.concrete_fields:
        value = getattr(row, field.attname)
        if isinstance(value, (bytes, memoryview)):
            value = bytes(value).decode("utf-8", errors="replace")
        values[field.attname] = value
    return values


@pytest.fixture
def tenants(make_user):
    """Three accounts with data of their own: two members and the guest."""
    a, b, demo = make_user(), make_user(), make_user(role=Role.DEMO)
    return {
        "a": (a, plant(a)),
        "b": (b, plant(b)),
        "demo": (demo, plant(demo)),
    }


def test_every_tenant_model_has_a_canary_seeder():
    missing = sorted(
        model.__name__ for model in classification.tenant_models() if model not in SEEDERS
    )
    assert not missing, f"Add a seeder in tests/canaries.py for: {missing}"


def test_each_seeder_really_plants_its_canary(tenants):
    # Guards the suite itself: a seeder that silently wrote nothing would make every "the canary
    # did not leak" assertion below pass for the wrong reason.
    user, canaries = tenants["b"]
    with tenant_context(user.pk):
        stored = json.dumps(
            [_columns(row) for model in SEEDERS for row in model.objects.all()], default=str
        )
    assert len(canaries) == len(SEEDERS)
    for canary in canaries:
        assert canary in stored


def test_a_query_with_no_filter_returns_only_the_callers_rows(tenants):
    (a, own), (_b, foreign) = tenants["a"], tenants["b"]
    with tenant_context(a.pk):
        for model in classification.tenant_models():
            rows = list(model.objects.all())
            assert rows, f"{model.__name__}: the caller's own row is missing"
            assert {row.user_id for row in rows} == {a.pk}
            dumped = json.dumps([_columns(row) for row in rows], default=str)
            assert any(canary in dumped for canary in own)
            assert not any(canary in dumped for canary in foreign)


def test_raw_sql_is_filtered_too(tenants):
    (a, _), (b, _) = tenants["a"], tenants["b"]
    with tenant_context(a.pk), connection.cursor() as cursor:
        for table in classification.tenant_tables():
            cursor.execute(f'SELECT DISTINCT user_id FROM "{table}"')
            assert cursor.fetchall() == [(a.pk,)]
            cursor.execute(f'SELECT count(*) FROM "{table}" WHERE user_id = %s', [b.pk])
            assert cursor.fetchone() == (0,)


def test_another_users_rows_cannot_be_changed_or_deleted(tenants):
    (a, _), (b, foreign) = tenants["a"], tenants["b"]
    with tenant_context(a.pk):
        for model in classification.tenant_models():
            assert model.objects.filter(user_id=b.pk).delete()[0] == 0
            assert model.objects.filter(user_id=b.pk).update(user_id=a.pk) == 0
    with tenant_context(b.pk):
        for model in classification.tenant_models():
            dumped = json.dumps([_columns(row) for row in model.objects.all()], default=str)
            assert any(canary in dumped for canary in foreign), "tenant B's row was touched"


def _ids(tenants) -> dict[str, list[int]]:
    return planted_ids(user for user, _canaries in tenants.values())


def _crawl(client: Client, ids: dict[str, list[int]] | None = None) -> dict[str, str]:
    """GET every route the server has and return what came back, headers included.

    A route with a parameter is requested with the id of every planted row of its model, the
    caller's own and everybody else's.
    """
    seen = {}
    for route in all_routes():
        if route.method not in ("GET", "*"):
            continue
        for path in route.paths(ids):
            response = client.get(path)
            headers = "\n".join(f"{key}: {value}" for key, value in response.items())
            body = b"".join(response).decode("utf-8", errors="replace")
            seen[f"{route.label} -> {path}"] = f"{response.status_code}\n{headers}\n\n{body}"
    assert seen, "no routes were crawled"
    return seen


def _assert_absent(seen: dict[str, str], canaries: list[str], who: str) -> None:
    for label, text in seen.items():
        for canary in canaries:
            assert canary not in text, f"{label} leaked another tenant's data to {who}"


def test_no_response_to_tenant_a_contains_tenant_b_data(tenants, client_for):
    (a, own), (_b, foreign), (_demo, demo_data) = tenants["a"], tenants["b"], tenants["demo"]
    seen = _crawl(client_for(a), _ids(tenants))
    _assert_absent(seen, foreign + demo_data, "tenant A")
    # The crawl must reach tenant data at all, or the assertion above proves nothing.
    assert any(canary in text for text in seen.values() for canary in own)


def test_no_response_to_the_demo_account_contains_real_tenant_data(tenants, client_for):
    (_a, a_data), (_b, b_data), (demo, own) = tenants["a"], tenants["b"], tenants["demo"]
    seen = _crawl(client_for(demo), _ids(tenants))
    _assert_absent(seen, a_data + b_data, "the demo account")
    assert any(canary in text for text in seen.values() for canary in own)


def test_no_response_to_an_anonymous_visitor_contains_tenant_data(tenants):
    everyone = [canary for _user, canaries in tenants.values() for canary in canaries]
    _assert_absent(_crawl(Client(), _ids(tenants)), everyone, "an anonymous visitor")


def test_requests_on_one_connection_do_not_inherit_the_previous_user(tenants, client_for):
    # The test client reuses one database connection, as a server worker does.
    (a, a_data), (b, b_data) = tenants["a"], tenants["b"]
    first = client_for(a).get("/api/profile").json()
    second = client_for(b).get("/api/profile").json()
    assert first["timezone"] in a_data
    assert second["timezone"] in b_data
    assert Client().get("/api/profile").status_code == 401


def test_the_crawl_requests_other_tenants_rows_by_id(tenants, client_for):
    # Guards the crawl: a detail route must be called with ids from every tenant, or "nothing
    # leaked" would only mean "nothing was asked for".
    (a, _own), (b, _foreign) = tenants["a"], tenants["b"]
    ids = _ids(tenants)
    with tenant_context(b.pk):
        b_application = Application.objects.values_list("pk", flat=True).first()
    assert b_application in ids["Application"]
    seen = _crawl(client_for(a), ids)
    label = f"GET api/applications/<int:application_id> -> /api/applications/{b_application}"
    assert seen[label].startswith("404")
