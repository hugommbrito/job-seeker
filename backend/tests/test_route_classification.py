"""Every route states whether the demo account may use it, and the guard enforces the answer."""

from __future__ import annotations

import re

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

from apps.accounts.demo import (
    DemoAccess,
    DemoGuardMiddleware,
    demo_access,
    demo_denied,
    demo_readable,
)
from apps.accounts.models import Role
from config.api import api
from tests.routes import all_routes

pytestmark = pytest.mark.django_db

MARK = "_demo_access"


def test_every_route_is_classified():
    unclassified = sorted(route.label for route in all_routes() if not hasattr(route.view, MARK))
    assert not unclassified, (
        f"Routes with no demo decision: {unclassified}. Mark each view with @demo_readable or "
        "@demo_denied (apps/accounts/demo.py)."
    )


def test_the_walk_finds_every_api_operation():
    # The guard reads Django Ninja's operations through a closure. If a Ninja release changes
    # that, this count stops matching the OpenAPI schema and the failure points here.
    schema = api.get_openapi_schema()
    documented = {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        for method in operations
    }
    # The schema spells a parameter {name} where Django's pattern has <int:name>.
    walked = {
        (route.method, "/" + re.sub(r"<(?:\w+:)?(\w+)>", r"{\1}", route.pattern))
        for route in all_routes()
        if route.is_api
    }
    assert walked == documented
    assert walked, "no API operations found"


def test_the_expected_decisions():
    # Spelled out so that widening the guest's access is a visible change to this file.
    decisions = {route.label: getattr(route.view, MARK) for route in all_routes()}
    assert decisions == {
        "* health": DemoAccess.READABLE,
        "* api/": DemoAccess.DENIED,  # Django Ninja's own root view, which only answers 404
        "GET api/auth/csrf": DemoAccess.READABLE,
        "POST api/auth/login": DemoAccess.DENIED,
        "POST api/auth/logout": DemoAccess.READABLE,
        "GET api/auth/me": DemoAccess.READABLE,
        "GET api/auth/options": DemoAccess.READABLE,
        "POST api/auth/demo": DemoAccess.DENIED,
        "GET api/profile": DemoAccess.READABLE,
        "PATCH api/profile": DemoAccess.DENIED,
        "GET api/tracks": DemoAccess.READABLE,
        "POST api/tracks": DemoAccess.DENIED,
        "PATCH api/tracks/<int:track_id>": DemoAccess.DENIED,
        "DELETE api/tracks/<int:track_id>": DemoAccess.DENIED,
        "GET api/applications": DemoAccess.READABLE,
        "POST api/applications": DemoAccess.DENIED,
        "POST api/applications/import": DemoAccess.DENIED,
        "GET api/applications/<int:application_id>": DemoAccess.READABLE,
        "PATCH api/applications/<int:application_id>": DemoAccess.DENIED,
        "DELETE api/applications/<int:application_id>": DemoAccess.DENIED,
        "POST api/applications/<int:application_id>/stage": DemoAccess.DENIED,
        "POST api/applications/<int:application_id>/close": DemoAccess.DENIED,
        "POST api/applications/<int:application_id>/reopen": DemoAccess.DENIED,
        "POST api/applications/<int:application_id>/events": DemoAccess.DENIED,
        "PATCH api/applications/<int:application_id>/events/<int:event_id>": DemoAccess.DENIED,
        "DELETE api/applications/<int:application_id>/events/<int:event_id>": DemoAccess.DENIED,
        "POST api/applications/<int:application_id>/contacts": DemoAccess.DENIED,
        "PATCH api/applications/<int:application_id>/contacts/<int:contact_id>": DemoAccess.DENIED,
        "DELETE api/applications/<int:application_id>/contacts/<int:contact_id>": DemoAccess.DENIED,
        "POST api/applications/<int:application_id>/documents": DemoAccess.DENIED,
        "GET api/applications/<int:application_id>/documents/<int:document_id>": (
            DemoAccess.READABLE
        ),
        "DELETE api/applications/<int:application_id>/documents/<int:document_id>": (
            DemoAccess.DENIED
        ),
        "POST api/captures": DemoAccess.DENIED,
        "GET api/captures": DemoAccess.READABLE,
        "GET api/captures/<int:capture_id>": DemoAccess.READABLE,
        "POST api/captures/<int:capture_id>/extract": DemoAccess.DENIED,
        "POST api/captures/<int:capture_id>/save": DemoAccess.DENIED,
        "DELETE api/captures/<int:capture_id>": DemoAccess.DENIED,
        "GET api/notifications": DemoAccess.READABLE,
        "POST api/notifications/read": DemoAccess.DENIED,
        "GET api/channels": DemoAccess.READABLE,
        "POST api/channels/telegram/link": DemoAccess.DENIED,
        "DELETE api/channels/telegram": DemoAccess.DENIED,
        "POST api/channels/telegram/test": DemoAccess.DENIED,
        "GET api/operations": DemoAccess.DENIED,
        "* ^(?!api/|static/).*$": DemoAccess.READABLE,
    }


