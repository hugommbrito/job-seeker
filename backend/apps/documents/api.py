"""Documents kept with an application: upload, download and delete.

Downloads are always an opaque attachment in a sandbox, whatever was uploaded, so a stored HTML
email or a crafted PDF can never run as a page of this site.
"""

from __future__ import annotations

from datetime import datetime

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from ninja import File, Form, Router, Schema, Status, UploadedFile
from ninja.errors import HttpError

from apps.accounts.demo import demo_denied, demo_readable
from apps.applications.models import Application
from apps.documents.models import Document, DocumentKind
from apps.documents.store import document_store
from apps.documents.uploads import UploadRefused, inspect

router = Router(tags=["documents"])


class DocumentOut(Schema):
    id: int
    kind: DocumentKind
    filename: str
    content_type: str
    size: int
    created_at: datetime


def _document(application_id: int, document_id: int) -> Document:
    return get_object_or_404(Document, pk=document_id, application_id=application_id)


@router.post("/{int:application_id}/documents", response={201: DocumentOut})
@demo_denied
def upload_document(
    request: HttpRequest,
    application_id: int,
    file: File[UploadedFile],
    kind: Form[DocumentKind] = DocumentKind.OTHER,
) -> Status[Document]:
    application = get_object_or_404(Application, pk=application_id)
    # Refused before reading it into memory; inspect() checks the size of what was read too.
    if file.size is not None and file.size > settings.DOCUMENT_MAX_BYTES:
        raise HttpError(422, "The file is too large.")
    content = file.read()
    try:
        accepted = inspect(file.name or "", content)
    except UploadRefused as refusal:
        raise HttpError(422, str(refusal)) from refusal
    document = Document.objects.create(
        application=application,
        kind=kind,
        filename=accepted.filename,
        content_type=accepted.content_type,
        size=accepted.size,
        sha256=accepted.sha256,
    )
    document_store().save(document, content)
    return Status(201, document)


@router.get("/{int:application_id}/documents/{int:document_id}")
@demo_readable
def download_document(request: HttpRequest, application_id: int, document_id: int) -> HttpResponse:
    document = _document(application_id, document_id)
    response = HttpResponse(
        document_store().read(document), content_type="application/octet-stream"
    )
    response["Content-Disposition"] = content_disposition_header(
        as_attachment=True, filename=document.filename
    )
    response["Cache-Control"] = "private, no-store"
    # Should a browser render it anyway, it renders with no scripts, no plugins and no origin.
    response["Content-Security-Policy"] = "sandbox; default-src 'none'"
    return response


@router.delete("/{int:application_id}/documents/{int:document_id}", response={204: None})
@demo_denied
def delete_document(request: HttpRequest, application_id: int, document_id: int) -> Status[None]:
    _document(application_id, document_id).delete()
    return Status(204, None)
