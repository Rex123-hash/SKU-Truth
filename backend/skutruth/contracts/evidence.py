"""Evidence, evidence clusters, and conflicts.

FROZEN CONTRACT — see contracts/README.md before changing anything here.

The central idea: corroboration is counted over *independent clusters*, not over
URLs. Three distributors that copied one manufacturer datasheet are one
observation. `EvidenceCluster` is the unit that adjudication counts.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .enums import ConflictCause, EvidenceModality, ResolvedBy, SkuSpecificity, SourceType
from .value import AttributeValue


class DocumentLocator(BaseModel):
    """Where inside a document the quote lives. Drives the "open at page N" affordance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int | None = Field(default=None, ge=1, description="1-indexed PDF page")
    section: str | None = Field(default=None, description="Heading or table caption")
    char_start: int | None = Field(default=None, ge=0, description="Offset into extracted text")
    char_end: int | None = Field(default=None, ge=0)

    def human(self) -> str:
        bits: list[str] = []
        if self.page is not None:
            bits.append(f"p.{self.page}")
        if self.section:
            bits.append(self.section)
        return " · ".join(bits) if bits else "location not recorded"


class Evidence(BaseModel):
    """One extracted observation of one attribute value from one document region.

    `quote` is mandatory and must be verbatim source text. An Evidence without a
    quote cannot be shown to a reviewer, and an attribute value with no quotable
    support is by definition unsupported.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str
    source_url: str
    source_type: SourceType
    publisher: str | None = None
    document_sha256: str = Field(description="Content address of the stored artifact")
    locator: DocumentLocator = Field(default_factory=DocumentLocator)
    quote: str = Field(min_length=1, description="Verbatim text supporting the value")
    modality: EvidenceModality
    sku_specificity: SkuSpecificity
    retrieved_at: datetime

    # Reproducibility trail: enough to re-run this exact extraction.
    extractor_model: str
    prompt_version: str
    run_id: str


class EvidenceCluster(BaseModel):
    """A set of Evidence judged to be non-independent (copies of one another).

    `members` is never empty. `independence_note` explains, in one sentence a
    reviewer can read, why these were collapsed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cluster_id: str
    representative_value: AttributeValue
    members: list[Evidence] = Field(min_length=1)
    independence_note: str | None = None

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def best_member(self) -> Evidence:
        """The member a reviewer should be shown first: most specific, then most structured."""
        spec_rank = {
            SkuSpecificity.EXACT_SKU: 0,
            SkuSpecificity.FAMILY: 1,
            SkuSpecificity.RANGE: 2,
        }
        mod_rank = {
            EvidenceModality.SPEC_TABLE: 0,
            EvidenceModality.SPEC_LINE: 1,
            EvidenceModality.PROSE: 2,
            EvidenceModality.IMAGE_OCR: 3,
            EvidenceModality.MARKETING: 4,
        }
        return min(
            self.members,
            key=lambda e: (spec_rank[e.sku_specificity], mod_rank[e.modality]),
        )


class Conflict(BaseModel):
    """A recorded disagreement between clusters, classified by cause.

    Only `cause == FACTUAL` is a genuine source disagreement; the rest are
    resolved deterministically and retained for the audit trail.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cause: ConflictCause
    cluster_ids: list[str] = Field(min_length=2)
    explanation: str
    resolution: str | None = None
    resolved_by: ResolvedBy = ResolvedBy.UNRESOLVED
