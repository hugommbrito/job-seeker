"""Where document bytes are kept.

Callers use ``document_store()`` and never touch ``DocumentBlob`` directly, so moving the bytes
to object storage later is a new class here and a setting, not a change at every call site.
"""

from __future__ import annotations

from typing import Protocol

from django.conf import settings
from django.utils.module_loading import import_string

from apps.documents.models import Document, DocumentBlob


class DocumentStore(Protocol):
    def save(self, document: Document, content: bytes) -> None: ...

    def read(self, document: Document) -> bytes: ...


class DatabaseStore:
    """Keeps the bytes in Postgres, under the same row-level security as the metadata."""

    def save(self, document: Document, content: bytes) -> None:
        DocumentBlob.objects.update_or_create(document=document, defaults={"content": content})

    def read(self, document: Document) -> bytes:
        return bytes(DocumentBlob.objects.get(document=document).content)


def document_store() -> DocumentStore:
    store: DocumentStore = import_string(settings.DOCUMENT_STORE)()
    return store