def _call(client, route, path):
    method = "GET" if route.method == "*" else route.method
    return client.generic(method, path, content_type="application/json", data="{}")


def test_the_demo_account_gets_403_on_every_route_not_marked_for_it(make_user, client_for):
    client = client_for(make_user(role=Role.DEMO))
    denied = [route for route in all_routes() if getattr(route.view, MARK) is DemoAccess.DENIED]
    assert denied, "there is no denied route to test the guard with"
    for route in denied:
        for path in route.paths():
            response = _call(client, route, path)
            assert response.status_code == 403, route.label
            assert response.json() == {"detail": "Not available to the demo account."}
    # Refused, not signed out: the session must survive a 403.
    assert client.get("/api/auth/me").json()["role"] == "demo"


def test_the_demo_account_reaches_every_route_marked_for_it(make_user, client_for):
    for route in all_routes():
        if getattr(route.view, MARK) is not DemoAccess.READABLE or route.label.endswith("logout"):
            continue
        client = client_for(make_user(role=Role.DEMO))
        for path in route.paths():
            assert _call(client, route, path).status_code not in (401, 403), route.label


def test_a_member_is_not_affected_by_the_guard(make_user, client_for):
    client = client_for(make_user())
    client.get("/api/auth/csrf")
    token = client.cookies["csrftoken"].value
    response = client.post(
        "/api/auth/login",
        data={"email": "nobody@example.test", "password": "wrong"},
        content_type="application/json",
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 401  # reached the view, which rejected the credentials


def _guard(view, user, method="GET"):
    request = getattr(RequestFactory(), method.lower())("/anything")
    request.user = user
    return DemoGuardMiddleware(lambda r: HttpResponse()).process_view(request, view, (), {})


def test_an_unmarked_view_is_denied_to_the_demo_account(make_user):
    def unmarked(request):
        return HttpResponse()

    assert demo_access(unmarked, "GET") is None
    assert _guard(unmarked, make_user(role=Role.DEMO)).status_code == 403
    assert _guard(unmarked, make_user(role=Role.MEMBER)) is None
    assert _guard(unmarked, make_user(role=Role.OWNER)) is None


def test_the_marks_decide(make_user):
    demo = make_user(role=Role.DEMO)

    @demo_readable
    def open_view(request):
        return HttpResponse()

    @demo_denied
    def closed_view(request):
        return HttpResponse()

    assert _guard(open_view, demo) is None
    assert _guard(closed_view, demo).status_code == 403


def test_the_guard_decides_per_method_on_an_api_path(make_user):
    # One URL, two operations with different marks: reading is allowed, writing is not.
    from ninja import NinjaAPI

    scratch = NinjaAPI(urls_namespace="scratch-demo-guard")

    @scratch.get("/thing")
    @demo_readable
    def read_thing(request):
        return {}

    @scratch.post("/thing")
    @demo_denied
    def write_thing(request):
        return {}

    callback = next(
        pattern.callback for pattern in scratch.urls[0] if str(pattern.pattern) == "thing"
    )
    demo = make_user(role=Role.DEMO)
    assert _guard(callback, demo, "GET") is None
    assert _guard(callback, demo, "POST").status_code == 403
    # A method the path does not serve has no mark, so it is denied like any unmarked view.
    assert _guard(callback, demo, "DELETE").status_code == 403
