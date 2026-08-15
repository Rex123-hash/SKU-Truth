"""Evaluation cases, ground truth, and the prediction shape scored against them.

Ground truth is human-reviewed and lives in a manifest. Predictions are supplied to
the scorer — this package never executes a pipeline and never reaches a network.

`CasePrediction` is deliberately *not* a `GoldenRecord`. The frozen contract makes an
unsupported acceptance impossible to construct, which is exactly what we want in
production and exactly what would make the unsupported-claim rate unmeasurable. So
the scorer takes a looser shape that can represent output the contract would reject:
raw candidate output, an ablation, or a baseline that obeys none of our rules. A
contract-valid record converts into it via `prediction_from_golden_record`.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import (
    Applicability,
    AttributeStatus,
    AttributeValue,
    ConditionSet,
    GoldenRecord,
    IdentityDisposition,
    IdentityScope,
    ProductInput,
    RunProvenance,
    SupportGrade,
    WithheldReason,
)


class Split(StrEnum):
    """Which pool a case belongs to.

    `DEV` is for looking at, debugging against, and iterating on. `LOCKED_TEST` is for
    final reported numbers, and its truth is not edited because the system did badly
    on it. That is process discipline, not access control — see data/eval/README.md.
    """

    DEV = "DEV"
    LOCKED_TEST = "LOCKED_TEST"


class ReviewStatus(StrEnum):
    """How much human scrutiny a case's truth has had."""

    SYNTHETIC = "SYNTHETIC"  # structural fixture; never a benchmark claim
    DRAFT = "DRAFT"  # labelled once, not yet verified
    REVIEWED = "REVIEWED"  # labelled and independently verified against the artifact


class CaseOutcome(StrEnum):
    """What happened when the system was run against a case.

    Anything other than `SCORED` is a failure that still appears in the report. A case
    that crashed is not quietly dropped, because dropping it would flatter every rate
    that follows.
    """

    SCORED = "SCORED"
    MISSING_PREDICTION = "MISSING_PREDICTION"
    EXECUTION_ERROR = "EXECUTION_ERROR"
    REPLAY_MISS = "REPLAY_MISS"
    INVALID_OUTPUT = "INVALID_OUTPUT"


class CitationOutcome(StrEnum):
    """Whether an accepted claim's citation held up.

    `NOT_EVALUATED` is a first-class result, not a soft pass. Full citation validity
    needs artifact ingestion and span verification, which do not exist yet; scoring a
    check we cannot perform as "valid" would manufacture a number.
    """

    VALID = "VALID"
    INVALID = "INVALID"
    NOT_EVALUATED = "NOT_EVALUATED"


# ---------------------------------------------------------------------------------
# Ground truth
# ---------------------------------------------------------------------------------


