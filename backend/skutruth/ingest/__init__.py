"""Versioned PDF artifact ingestion.

Turns document bytes into a hashed, page-addressable source artifact. See ./README.md
for what that proves — and, more importantly, what it does not.
"""

from .citation_checks import (
    ArtifactCheckOutcome,
    CitationArtifactCheck,
    check_citation_artifact,
)
from .errors import (
    ArtifactNotFoundError,
    ArtifactStoreError,
    CorruptArtifactError,
    DocumentTooLargeError,
    EmptyDocumentError,
    EncryptedDocumentError,
    IngestionError,
    MalformedDocumentError,
    UnsupportedDocumentError,
)
from .hashing import artifact_id, is_valid_sha256, sha256_bytes, sha256_text
from .limits import (
    ACCEPTED_MEDIA_TYPE,
    DEFAULT_LIMITS,
    MAX_FILE_BYTES,
    MAX_PAGE_COUNT,
    MAX_PAGE_TEXT_CHARS,
    IngestionLimits,
)
from .locate import TextMatch, find_text, page_contains
from .models import (
    INGESTION_VERSION,
    DocumentTextStatus,
    ExtractionStatus,
    IngestedArtifact,
    IngestedPage,
    SourceMetadata,
    to_source_artifact,
)
from .pdf import PARSER_NAME, ingest_pdf, ingest_pdf_bytes
from .storage import (
    DEFAULT_FIXTURE_DIR,
    DEFAULT_RUNTIME_DIR,
    STORAGE_VERSION,
    ArtifactStore,
    fixture_store,
    ingest_and_store,
    runtime_store,
)
from .tables import (
    TABLE_EXTRACTION_VERSION,
    ExtractedCell,
    ExtractedTable,
    PageTableExtraction,
    TableExtractionStatus,
    extract_page_tables,
)
from .text import TEXT_NORMALIZATION_FORM, build_search_text, normalize_quote

__all__ = [
    "ACCEPTED_MEDIA_TYPE",
    "DEFAULT_FIXTURE_DIR",
    "DEFAULT_LIMITS",
    "DEFAULT_RUNTIME_DIR",
    "INGESTION_VERSION",
    "MAX_FILE_BYTES",
    "MAX_PAGE_COUNT",
    "MAX_PAGE_TEXT_CHARS",
    "PARSER_NAME",
    "STORAGE_VERSION",
    "TABLE_EXTRACTION_VERSION",
    "TEXT_NORMALIZATION_FORM",
    "ArtifactCheckOutcome",
    "ArtifactNotFoundError",
    "ArtifactStore",
    "ArtifactStoreError",
    "CitationArtifactCheck",
    "CorruptArtifactError",
    "DocumentTextStatus",
    "DocumentTooLargeError",
    "EmptyDocumentError",
    "EncryptedDocumentError",
    "ExtractedCell",
    "ExtractedTable",
    "ExtractionStatus",
    "IngestedArtifact",
    "IngestedPage",
    "IngestionError",
    "IngestionLimits",
    "MalformedDocumentError",
    "PageTableExtraction",
    "SourceMetadata",
    "TableExtractionStatus",
    "TextMatch",
    "UnsupportedDocumentError",
    "artifact_id",
    "build_search_text",
    "check_citation_artifact",
    "extract_page_tables",
    "find_text",
    "fixture_store",
    "ingest_and_store",
    "ingest_pdf",
    "ingest_pdf_bytes",
    "is_valid_sha256",
    "normalize_quote",
    "page_contains",
    "runtime_store",
    "sha256_bytes",
    "sha256_text",
    "to_source_artifact",
]
