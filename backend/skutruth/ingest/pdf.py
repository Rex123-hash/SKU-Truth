"""PDF parsing, isolated from everything downstream.

`pypdf` was chosen over the alternatives for two reasons that matter here.

**Licence.** pypdf is BSD-3-Clause. PyMuPDF, which is faster and extracts more
faithfully, is AGPL-3.0 — a genuine problem for a submission whose IP transfers to the
organisers on award, and not a licence to take on casually for a convenience.

**Determinism.** pypdf is pure Python with no binary wheels, so extraction does not
vary with the platform a run happens to land on. For a system whose whole claim is
reproducibility, a parser that behaves identically everywhere is worth more than one
that is faster.

The cost is real and worth stating: pypdf's table extraction is weaker than
pdfplumber's or PyMuPDF's, and dense specification tables can come out with awkward
ordering. That is a recall problem for later extraction, not a correctness problem
here — the page text is still exactly what the parser saw, and `parser_version` on
every artifact makes a future switch observable rather than silent.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime

from pypdf import PdfReader
from pypdf import __version__ as PYPDF_VERSION
from pypdf.errors import PdfReadError

from .errors import (
    DocumentTooLargeError,
    EmptyDocumentError,
    EncryptedDocumentError,
    MalformedDocumentError,
)
from .hashing import sha256_bytes, sha256_text
from .limits import ACCEPTED_MEDIA_TYPE, DEFAULT_LIMITS, PDF_MAGIC, IngestionLimits
from .models import (
    DocumentTextStatus,
    ExtractionStatus,
    IngestedArtifact,
    IngestedPage,
    SourceMetadata,
)
from .text import build_search_text, normalize_line_endings

PARSER_NAME = "pypdf"


def _validate_bytes(data: bytes, limits: IngestionLimits) -> None:
    if not data:
        raise EmptyDocumentError("document is empty (zero bytes)")
    if len(data) > limits.max_file_bytes:
        raise DocumentTooLargeError(
            f"document is {len(data):,} bytes, above the {limits.max_file_bytes:,} byte "
            "limit; it is rejected rather than truncated",
            limit="max_file_bytes",
            actual=len(data),
            allowed=limits.max_file_bytes,
        )
    if not data.startswith(PDF_MAGIC):
        # Checked before the parser sees anything, so a mis-pointed download fails on
        # a signature rather than somewhere deep inside a PDF state machine.
        raise MalformedDocumentError(
            f"document does not begin with the PDF signature {PDF_MAGIC.decode()!r}; "
            f"only {ACCEPTED_MEDIA_TYPE} is accepted"
        )


def _open(data: bytes) -> PdfReader:
    try:
        reader = PdfReader(io.BytesIO(data))
    except PdfReadError as exc:
        raise MalformedDocumentError(f"pypdf could not read the document: {exc}") from exc
    except Exception as exc:  # pypdf raises a variety of types on damaged input
        raise MalformedDocumentError(f"pypdf failed on the document: {exc}") from exc

    if reader.is_encrypted:
        # Not attempted with an empty password. That sometimes succeeds and sometimes
        # yields subtly wrong text, and evidence from a half-opened document is not
        # evidence.
        raise EncryptedDocumentError(
            "document is encrypted; ingestion refuses password-protected PDFs rather "
            "than attempting a decrypt whose result cannot be trusted"
        )
    return reader


def _extract_page(index: int, page, limits: IngestionLimits) -> IngestedPage:
    warnings: list[str] = []
    try:
        raw = page.extract_text() or ""
        status = ExtractionStatus.TEXT_EXTRACTED
    except Exception as exc:
        # One unreadable page must not lose the rest of the document; the failure is
        # recorded on the page rather than swallowed.
        raw, status = "", ExtractionStatus.EXTRACTION_FAILED
        warnings.append(f"text extraction failed: {type(exc).__name__}: {exc}")

    raw = normalize_line_endings(raw)
    if len(raw) > limits.max_page_text_chars:
        raise DocumentTooLargeError(
            f"page {index + 1} yielded {len(raw):,} characters, above the "
            f"{limits.max_page_text_chars:,} limit",
            limit="max_page_text_chars",
            actual=len(raw),
            allowed=limits.max_page_text_chars,
        )
    if status is ExtractionStatus.TEXT_EXTRACTED and not raw.strip():
        status = ExtractionStatus.NO_EXTRACTABLE_TEXT

    width = height = None
    try:
        box = page.mediabox
        width, height = float(box.width), float(box.height)
    except Exception:  # dimensions are a convenience, never a reason to fail
        warnings.append("page dimensions unavailable")

    return IngestedPage(
        page_number=index + 1,
        raw_text=raw,
        search_text=build_search_text(raw),
        text_sha256=sha256_text(raw),
        character_count=len(raw),
        status=status,
        width_points=width,
        height_points=height,
        warnings=tuple(warnings),
    )


def _document_text_status(
    pages: list[IngestedPage], limits: IngestionLimits
) -> DocumentTextStatus:
    """Classify the document, without ever running or implying OCR."""
    bearing = sum(1 for p in pages if p.has_text)
    if bearing == len(pages):
        return DocumentTextStatus.TEXT_EXTRACTABLE
    if bearing / len(pages) >= limits.min_text_bearing_page_ratio:
        return DocumentTextStatus.PARTIALLY_EXTRACTABLE
    return DocumentTextStatus.OCR_REQUIRED


def ingest_pdf_bytes(
    data: bytes,
    *,
    source: SourceMetadata | None = None,
    limits: IngestionLimits | None = None,
    ingested_at: datetime | None = None,
) -> IngestedArtifact:
    """Turn PDF bytes into a versioned, page-addressable artifact.

    Validates, hashes the original bytes, and extracts text page by page. Raises a
    typed `IngestionError` on anything it will not accept; never returns a partial
    document described as whole.
    """
    limits = limits or DEFAULT_LIMITS
    _validate_bytes(data, limits)
    reader = _open(data)

    page_count = len(reader.pages)
    if page_count == 0:
        raise EmptyDocumentError("document contains no pages")
    if page_count > limits.max_page_count:
        raise DocumentTooLargeError(
            f"document has {page_count} pages, above the {limits.max_page_count} page "
            "limit; it is rejected rather than partially ingested",
            limit="max_page_count",
            actual=page_count,
            allowed=limits.max_page_count,
        )

    pages = [_extract_page(i, page, limits) for i, page in enumerate(reader.pages)]

    warnings: list[str] = []
    failed = [p.page_number for p in pages if p.status is ExtractionStatus.EXTRACTION_FAILED]
    if failed:
        warnings.append(f"text extraction failed on page(s): {failed}")

    return IngestedArtifact(
        sha256=sha256_bytes(data),
        media_type=ACCEPTED_MEDIA_TYPE,
        byte_size=len(data),
        page_count=page_count,
        pages=tuple(pages),
        source=source or SourceMetadata(),
        text_status=_document_text_status(pages, limits),
        ingested_at=ingested_at or datetime.now(UTC),
        parser_name=PARSER_NAME,
        parser_version=PYPDF_VERSION,
        warnings=tuple(warnings),
    )


def ingest_pdf(
    path,
    *,
    source: SourceMetadata | None = None,
    limits: IngestionLimits | None = None,
    ingested_at: datetime | None = None,
) -> IngestedArtifact:
    """Ingest a local PDF file.

    Local bytes only. Ingestion never fetches a URL: discovery decides *this URL looks
    useful*, ingestion decides *these exact bytes are the evidence artifact*, and
    keeping the two apart is what stops a landing page from quietly becoming the thing
    a citation points at.
    """
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        raise MalformedDocumentError(f"no file at {p}")
    filename = p.name
    if source is None:
        source = SourceMetadata(original_filename=filename)
    elif source.original_filename is None:
        source = source.model_copy(update={"original_filename": filename})
    return ingest_pdf_bytes(
        p.read_bytes(), source=source, limits=limits, ingested_at=ingested_at
    )
