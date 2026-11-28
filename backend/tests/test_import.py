"""Importing past applications from a file, all or nothing."""

from __future__ import annotations

import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.applications.models import Application
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

CSV = (
    "company_name,role_title,stage,outcome,applied_at,last_interview_at,closed_on,source\n"
    "Example Corp,Analyst,interviews,rejected,2026-09-01,2026-09-20,2026-10-01,Referral\n"
    "Sample Inc,Coordinator,applied,,2026-10-05,,,Company site\n"
)


@pytest.fixture
def member(make_user):
    return make_user()


@pytest.fixture
def client(member, client_for):
    return client_for(member)


def _upload(client, name, content):
    return client.post(
        "/api/applications/import", {"file": SimpleUploadedFile(name, content.encode())}
    )


def test_csv_import_and_reimport(client, member):
    response = _upload(client, "past.csv", CSV)
    assert response.status_code == 200
    assert response.json() == {"created": 2, "skipped": 0, "errors": []}
    with tenant_context(member.pk):
        rejected = Application.objects.get(company_name="Example Corp")
    assert rejected.outcome == "rejected"
    assert rejected.stage == "interviews"
    assert str(rejected.last_interview_at) == "2026-09-20"
    # Importing the same file again creates nothing.
    assert _upload(client, "past.csv", CSV).json() == {"created": 0, "skipped": 2, "errors": []}


def test_json_import_with_timeline_and_contacts(client, member):
    rows = {
        "applications": [
            {
                "company_name": "Example Corp",
                "role_title": "Analyst",
                "applied_at": "2026-09-01",
                "events": [{"kind": "note", "occurred_on": "2026-09-03", "text": "Followed up"}],
                "contacts": [{"name": "Jordan Example", "email": "jordan@example.org"}],
                "posting": {"description": "The posting text"},
            }
        ]
    }
    assert _upload(client, "past.json", json.dumps(rows)).json()["created"] == 1
    with tenant_context(member.pk):
        application = Application.objects.get()
        assert application.contacts.get().name == "Jordan Example"
        assert application.events.filter(kind="note").exists()
        assert application.posting_snapshot == {"description": "The posting text"}


def test_one_bad_row_imports_nothing_and_every_problem_is_named(client, member):
    bad = CSV + ",Missing company,applied,,,,,\nExample Corp,Analyst,hired,,not-a-date,,,\n"
    response = _upload(client, "past.csv", bad)
    assert response.status_code == 422
    errors = response.json()["errors"]
    assert any(error.startswith("Row 3, company_name") for error in errors)
    assert any(error.startswith("Row 4, stage") for error in errors)
    assert any(error.startswith("Row 4, applied_at") for error in errors)
    with tenant_context(member.pk):
        assert not Application.objects.exists()


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("past.txt", "company_name\nX", ".csv or a .json"),
        ("past.json", "{not json", "not valid JSON"),
        ("past.json", '{"rows": []}', "Expected a list"),
        ("past.csv", "company_name,role_title,salary\nA,B,100\n", "Row 1, salary"),
    ],
)
def test_files_that_cannot_be_imported(client, name, content, reason):
    response = _upload(client, name, content)
    assert response.status_code == 422
    assert any(reason in error for error in response.json()["errors"])
