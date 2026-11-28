"""What a card holds besides its timeline: contacts and the documents that were sent."""

from __future__ import annotations

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from apps.documents.models import Document, DocumentBlob
from apps.documents.uploads import clean_filename
from apps.tenancy.context import tenant_context

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.7\n% a tiny but well-labelled file\n"


@pytest.fixture
def member(make_user):
    return make_user()


@pytest.fixture
def client(member, client_for):
    return client_for(member)


@pytest.fixture
def application(client):
    body = {"company_name": "Example Corp", "role_title": "Analyst"}
    return client.post("/api/applications", data=body, content_type="application/json").json()


def _upload(client, application, name="cv.pdf", content=PDF, kind="cv"):
    return client.post(
        f"/api/applications/{application['id']}/documents",
        {"file": SimpleUploadedFile(name, content), "kind": kind},
    )


# --- Contacts


def test_add_edit_and_remove_a_contact(client, application):
    base = f"/api/applications/{application['id']}/contacts"
    created = client.post(
        base,
        data={"name": "Sam Recruiter", "role": "Talent partner", "email": "sam@example.org"},
        content_type="application/json",
    )
    assert created.status_code == 201
    contact = created.json()
    detail = client.get(f"/api/applications/{application['id']}").json()
    assert [c["name"] for c in detail["contacts"]] == ["Sam Recruiter"]

    edited = client.patch(
        f"{base}/{contact['id']}",
        data={"phone": "+1 416 555 0100"},
        content_type="application/json",
    )
    assert edited.json()["phone"] == "+1 416 555 0100"
    assert client.delete(f"{base}/{contact['id']}").status_code == 204
    assert client.get(f"/api/applications/{application['id']}").json()["contacts"] == []


@pytest.mark.parametrize(
    "fields",
    [
        {"name": ""},
        {"name": "A", "email": "not-an-address"},
        {"name": "A", "profile_url": "javascript:alert(1)"},
        {"name": "A", "phone": "1" * 51},
    ],
)
def test_bad_contacts_are_refused(client, application, fields):
    response = client.post(
        f"/api/applications/{application['id']}/contacts",
        data=fields,
        content_type="application/json",
    )
    assert response.status_code == 422


def test_another_users_contacts_are_out_of_reach(client, application, make_user, client_for):
    other = client_for(make_user())
    theirs = other.post(
        "/api/applications",
        data={"company_name": "B", "role_title": "B"},
        content_type="application/json",
    ).json()
    contact = other.post(
        f"/api/applications/{theirs['id']}/contacts",
        data={"name": "Private person"},
        content_type="application/json",
    ).json()
    url = f"/api/applications/{theirs['id']}/contacts"
    assert client.post(url, data={"name": "x"}, content_type="application/json").status_code == 404
    assert client.delete(f"{url}/{contact['id']}").status_code == 404
    # Through one's own application id, too.
    mine = f"/api/applications/{application['id']}/contacts/{contact['id']}"
    assert (
        client.patch(mine, data={"name": "x"}, content_type="application/json").status_code == 404
    )


# --- Documents


def test_upload_list_and_download(client, application):
    response = _upload(client, application)
    assert response.status_code == 201
    document = response.json()
    assert document["filename"] == "cv.pdf"
    assert document["content_type"] == "application/pdf"
    assert document["kind"] == "cv"
    assert document["size"] == len(PDF)

    detail = client.get(f"/api/applications/{application['id']}").json()
    assert [d["id"] for d in detail["documents"]] == [document["id"]]

    download = client.get(f"/api/applications/{application['id']}/documents/{document['id']}")
    assert download.status_code == 200
    assert download.content == PDF
    # Always an opaque attachment, in a sandbox, never cached by a shared cache.
    assert download["Content-Type"] == "application/octet-stream"
    assert download["Content-Disposition"] == 'attachment; filename="cv.pdf"'
    assert download["Content-Security-Policy"] == "sandbox; default-src 'none'"
    assert download["Cache-Control"] == "private, no-store"
    assert download["X-Content-Type-Options"] == "nosniff"


def test_a_saved_html_email_downloads_as_a_file_not_a_page(client, application):
    html = b"<html><script>alert(document.cookie)</script></html>"
    document = _upload(client, application, name="rejection.html", content=html, kind="email")
    assert document.status_code == 201
    download = client.get(
        f"/api/applications/{application['id']}/documents/{document.json()['id']}"
    )
    assert download["Content-Type"] == "application/octet-stream"
    assert download["Content-Disposition"].startswith("attachment;")
    assert "sandbox" in download["Content-Security-Policy"]


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("setup.exe", b"MZ\x90\x00", "not accepted"),
        ("cv.pdf", b"not really a pdf", "not a .pdf file"),
        ("cv.docx", b"%PDF-1.7", "not a .docx file"),
        ("notes.txt", b"text\x00with a nul", "not text"),
        ("empty.txt", b"", "empty"),
    ],
)
def test_uploads_that_are_refused(client, application, name, content, reason):
    response = _upload(client, application, name=name, content=content)
    assert response.status_code == 422
    assert reason in response.json()["detail"]
    with tenant_context(application_owner(client)):
        assert not Document.objects.exists()


def application_owner(client) -> int:
    return int(client.session["_auth_user_id"])


def test_an_upload_over_the_limit_is_refused(client, application, settings):
    settings.DOCUMENT_MAX_BYTES = 16
    response = _upload(client, application, content=PDF)
    assert response.status_code == 422
    assert "too large" in response.json()["detail"]


def test_an_unknown_kind_is_refused(client, application):
    assert _upload(client, application, kind="passport").status_code == 422


@pytest.mark.parametrize(
    ("raw", "clean"),
    [
        ("cv.pdf", "cv.pdf"),
        ("../../etc/passwd.txt", "passwd.txt"),
        ("C:\\Users\\someone\\cv.pdf", "cv.pdf"),
        ('evil"\r\nX-Injected: 1.txt', "evil_X-Injected_ 1.txt"),
        ("...", "document"),
        ("a" * 300 + ".pdf", "a" * 146 + ".pdf"),
    ],
)
def test_filenames_are_cleaned(raw, clean):
    assert clean_filename(raw) == clean


def test_delete_a_document_and_its_content(client, application, member):
    document = _upload(client, application).json()
    url = f"/api/applications/{application['id']}/documents/{document['id']}"
    assert client.delete(url).status_code == 204
    assert client.get(url).status_code == 404
    with tenant_context(member.pk):
        assert not DocumentBlob.objects.exists()


def test_deleting_the_application_deletes_its_documents(client, application, member):
    _upload(client, application)
    assert client.delete(f"/api/applications/{application['id']}").status_code == 204
    with tenant_context(member.pk):
        assert not Document.objects.exists()
        assert not DocumentBlob.objects.exists()


def test_another_users_documents_are_out_of_reach(client, application, make_user, client_for):
    other = client_for(make_user())
    theirs = other.post(
        "/api/applications",
        data={"company_name": "B", "role_title": "B"},
        content_type="application/json",
    ).json()
    document = _upload(other, theirs).json()
    url = f"/api/applications/{theirs['id']}/documents"
    assert _upload(client, theirs).status_code == 404
    assert client.get(f"{url}/{document['id']}").status_code == 404
    assert client.delete(f"{url}/{document['id']}").status_code == 404
    # Asking for it under one's own application finds nothing either.
    mine = f"/api/applications/{application['id']}/documents/{document['id']}"
    assert client.get(mine).status_code == 404
    assert other.get(f"{url}/{document['id']}").content == PDF
