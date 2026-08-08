"""Product identity, attributes, and the golden record.

FROZEN CONTRACT — see contracts/README.md before changing anything here.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import AttributeStatus, EtimFeatureType, IdentityKind, RunMode
from .evidence import Conflict, EvidenceCluster
from .value import AttributeValue


class ProductInput(BaseModel):
    """The minimal input the challenge specifies. Everything else is derived."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brand: str = Field(min_length=1)
    mpn: str = Field(min_length=1)
    description: str | None = None
    supplier_sku: str | None = Field(default=None, description="Caller's internal identifier")


class VariantAxis(BaseModel):
    """A dimension along which members of a resolved FAMILY differ.

    This is the machine-readable form of "we cannot answer that until you tell us
    which variant". Surfacing it turns an abstention into a single precise question.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_feature_id: str | None = None
    name: str = Field(min_length=1, description="e.g. 'Rated control supply voltage'")
    observed_values: list[str] = Field(default_factory=list)
    example_mpns: list[str] = Field(default_factory=list)


class ProductIdentity(BaseModel):
    """What the input actually refers to.

    A FAMILY resolution is not a failure — it is the correct answer for an input
    like `LC1D18`, which is a TeSys D family stem rather than an orderable SKU.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: IdentityKind
    brand_normalized: str | None = None
    mpn_normalized: str | None = None
    canonical_name: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=1, description="Shown to the reviewer verbatim")
    variant_axes: list[VariantAxis] = Field(default_factory=list)
    candidate_mpns: list[str] = Field(
        default_factory=list, description="Orderable SKUs under a FAMILY, or rival readings"
    )

    @model_validator(mode="after")
    def _family_declares_variance(self) -> ProductIdentity:
        if self.kind is IdentityKind.FAMILY and not (self.variant_axes or self.candidate_mpns):
            raise ValueError(
                "a FAMILY identity must declare at least one variant axis or candidate MPN; "
                "otherwise it is indistinguishable from an EXACT_SKU"
            )
        return self


class ConfidenceFactors(BaseModel):
    """The decomposition behind a confidence number.

    Every term is displayed in the Evidence Drawer. No language model produces any
    of these values; they are computed from measurable properties of the evidence.
    Until the held-out evaluation set is large enough to calibrate against, the
    aggregate is documented as an uncalibrated ordinal score — see `calibrated`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    authority_prior: float = Field(ge=0.0, le=1.0)
    modality: float = Field(ge=0.0, le=1.0)
    sku_specificity: float = Field(ge=0.0, le=1.0)
    independent_cluster_agreement: float = Field(ge=0.0, le=1.0)
    etim_validation: float = Field(ge=0.0, le=1.0)
    recency: float = Field(ge=0.0, le=1.0)

    calibrated: bool = Field(
        default=False,
        description="True only when the aggregate was mapped through a fitted "
        "calibration curve on held-out data. False means ordinal score, not probability.",
    )


class ProductAttribute(BaseModel):
    """One attribute on the golden record, with everything needed to defend it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_feature_id: str = Field(pattern=r"^EF\d{6}$")
    name: str = Field(min_length=1)
    feature_type: EtimFeatureType
    expected_unit: str | None = Field(default=None, description="Unit ETIM mandates for the class")

    value: AttributeValue | None = None
    status: AttributeStatus
    confidence: float = Field(ge=0.0, le=1.0)
    confidence_factors: ConfidenceFactors | None = None

    evidence_clusters: list[EvidenceCluster] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)

    @model_validator(mode="after")
    def _abstention_carries_no_value(self) -> ProductAttribute:
        abstained = {AttributeStatus.INSUFFICIENT_EVIDENCE, AttributeStatus.VARIANT_DEPENDENT}
        if self.status in abstained and self.value is not None:
            raise ValueError(f"status {self.status} must not carry a committed value")
        if self.status not in abstained and self.value is None:
            raise ValueError(f"status {self.status} requires a value")
        return self

    @model_validator(mode="after")
    def _committed_values_are_supported(self) -> ProductAttribute:
        # The core invariant of the whole system: no committed value without evidence.
        if self.value is not None and not self.evidence_clusters:
            raise ValueError(
                f"attribute {self.etim_feature_id} commits to a value with no evidence cluster"
            )
        return self

    @model_validator(mode="after")
    def _verified_needs_independent_corroboration(self) -> ProductAttribute:
        if self.status is AttributeStatus.VERIFIED and len(self.evidence_clusters) < 2:
            raise ValueError(
                "VERIFIED requires >=2 independent evidence clusters; "
                "use SINGLE_SOURCE when only one survives independence clustering"
            )
        return self

    @property
    def is_abstention(self) -> bool:
        return self.status in {
            AttributeStatus.INSUFFICIENT_EVIDENCE,
            AttributeStatus.VARIANT_DEPENDENT,
        }


class CommerceContent(BaseModel):
    """Generated copy. Constrained to facts already committed on the record."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = None
    short_description: str | None = None
    long_description: str | None = None
    feature_bullets: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    grounded_feature_ids: list[str] = Field(
        default_factory=list,
        description="Attributes the copy is permitted to reference. Anything outside "
        "this set appearing in the copy is an unsupported claim.",
    )


class RunCost(BaseModel):
    """Measured, never estimated. Absent is better than guessed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    model_calls: int = 0
    search_queries: int = 0
    cache_hits: int = 0
    wall_seconds: float = 0.0


class GoldenRecord(BaseModel):
    """The output of one enrichment run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str
    run_id: str
    run_mode: RunMode = Field(
        description="LIVE or REPLAY. A REPLAY run replays previously recorded real "
        "interactions and is labelled as such wherever it is displayed."
    )
    created_at: datetime

    input: ProductInput
    identity: ProductIdentity
    etim_class_id: str | None = Field(default=None, pattern=r"^EC\d{6}$")
    etim_class_name: str | None = None

    attributes: list[ProductAttribute] = Field(default_factory=list)
    commerce: CommerceContent | None = None
    cost: RunCost = Field(default_factory=RunCost)

    @property
    def committed(self) -> list[ProductAttribute]:
        return [a for a in self.attributes if not a.is_abstention]

    @property
    def abstained(self) -> list[ProductAttribute]:
        return [a for a in self.attributes if a.is_abstention]

    @property
    def completeness(self) -> float:
        """Fraction of ETIM-expected attributes for the class that carry a value.

        The denominator is the class's full expected feature set, so an abstention
        costs completeness exactly as much as a miss. That is deliberate: abstention
        is honest, not free.
        """
        if not self.attributes:
            return 0.0
        return len(self.committed) / len(self.attributes)
