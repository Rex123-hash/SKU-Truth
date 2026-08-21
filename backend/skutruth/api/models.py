"""The frontend-facing contract.

Deliberately **not** the internal models. A judge-facing UI should not have to know what
a `SourceBoundHtmlAttributeCandidate` is, and the internal types carry things that must
never cross the wire: stored file paths, whole HTML documents, cassette internals.

Every field here is either a value a person reads on screen or a typed state the UI
branches on. The four questions the demo exists to answer -- what we know, what AI
proposed, what we verified, what we refused -- are separate top-level shapes, so a UI
cannot accidentally render a proposal as a fact.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

#: Evidence excerpts are pointers, not content. Long enough to recognise the fragment,
#: short enough that the response is never a redistribution of the source document.
MAX_EXCERPT = 200


class ExecutionMode(StrEnum):
    """How the server answered. Never inferred, never silently downgraded."""

    #: Deterministic stages plus stored evidence. Zero external network calls.
    DEMO_REPLAY = "DEMO_REPLAY"
    #: Live providers, existing budgets. A live failure stays a typed failure.
    LIVE = "LIVE"


class Stage(StrEnum):
    """The pipeline stages a judge watches, in order."""

    NORMALIZATION = "NORMALIZATION"
    CLASSIFICATION = "CLASSIFICATION"
    DISCOVERY = "DISCOVERY"
    ACQUISITION = "ACQUISITION"
    IDENTITY = "IDENTITY"
    AI_PROPOSAL = "AI_PROPOSAL"
    VERIFICATION = "VERIFICATION"
    DELIVERY_MAPPING = "DELIVERY_MAPPING"


class StageStatus(StrEnum):
    """A UI-level status. The typed internal reason travels beside it, never instead."""

    SUCCESS = "SUCCESS"
    REVIEW = "REVIEW"
    WITHHELD = "WITHHELD"
    BLOCKED = "BLOCKED"
    NOT_RUN = "NOT_RUN"


class EvidenceBasis(StrEnum):
    """Where a stage's reported outcome comes from.

    This is the field that keeps the demo honest. `RECORDED_OBSERVATION` means a person
    watched it happen in a live run and wrote it down; it is *not* replayable, and the UI
    should say so rather than implying the server just re-derived it.
    """

    #: Recomputed now from committed code and committed data.
    DETERMINISTIC = "DETERMINISTIC"
    #: Re-derived now from a recorded provider interaction.
    STORED_CASSETTE = "STORED_CASSETTE"
    #: Re-derived now from a stored immutable artifact.
    STORED_ARTIFACT = "STORED_ARTIFACT"
    #: Observed during a live run and recorded by the operator. Not replayable.
    RECORDED_OBSERVATION = "RECORDED_OBSERVATION"


class TimelineEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: Stage
    status: StageStatus
    #: The internal typed reason, verbatim (e.g. `EXACT_PRODUCT_MPN`), or "".
    reason: str = ""
    detail: str = ""
    evidence: EvidenceBasis


class ProductSummary(BaseModel):
    """The messy input, exactly as the organizer supplied it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    row_number: int | None = None
    mpn: str
    raw_description: str = ""
    raw_manufacturer: str = ""
    raw_brand_signals: tuple[str, ...] = ()


class NormalizationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    manufacturer: str | None = None
    manufacturer_decision: str
    manufacturer_reason: str
    manufacturer_authority: str | None = None
    brand: str | None = None
    brand_decision: str
    brand_reason: str


class ClassificationView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    family: str | None = None
    decision: str
    reason: str = ""
    cues: tuple[str, ...] = ()
    #: The official delivery taxonomy path, populated only where an organizer example
    #: authorises it. Blank is the correct and common answer.
    delivery_classpath: str | None = None
    delivery_decision: str | None = None


class SourceView(BaseModel):
    """What discovery found, and whether anything was safely acquired."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    discovery_status: StageStatus
    results_returned: int = 0
    exact_candidates: int = 0
    authority: str | None = None
    relevance: str | None = None
    source_kind: str | None = None
    discovery_url: str | None = None
    final_url: str | None = None
    artifact_kind: str | None = None
    artifact_sha256: str | None = None
    #: A typed blocker code when acquisition did not produce an artifact.
    blocker: str | None = None
    blocker_detail: str = ""


class IdentityView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    decision: str
    identity_scope: str | None = None
    covers_mpn: str | None = None
    reason: str = ""


class AiView(BaseModel):
    """What the model did -- never what it established."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    ran: bool
    model: str | None = None
    profile_id: str | None = None
    proposal_count: int = 0
    source_bound_count: int = 0
    rejected_count: int = 0
    replayed: bool = False
    not_run_reason: str = ""