class ExpectedEvidence(BaseModel):
    """The artifact and span a reviewer confirmed supports the expected value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str = Field(min_length=1)
    artifact_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    page: int | None = Field(default=None, ge=1)
    quote: str | None = None
    identity_scope: IdentityScope | None = None

    @property
    def is_sufficient_for_citation_scoring(self) -> bool:
        """Whether this fixture carries enough to judge a citation at all.

        Without a hash and a page there is nothing to check, and the honest result is
        `NOT_EVALUATED`.
        """
        return self.artifact_sha256 is not None and self.page is not None


class ExpectedIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    disposition: IdentityDisposition
    exact_mpn: str | None = Field(
        default=None, description="Required when the disposition is EXACT"
    )
    missing_discriminators: tuple[str, ...] = Field(
        default=(), description="e.g. ('Rated control supply voltage',)"
    )
    notes: str | None = None

    @model_validator(mode="after")
    def _exact_truth_names_its_reference(self) -> ExpectedIdentity:
        if self.disposition is IdentityDisposition.EXACT and not (
            self.exact_mpn and self.exact_mpn.strip()
        ):
            raise ValueError(
                "ground truth of EXACT must name the exact MPN; otherwise there is "
                "nothing to check a prediction against"
            )
        return self


class ExpectedAttribute(BaseModel):
    """The reviewed truth for one ETIM feature on one case."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_feature_id: str = Field(pattern=r"^EF\d{6}$")
    applicability: Applicability = Applicability.APPLICABLE
    buyer_critical: bool = False

    value: AttributeValue | None = None
    conditions: ConditionSet = Field(default_factory=ConditionSet)

    expected_status: AttributeStatus | None = Field(
        default=None,
        description="Set when one outcome is required. Left None when both accepting "
        "and withholding are defensible, so the case does not punish either.",
    )
    acceptable_withheld_reasons: tuple[WithheldReason, ...] = Field(
        default=(), description="Reasons a withholding is considered correct here"
    )
    evidence: ExpectedEvidence | None = None
    notes: str | None = None

    @model_validator(mode="after")
    def _truth_is_internally_consistent(self) -> ExpectedAttribute:
        if self.applicability is Applicability.NOT_APPLICABLE and self.value is not None:
            raise ValueError(
                f"{self.etim_feature_id} is NOT_APPLICABLE but carries an expected value"
            )
        if self.expected_status is AttributeStatus.ACCEPTED and self.value is None:
            raise ValueError(
                f"{self.etim_feature_id} expects ACCEPTED but records no expected value"
            )
        return self

    @property
    def condition_key(self) -> tuple:
        """Identity of the (feature, operating point) this truth is about."""
        return (self.etim_feature_id, self.conditions.key())

    @property
    def is_judgeable(self) -> bool:
        """Whether a predicted value can be scored right or wrong against this.

        Truth that records no value cannot judge one. Such a row still shapes
        coverage and applicability, but it never enters the precision denominator.
        """
        return self.value is not None


class EvalCase(BaseModel):
    """One product input plus its human-reviewed ground truth."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    split: Split
    input: ProductInput

    manufacturer: str = Field(min_length=1)
    product_family_id: str = Field(
        min_length=1,
        description="Grouping key for splitting. Every case of one family must sit in "
        "the same split, or development leaks into the locked test.",
    )
    etim_class_id: str | None = Field(default=None, pattern=r"^EC\d{6}$")

    expected_identity: ExpectedIdentity
    expected_attributes: tuple[ExpectedAttribute, ...] = ()

    review_status: ReviewStatus = ReviewStatus.DRAFT
    reviewed_by: str | None = None
    license_status: str | None = Field(
        default=None, description="Redistribution status of the source artifact"
    )
    notes: str | None = None

    @model_validator(mode="after")
    def _no_duplicate_truth_for_one_operating_point(self) -> EvalCase:
        seen: set[tuple] = set()
        for attr in self.expected_attributes:
            if attr.condition_key in seen:
                raise ValueError(
                    f"case {self.case_id} states truth twice for {attr.etim_feature_id} "
                    f"at the same operating point; one of them must be wrong"
                )
            seen.add(attr.condition_key)
        return self

    @property
    def is_synthetic(self) -> bool:
        return self.review_status is ReviewStatus.SYNTHETIC

    def attribute(self, feature_id: str) -> ExpectedAttribute | None:
        for attr in self.expected_attributes:
            if attr.etim_feature_id == feature_id:
                return attr
        return None


# ---------------------------------------------------------------------------------
# Predictions
# ---------------------------------------------------------------------------------


class PredictedCitation(BaseModel):
    """What a prediction claims supports an accepted value."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str | None = None
    artifact_sha256: str | None = None
    page: int | None = None
    quote: str | None = None
    identity_scope: IdentityScope | None = None
    span_verified: bool | None = Field(
        default=None,
        description="Whether the span was mechanically located. None means the "
        "producer did not say, which is scored as unverified, never as verified.",
    )


