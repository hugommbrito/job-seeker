"""What an upload may be, decided from its name and its first bytes.

Uploaded files are kept and handed back as downloads, never rendered by the app. The checks
here keep the store to the documents a job search produces, refuse anything whose content does
not match its name, and make the stored filename safe to put in a header.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath

from django.conf import settings


class UploadRefused(ValueError):
    """The upload is not accepted; the message says why and is safe to show."""


@dataclass(frozen=True)
class FileType:
    content_type: str
    # The bytes the file must start with, or None for text formats, which are checked for
    # binary content instead.
    signature: bytes | None


ZIP = b"PK\x03\x04"
TYPES: dict[str, FileType] = {
    ".pdf": FileType("application/pdf", b"%PDF-"),
    ".docx": FileType(
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document", ZIP
    ),
    ".odt": FileType("application/vnd.oasis.opendocument.text", ZIP),
    ".doc": FileType("application/msword", b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"),
    ".rtf": FileType("application/rtf", b"{\\rtf"),
    ".txt": FileType("text/plain", None),
    ".md": FileType("text/markdown", None),
    ".html": FileType("text/html", None),
    ".htm": FileType("text/html", None),
    ".eml": FileType("message/rfc822", None),
    ".png": FileType("image/png", b"\x89PNG\r\n\x1a\n"),
    ".jpg": FileType("image/jpeg", b"\xff\xd8\xff"),
    ".jpeg": FileType("image/jpeg", b"\xff\xd8\xff"),
}

_UNSAFE = re.compile(r"[\x00-\x1f\x7f\"\\/:*?<>|]+")


@dataclass(frozen=True)
class AcceptedFile:
    filename: str
    content_type: str
    size: int
    sha256: str


def clean_filename(raw: str) -> str:
    """The last path component, normalised, without characters that break headers or paths."""
    # Browsers send a bare name, but a client can send "C:\\fake\\..\\path" or "../../x".
    name = PureWindowsPath(PurePosixPath(raw).name).name
    name = unicodedata.normalize("NFC", name)
    name = _UNSAFE.sub("_", name).strip(" .")
    if len(name) > 150:
        stem, dot, suffix = name.rpartition(".")
        name = (
            f"{stem[: 150 - len(suffix) - 1]}.{suffix}" if dot and len(suffix) <= 10 else name[:150]
        )
    return name or "document"


def inspect(raw_name: str, content: bytes) -> AcceptedFile:
    """Accept the file or raise ``UploadRefused`` with a reason a person can act on."""
    if not content:
        raise UploadRefused("The file is empty.")
    if len(content) > settings.DOCUMENT_MAX_BYTES:
        limit = settings.DOCUMENT_MAX_BYTES // (1024 * 1024)
        raise UploadRefused(f"The file is larger than {limit} MB.")
    filename = clean_filename(raw_name)
    suffix = PurePosixPath(filename.lower()).suffix
    kind = TYPES.get(suffix)
    if kind is None:
        allowed = ", ".join(sorted(TYPES))
        raise UploadRefused(f"Files of this type are not accepted. Accepted: {allowed}.")
    if kind.signature is not None:
        if not content.startswith(kind.signature):
            raise UploadRefused(f"The file's content is not a {suffix} file.")
    elif b"\x00" in content[:8192]:
        raise UploadRefused(f"The file's content is not text, as a {suffix} file should be.")
    return AcceptedFile(
        filename=filename,
        content_type=kind.content_type,
        size=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )
