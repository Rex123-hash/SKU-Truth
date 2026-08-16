"""Typed ingestion failures.

Ingestion refuses rather than degrades. A truncated document that reports itself as
complete, or a corrupted artifact silently re-derived on read, would put a citation
behind text nobody can vouch for — so every failure below is loud.
"""

from __future__ import annotations


class IngestionError(Exception):
    """Base class for every refusal in this package."""


class UnsupportedDocumentError(IngestionError):
    """The bytes are not a document this layer accepts."""


class EmptyDocumentError(UnsupportedDocumentError):
    """Zero bytes, or a PDF with no pages."""


class EncryptedDocumentError(UnsupportedDocumentError):
    """The PDF is password-protected.

    Refused rather than guessed at. An empty-password decrypt sometimes succeeds and
    sometimes yields subtly wrong text, and evidence extracted from a document we
    only half-opened is not evidence.
    """


class MalformedDocumentError(UnsupportedDocumentError):
    """The parser could not read the document."""


class DocumentTooLargeError(IngestionError):
    """The document exceeds a configured limit.

    Raised instead of truncating. A partially ingested document whose page map claims
    to be the whole thing is worse than no ingestion at all.
    """

    def __init__(self, message: str, *, limit: str, actual: int, allowed: int) -> None:
        super().__init__(message)
        self.limit = limit
        self.actual = actual
        self.allowed = allowed


class ArtifactStoreError(IngestionError):
    """The artifact store could not satisfy a request."""


class ArtifactNotFoundError(ArtifactStoreError):
    """No stored artifact for this hash."""

    def __init__(self, sha256: str, searched: str) -> None:
        super().__init__(f"no artifact {sha256} under {searched}")
        self.sha256 = sha256
        self.searched = searched


class CorruptArtifactError(ArtifactStoreError):
    """A stored artifact failed validation on load.

    Never repaired automatically. Reading is reading; regenerating is re-ingestion,
    and a read that quietly rebuilt its own evidence would defeat the point of
    hashing it.
    """

    def __init__(self, sha256: str, reason: str) -> None:
        super().__init__(f"stored artifact {sha256} failed validation: {reason}")
        self.sha256 = sha256
        self.reason = reason
