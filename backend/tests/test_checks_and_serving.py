"""The database-role check, the health endpoint and how the web client is served."""

from __future__ import annotations

import pytest
from django.core.management import call_command
from django.test import Client

from apps.tenancy.checks import RoleFacts, check_database_role, read_role_facts, role_problems


def _ids(facts: RoleFacts, service: str) -> list[str]:
    return [message.id for message in role_problems(facts, service)]


def test_the_app_role_passes_in_every_service():
    facts = RoleFacts(is_superuser=False, bypasses_rls=False, owned_tables=0)
    assert _ids(facts, "api") == []
    assert _ids(facts, "worker") == []


def test_a_superuser_is_refused_everywhere_including_migrate():
    facts = RoleFacts(is_superuser=True, bypasses_rls=True, owned_tables=0)
    assert "tenancy.E001" in _ids(facts, "api")
    assert _ids(facts, "migrate") == ["tenancy.E001"]


def test_bypassrls_is_refused_outside_migrate():
    facts = RoleFacts(is_superuser=False, bypasses_rls=True, owned_tables=0)
    assert _ids(facts, "api") == ["tenancy.E002"]


def test_the_schema_owner_is_refused_outside_migrate():
    facts = RoleFacts(is_superuser=False, bypasses_rls=False, owned_tables=9)
    assert _ids(facts, "api") == ["tenancy.E003"]
    assert _ids(facts, "migrate") == []


@pytest.mark.django_db
def test_the_check_reads_the_real_role_and_passes_for_the_test_connection():
    assert read_role_facts() == RoleFacts(is_superuser=False, bypasses_rls=False, owned_tables=0)
    assert check_database_role(app_configs=None, databases=["default"]) == []
    # Not asked about a database: nothing to say, and no connection opened.
    assert check_database_role(app_configs=None, databases=None) == []


@pytest.mark.django_db
def test_no_migration_is_missing():
    call_command("makemigrations", check=True, dry_run=True, verbosity=0)


def test_health_answers_without_touching_the_database(django_assert_num_queries, db):
    with django_assert_num_queries(0):
        response = Client().get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_is_read_only():
    assert Client().post("/health").status_code == 405
    # Monitors and link checkers probe with HEAD.
    assert Client().head("/health").status_code == 200


@pytest.fixture
def built_client(tmp_path, settings):
    (tmp_path / "index.html").write_text("<!doctype html><title>job-seeker</title>")
    settings.WEB_DIST_DIR = tmp_path
    return tmp_path


@pytest.mark.parametrize("path", ["/", "/board", "/settings/profile", "/healthy"])
def test_client_side_routes_get_the_entry_page(built_client, path):
    response = Client().get(path)
    assert response.status_code == 200
    assert b"<title>job-seeker</title>" in response.content
    assert response["Cache-Control"] == "no-cache"


def test_the_entry_page_answers_head_and_refuses_writes(built_client):
    assert Client().head("/").status_code == 200
    assert Client().post("/").status_code == 405


def test_an_unknown_api_path_is_a_404_and_not_the_entry_page(built_client):
    response = Client().get("/api/does-not-exist")
    assert response.status_code == 404
    assert b"job-seeker</title>" not in response.content


def test_without_a_build_the_entry_page_says_so(tmp_path, settings):
    settings.WEB_DIST_DIR = tmp_path / "missing"
    response = Client().get("/")
    assert response.status_code == 404
    assert b"has not been built" in response.content


def test_responses_carry_the_content_security_policy(built_client):
    policy = Client().get("/")["Content-Security-Policy"]
    directives = dict(part.strip().split(" ", 1) for part in policy.split(";"))
    # The point of the policy: only this origin's scripts run, so untrusted posting or email
    # text can never become code even if it is rendered wrongly.
    assert directives["script-src"] == "'self'"
    assert directives["object-src"] == "'none'"
    assert directives["frame-ancestors"] == "'none'"
    assert "unsafe-inline" not in directives["script-src"]
    assert "unsafe-eval" not in policy


def test_other_hardening_headers(built_client):
    response = Client().get("/")
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"


def test_the_interactive_docs_are_not_served_outside_development():
    assert Client().get("/api/docs").status_code == 404
    assert Client().get("/api/openapi.json").status_code == 404