class PredictedAttribute(BaseModel):
    """One attribute as the system under evaluation reported it.

    Looser than `ProductAttribute` on purpose — it must be able to represent output
    the frozen contract would reject, so that a baseline or an ablation can be scored
    with exactly the same code.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_feature_id: str = Field(pattern=r"^EF\d{6}$")
    status: AttributeStatus
    value: AttributeValue | None = None
    bound_conditions: ConditionSet = Field(default_factory=ConditionSet)
    applicability: Applicability = Applicability.UNKNOWN
    support_grade: SupportGrade | None = None
    withheld_reason: WithheldReason | None = None
    has_verified_evidence: bool = Field(
        default=False,
        description="Whether a verified span backs this value. Defaults to False so "
        "a producer that says nothing is treated as unsupported.",
    )
    citation: PredictedCitation | None = None

    @property
    def is_accepted(self) -> bool:
        return self.status is AttributeStatus.ACCEPTED


class CasePrediction(BaseModel):
    """The system's output for one case, plus how it was produced."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str = Field(min_length=1)
    outcome: CaseOutcome = CaseOutcome.SCORED

    identity_disposition: IdentityDisposition | None = None
    identity_mpn: str | None = None
    attributes: tuple[PredictedAttribute, ...] = ()

    provenance: RunProvenance | None = None
    interaction_count: int = Field(default=0, ge=0)
    provider_latency_seconds: tuple[float, ...] = ()
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    provider_reported_cost: float | None = None
    currency: str | None = None

    evaluation_seconds: float | None = Field(
        default=None,
        ge=0.0,
        description="Wall time to produce this prediction. Distinct from provider "
        "latency: replaying a cassette is fast and says nothing about the provider.",
    )
    error_message: str | None = None

    @model_validator(mode="after")
    def _failures_explain_themselves(self) -> CasePrediction:
        if self.outcome is not CaseOutcome.SCORED and not self.error_message:
            raise ValueError(f"outcome {self.outcome} requires an error_message")
        return self

    @property
    def succeeded(self) -> bool:
        return self.outcome is CaseOutcome.SCORED

    def attribute(self, feature_id: str) -> PredictedAttribute | None:
        for attr in self.attributes:
            if attr.etim_feature_id == feature_id:
                return attr
        return None


def prediction_from_golden_record(
    record: GoldenRecord, *, case_id: str, evaluation_seconds: float | None = None
) -> CasePrediction:
    """Adapt contract-valid output into the scorer's shape.

    `has_verified_evidence` is read from the record's own licensing evidence, so a
    `GoldenRecord` scores as supported for the reason the contract already enforced,
    not because the adapter assumed it.
    """
    attributes = tuple(
        PredictedAttribute(
            etim_feature_id=attr.etim_feature_id,
            status=attr.status,
            value=attr.value,
            bound_conditions=attr.bound_conditions,
            applicability=attr.applicability,
            support_grade=attr.support_grade,
            withheld_reason=attr.withheld_reason,
            has_verified_evidence=bool(attr.licensing_evidence),
            citation=_citation_from_attribute(attr),
        )
        for attr in record.attributes
    )
    return CasePrediction(
        case_id=case_id,
        identity_disposition=record.identity.disposition,
        identity_mpn=record.identity.mpn_normalized,
        attributes=attributes,
        provenance=record.provenance,
        interaction_count=record.cost.model_calls,
        input_tokens=record.cost.input_tokens or None,
        output_tokens=record.cost.output_tokens or None,
        evaluation_seconds=evaluation_seconds,
    )


def _citation_from_attribute(attr) -> PredictedCitation | None:
    evidence = attr.licensing_evidence
    if not evidence:
        return None
    best = evidence[0]
    return PredictedCitation(
        artifact_id=best.artifact.artifact_id,
        artifact_sha256=best.artifact.sha256,
        page=best.locator.page,
        quote=best.raw_fragment,
        identity_scope=best.identity_scope,
        span_verified=best.may_support_accepted_value,
    )