class EvidenceLocatorView(BaseModel):
    """Enough to point a reviewer at the evidence. Never the document itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    jsonld_block_index: int | None = None
    json_pointer: str | None = None
    element_index: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    excerpt: str = Field(default="", max_length=MAX_EXCERPT)


class ProposedAttribute(BaseModel):
    """A model proposal, bound to a locator. Not a fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: str
    label: str
    proposed_value: str
    proposed_uom: str = ""
    value_kind: str | None = None
    locator: EvidenceLocatorView | None = None


class VerifiedAttribute(BaseModel):
    """A manufacturer fact, mechanically re-derived from the stored source."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: str
    label: str
    value: str
    uom: str | None = None
    #: What the source itself says, beside what was proposed -- this comparison is what
    #: the demo is about.
    source_label: str
    source_value: str
    source_uom: str = ""
    locator: EvidenceLocatorView
    status: str
    reason: str
    authority: str
    decision: str
    unilog_mapping_status: str
    delivery_eligible: bool = False


class WithheldAttribute(BaseModel):
    """A proposal that survived binding and still did not become a fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: str
    label: str
    proposed_value: str
    proposed_uom: str = ""
    source_label: str = ""
    source_value: str = ""
    locator: EvidenceLocatorView | None = None
    status: str
    reason: str
    detail: str = ""


class AttributesView(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    proposed: tuple[ProposedAttribute, ...] = ()
    verified: tuple[VerifiedAttribute, ...] = ()
    withheld: tuple[WithheldAttribute, ...] = ()


class DeliveryView(BaseModel):
    """Whether anything is authorised for the official Unilog delivery format."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    mapped_count: int = 0
    mapping_status: str
    unauthorized_reason: str = ""


class ProductDetail(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    mode: ExecutionMode
    headline: str
    product: ProductSummary
    normalization: NormalizationView
    classification: ClassificationView
    source: SourceView
    identity: IdentityView
    ai: AiView
    attributes: AttributesView
    delivery: DeliveryView
    timeline: tuple[TimelineEntry, ...]


class ProductCard(BaseModel):
    """One row of the demo list."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    mpn: str
    manufacturer: str
    headline: str
    outcome: str
    verified_count: int = 0
    withheld_count: int = 0


class DemoIndex(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: ExecutionMode
    products: tuple[ProductCard, ...]
    metrics: dict[str, int]


class HealthResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    status: str
    mode: ExecutionMode
    version: str
    demo_cases: int
    #: Stated explicitly so a reader never has to infer it from the mode name.
    external_calls: bool


class AnalyzeRequest(BaseModel):
    """An organizer-style row. The client supplies data, never a URL and never a domain."""

    model_config = ConfigDict(extra="forbid")

    mpn: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=500)
    manufacturer: str = Field(default="", max_length=200)
    e1_brand: str = Field(default="", max_length=200)
    unilog_brand: str = Field(default="", max_length=200)
    dib_brand: str = Field(default="", max_length=200)


class SchemaResponse(BaseModel):
    """Facts about the delivery contract, for the UI to render honestly."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    delivery_columns: int
    attribute_triplets: int
    organizer_rows: int
    organizer_examples_populated: int
    stages: tuple[str, ...]
    stage_statuses: tuple[str, ...]
    evidence_bases: tuple[str, ...]
    trust_note: str


__all__ = [
    "MAX_EXCERPT",
    "AiView",
    "AnalyzeRequest",
    "AttributesView",
    "ClassificationView",
    "DeliveryView",
    "DemoIndex",
    "EvidenceBasis",
    "EvidenceLocatorView",
    "ExecutionMode",
    "HealthResponse",
    "IdentityView",
    "NormalizationView",
    "ProductCard",
    "ProductDetail",
    "ProductSummary",
    "ProposedAttribute",
    "SchemaResponse",
    "SourceView",
    "Stage",
    "StageStatus",
    "TimelineEntry",
    "VerifiedAttribute",
    "WithheldAttribute",
]
