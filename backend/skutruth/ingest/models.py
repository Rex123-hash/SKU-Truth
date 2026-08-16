"""The ingested artifact and its page map.

What this milestone produces is the *versioned source artifact* the trust claim rests
on. It proves one thing precisely:

    these page contents were extracted from this exact artifact.

It proves nothing at all about whether any of that text supports a product attribute.
That is span verification, and it does not exist yet — so nothing here sets
`EvidenceVerification`, and nothing here builds a `ProductAttribute`.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import DiscoveryMethod, IdentityScope, SourceArtifact, SourceType

from .hashing import artifact_id, is_valid_sha256
from .text import TEXT_NORMALIZATION_FORM

#: Bumped when the ingestion pipeline changes in a way that could alter page text.
#: Recorded on every artifact, because a parser upgrade can silently reorder a table
#: and that must be observable rather than inferred.
INGESTION_VERSION = "pdf-ingest@v1"


class ExtractionStatus(StrEnum):
    """What text extraction achieved for a page or a document."""

    TEXT_EXTRACTED = "TEXT_EXTRACTED"
    NO_EXTRACTABLE_TEXT = "NO_EXTRACTABLE_TEXT"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"


class DocumentTextStatus(StrEnum):
    """Document-level assessment, used to decide whether OCR would be needed.

    `OCR_REQUIRED` is a statement about the document, not a promise to do anything
    about it. No OCR runs in this milestone, and recognised text must never be
    presented as though it were extracted from the file.
    """

    TEXT_EXTRACTABLE = "TEXT_EXTRACTABLE"
    PARTIALLY_EXTRACTABLE = "PARTIALLY_EXTRACTABLE"
    OCR_REQUIRED = "OCR_REQUIRED"


class SourceMetadata(BaseModel):
    """What is known about where a document came from.

    `discovery_url` and `final_artifact_url` are separate fields and must stay that
    way. A search result or a landing page is where we *looked*; the artifact URL is
    what we actually read. Collapsing them would let a citation point at a page that
    never contained the evidence.

    Every field is optional because a local fixture legitimately has no URL, and
    inventing one would be fabrication.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    publisher: str | None = None
    final_artifact_url: str | None = Field(
        default=None, description="The URL the bytes actually came from, after redirects"
    )
    discovery_url: str | None = Field(
        default=None, description="Where the artifact was found. Never the evidence URL."
    )
    discovery_method: DiscoveryMethod = DiscoveryMethod.OPERATOR_SUPPLIED
    source_type: SourceType | None = None
    identity_scope: IdentityScope | None = Field(
        default=None, description="Set only when genuinely known; never guessed"
    )
    covers_mpn: str | None = Field(
        default=None, description="The commercial reference this document is about, if stated"
    )
    document_version: str | None = Field(
        default=None, description="The publisher's own revision or date marking"
    )
    original_filename: str | None = None
    retrieved_at: datetime | None = None
    license_note: str | None = Field(
        default=None, description="Redistribution status, for anything considered for commit"
    )

    @model_validator(mode="after")
    def _retrieved_at_is_utc_aware(self) -> SourceMetadata:
        if self.retrieved_at is not None and (
            self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None
        ):
            raise ValueError("retrieved_at must be timezone-aware")
        return self


