"""The generic claim, the evidence unit, and the verification outcome.

`ProductClaim` is deliberately vocabulary-agnostic. It reuses the frozen `AttributeValue`
and `ConditionSet` contracts but knows nothing about ETIM classes, and nothing about
Unilog LOV labels either. The competition-facing vocabulary is now Unilog; the engine that
decides whether a fact is supported must not have to change when the vocabulary does. An
adapter turns an ETIM-shaped `ExtractionCandidate` into a claim; a later adapter will do
the same for a Unilog-shaped one.

There is **no confidence field and no support grade** here. Verification answers one
question — does the artifact support this claim — and answers it yes or no with a reason.
Grading depends on authoritativeness and scope as well, and belongs to adjudication.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from skutruth.contracts import AttributeValue, ConditionSet, EvidenceVerification


class VerificationFailure(StrEnum):
    """Why a claim was not verified. Never a bare "unverified".

    This is a *reason* vocabulary, not a second status enum: the status stays the frozen
    `EvidenceVerification`.
    """

    ARTIFACT_MISMATCH = "ARTIFACT_MISMATCH"
    ARTIFACT_UNREADABLE = "ARTIFACT_UNREADABLE"
    PAGE_NOT_FOUND = "PAGE_NOT_FOUND"
    SOURCE_FRAGMENT_NOT_FOUND = "SOURCE_FRAGMENT_NOT_FOUND"
    AMBIGUOUS_MATCH = "AMBIGUOUS_MATCH"
    VALUE_NOT_SUPPORTED = "VALUE_NOT_SUPPORTED"
    UNIT_NOT_SUPPORTED = "UNIT_NOT_SUPPORTED"
    OPERATOR_MISMATCH = "OPERATOR_MISMATCH"
    CONDITION_NOT_SUPPORTED = "CONDITION_NOT_SUPPORTED"
    TABLE_STRUCTURE_UNRESOLVED = "TABLE_STRUCTURE_UNRESOLVED"
    PRODUCT_REFERENCE_MISMATCH = "PRODUCT_REFERENCE_MISMATCH"
    PRODUCT_SCOPE_NOT_SUPPORTED = "PRODUCT_SCOPE_NOT_SUPPORTED"
    UNSUPPORTED_VALUE_KIND = "UNSUPPORTED_VALUE_KIND"


class EvidenceMode(StrEnum):
    """Which kind of coherent source unit carried the evidence."""

    TEXT_UNIT = "TEXT_UNIT"
    TABLE_UNIT = "TABLE_UNIT"
    NONE = "NONE"


class TextMatchMode(StrEnum):
    """How the source fragment was located.

    `NORMALIZED` covers representation-only differences — NBSP, exotic spaces, Unicode
    form. It is **not** OCR tolerance: no character is ever substituted and no number is
    ever altered, so a normalized hit is as exact as a literal one. That is why both map
    to `EXACT_SPAN` and why `FUZZY_OCR_SPAN` is never emitted while the system does no OCR.
    """

    LITERAL = "LITERAL"
    NORMALIZED = "NORMALIZED"
    TABLE_CELL = "TABLE_CELL"


class ProductClaim(BaseModel):
    """One proposed fact about one exact product, with where it is claimed to come from.

    Vocabulary-agnostic: `key` is an opaque identifier — an ETIM feature id today, a
    Unilog attribute label later — and nothing in the verifier interprets it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1, description="Opaque feature/attribute id")
    label: str | None = Field(default=None, description="Human-facing name, display only")
    value: AttributeValue
    conditions: ConditionSet = Field(default_factory=ConditionSet)

    exact_mpn: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int = Field(ge=1)
    source_fragment: str = Field(
        min_length=1,
        description="The model's quote. A locator hint only — never the evidence itself.",
    )


class EvidenceUnit(BaseModel):
    """One coherent region of the artifact that must support the whole claim alone.

    The one-evidence-unit rule lives here. A text unit is a single source line; a table
    unit is one body row plus the header cells structurally above it. Value and every
    condition must be supported *within one unit*, so support cannot be assembled from a
    number in one paragraph and a qualifier in another.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: EvidenceMode
    text: str = Field(description="The actual artifact text of this unit")
    start: int | None = Field(default=None, description="Offset into the page raw text")
    end: int | None = None
    table_index: int | None = None
    row_index: int | None = None
    column_index: int | None = None
    bbox: tuple[float, float, float, float] | None = None


class ConditionOutcome(BaseModel):
    """Whether one bound qualifier was supported, and how.

    `failure` is decided by the comparison itself and carried here as a typed value.
    `detail` explains it for a human and is never parsed to recover the reason — a
    classification that depends on the wording of its own prose breaks the moment the
    wording is improved.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: str
    value: str
    supported: bool
    failure: VerificationFailure | None = None
    detail: str = ""


class VerificationOutcome(BaseModel):
    """The verifier's decision about one claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str
    exact_mpn: str
    value: AttributeValue
    conditions: ConditionSet

    artifact_sha256: str
    page_number: int
    status: EvidenceVerification
    failure: VerificationFailure | None = None
    failure_detail: str = ""

    evidence_mode: EvidenceMode = EvidenceMode.NONE
    match_mode: TextMatchMode | None = None
    #: What the model said it read.
    proposed_fragment: str = ""
    #: What the artifact actually says. Both are kept: a divergence between them is
    #: itself a finding, and only the second one is evidence.
    matched_text: str = ""
    evidence: EvidenceUnit | None = None
    condition_outcomes: tuple[ConditionOutcome, ...] = ()
    value_detail: str = ""
    verifier_version: str

    @property
    def verified(self) -> bool:
        return self.status is EvidenceVerification.EXACT_SPAN

    def summary(self) -> str:
        if self.verified:
            return f"{self.key}: EXACT_SPAN via {self.evidence_mode.value} p{self.page_number}"
        reason = self.failure.value if self.failure else "UNVERIFIED"
        return f"{self.key}: {reason}"


__all__ = [
    "ConditionOutcome",
    "EvidenceMode",
    "EvidenceUnit",
    "ProductClaim",
    "TextMatchMode",
    "VerificationFailure",
    "VerificationOutcome",
]
