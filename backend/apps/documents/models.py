"""Files a user keeps with an application: the CV and cover letter sent, a saved email.

The bytes live in their own table, so listing documents never loads them, and the store that
holds them is behind an interface (``apps.documents.store``) so another backend can replace the
database later without touching the callers. Both tables are per-user and under row-level
security, like every other piece of a user's data.
"""

from __future__ import annotations

from typing import ClassVar

from django.db import models

from apps.applications.models import Application
from apps.tenancy.models import TenantModel


class DocumentKind(models.TextChoices):
    CV = "cv", "CV"
    COVER_LETTER = "cover_letter", "Cover letter"
    EMAIL = "email", "Email"
    OTHER = "other", "Other"


class Document(TenantModel):
    # Phase 1 documents always belong to an application; later ones (a base CV) may not.
    application = models.ForeignKey(
        Application, null=True, blank=True, on_delete=models.CASCADE, related_name="documents"
    )
    kind = models.CharField(max_length=16, choices=DocumentKind.choices, default=DocumentKind.OTHER)
    filename = models.CharField(max_length=200)
    # What the upload was recognised as; downloads are always sent as an opaque attachment.
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    sha256 = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints: ClassVar = [
            models.CheckConstraint(
                condition=models.Q(kind__in=DocumentKind.values), name="documents_kind_valid"
            ),
        ]

    def __str__(self) -> str:
        return f"document {self.pk}"


class DocumentBlob(TenantModel):
    document = models.OneToOneField(Document, on_delete=models.CASCADE, related_name="blob")
    content = models.BinaryField()

    def __str__(self) -> str:
        return f"content of document {self.document_id}"