class IngestedPage(BaseModel):
    """One page, kept whole.

    `page_number` is 1-indexed everywhere outside the parser call itself. Page 1 in a
    citation means page 1 in the PDF a reviewer opens.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int = Field(ge=1)
    raw_text: str = Field(description="Parser output, line endings normalised, nothing else")
    search_text: str = Field(description="Lossy normalised index; never sufficient alone")
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Over raw_text")
    character_count: int = Field(ge=0)
    status: ExtractionStatus
    width_points: float | None = None
    height_points: float | None = None
    warnings: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _character_count_matches(self) -> IngestedPage:
        if self.character_count != len(self.raw_text):
            raise ValueError(
                f"page {self.page_number} reports {self.character_count} characters but "
                f"carries {len(self.raw_text)}"
            )
        return self

    @property
    def has_text(self) -> bool:
        return self.status is ExtractionStatus.TEXT_EXTRACTED


class IngestedArtifact(BaseModel):
    """A document turned into versioned, page-addressable evidence infrastructure."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Over the original bytes")
    media_type: str = "application/pdf"
    byte_size: int = Field(ge=1)
    page_count: int = Field(ge=1)
    pages: tuple[IngestedPage, ...]

    source: SourceMetadata = Field(default_factory=SourceMetadata)
    text_status: DocumentTextStatus
    ingested_at: datetime
    ingestion_version: str = INGESTION_VERSION
    parser_name: str
    parser_version: str
    text_normalization_form: str = TEXT_NORMALIZATION_FORM
    warnings: tuple[str, ...] = ()

    @property
    def artifact_id(self) -> str:
        return artifact_id(self.sha256)

    @model_validator(mode="after")
    def _page_map_is_complete(self) -> IngestedArtifact:
        """Pages must be exactly 1..page_count, once each, in order.

        A gap or a duplicate would mean a citation to page N could land on the wrong
        page, or on nothing.
        """
        if len(self.pages) != self.page_count:
            raise ValueError(
                f"page_count is {self.page_count} but {len(self.pages)} pages are present"
            )
        numbers = [p.page_number for p in self.pages]
        if numbers != list(range(1, self.page_count + 1)):
            raise ValueError(
                "pages must be numbered 1..page_count exactly once each and in order; "
                f"got {numbers[:10]}{'...' if len(numbers) > 10 else ''}"
            )
        return self

    @model_validator(mode="after")
    def _ingested_at_is_utc_aware(self) -> IngestedArtifact:
        if self.ingested_at.tzinfo is None or self.ingested_at.utcoffset() is None:
            raise ValueError("ingested_at must be timezone-aware")
        return self

    def page(self, page_number: int) -> IngestedPage | None:
        if 1 <= page_number <= self.page_count:
            return self.pages[page_number - 1]
        return None

    @property
    def text_bearing_pages(self) -> int:
        return sum(1 for p in self.pages if p.has_text)

    def summary(self) -> str:
        return (
            f"{self.sha256[:12]} · {self.page_count} pages · {self.byte_size:,} bytes · "
            f"{self.text_status.value} · {self.parser_name} {self.parser_version}"
        )


def to_source_artifact(
    artifact: IngestedArtifact,
    *,
    source_type: SourceType | None = None,
    identity_scope: IdentityScope | None = None,
    retrieved_at: datetime | None = None,
) -> SourceArtifact:
    """Adapt an ingested artifact into the frozen `SourceArtifact` contract.

    Only what ingestion defensibly knows is carried across. `source_type` and
    `identity_scope` are not derivable from a PDF's bytes — whether a document is a
    manufacturer datasheet or a distributor page, and whether it covers one reference
    or a family, are judgements about provenance, not facts in the file. They must
    come from source metadata or from the caller, and this function raises rather than
    guessing.

    Nothing here sets any span verification state. Ingestion has proved where the text
    came from, not what it supports.
    """
    resolved_type = source_type or artifact.source.source_type
    if resolved_type is None:
        raise ValueError(
            "source_type is not derivable from document bytes; supply it in "
            "SourceMetadata or to this adapter rather than inventing one"
        )
    resolved_scope = identity_scope or artifact.source.identity_scope
    if resolved_scope is None:
        raise ValueError(
            "identity_scope is not derivable from document bytes; supply it in "
            "SourceMetadata or to this adapter rather than inventing one"
        )
    resolved_retrieved = retrieved_at or artifact.source.retrieved_at or artifact.ingested_at
    final_url = artifact.source.final_artifact_url
    if final_url is None:
        raise ValueError(
            "SourceArtifact requires a final_artifact_url; a locally ingested fixture "
            "with no URL cannot be presented as a retrievable source"
        )

    return SourceArtifact(
        artifact_id=artifact.artifact_id,
        sha256=artifact.sha256,
        final_url=final_url,
        discovery_url=artifact.source.discovery_url,
        discovery_method=artifact.source.discovery_method,
        publisher=artifact.source.publisher,
        source_type=resolved_type,
        media_type=artifact.media_type,
        page_count=artifact.page_count,
        retrieved_at=resolved_retrieved,
        document_version=artifact.source.document_version,
        identity_scope=resolved_scope,
        covers_mpn=artifact.source.covers_mpn,
    )


def is_valid_artifact_sha(value: str) -> bool:
    return is_valid_sha256(value)
