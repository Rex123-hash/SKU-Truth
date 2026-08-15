"""Product identity, attributes, and the golden record.

FROZEN CONTRACT — see contracts/README.md before changing anything here.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .conditions import ConditionCompleteness, ConditionSet
from .coverage import CoverageReport
from .enums import (
    Applicability,
    AttributeStatus,
    EtimFeatureType,
    FamilyInvariance,
    IdentityDisposition,
    IdentityScope,
    RunMode,
    SupportGrade,
    WithheldReason,
)
from .evidence import Conflict, Evidence, EvidenceGroup
from .support import SupportFactors, compute_support_factors, derive_support_grade
from .value import VALUE_KIND_FOR_FEATURE_TYPE, AttributeValue


class ProductInput(BaseModel):
    """The minimal input the challenge specifies. Everything else is derived."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brand: str = Field(min_length=1)
    mpn: str = Field(min_length=1)
    description: str | None = None
    supplier_sku: str | None = Field(default=None, description="Caller's internal identifier")


class VariantAxis(BaseModel):
    """A discriminator that the supplied reference leaves unbound.

    This is the machine-readable form of "we cannot answer that until you tell us
    which variant", and it turns an abstention into one precise question. Options are
    recorded only from evidence, never assumed.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_feature_id: str | None = None
    name: str = Field(min_length=1, description="e.g. 'Rated control supply voltage'")
    observed_options: tuple[str, ...] = ()
    example_mpns: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = Field(
        default=(), description="Evidence that established this axis exists"
    )


class ProductIdentity(BaseModel):
    """What the input was determined to refer to.

    `FAMILY_OR_INCOMPLETE_REFERENCE` asserts only that a discriminator is unbound. It
    does not assert that the reference is unorderable — some channels do list a family
    stem or configurable base reference as a purchasable record, and claiming otherwise
    would be an inference we cannot support.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    disposition: IdentityDisposition
    brand_normalized: str | None = None
    mpn_normalized: str | None = None
    canonical_name: str | None = None
    reasoning: str = Field(min_length=1, description="Shown to the reviewer verbatim")

    variant_axes: tuple[VariantAxis, ...] = ()
    candidate_mpns: tuple[str, ...] = Field(
        default=(), description="Exact child references, or rival readings when CONTRADICTORY"
    )
    resolved_from: str | None = Field(
        default=None, description="Prior MPN this run resolved from, after a variant selection"
    )
    evidence_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _exact_identity_has_a_canonical_reference(self) -> ProductIdentity:
        """EXACT means we know which orderable reference this is. Say which.

        Non-exact dispositions are not forced to invent one: an unresolved family
        stem or an unknown reference legitimately has no canonical exact MPN.
        """
        if self.disposition is IdentityDisposition.EXACT and not (
            self.mpn_normalized and self.mpn_normalized.strip()
        ):
            raise ValueError(
                "EXACT identity requires a normalized MPN; an exact disposition without "
                "a canonical product reference asserts more than it can name"
            )
        return self

    @model_validator(mode="after")
    def _incomplete_reference_names_its_discriminator(self) -> ProductIdentity:
        if self.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE and not (
            self.variant_axes or self.candidate_mpns
        ):
            raise ValueError(
                "FAMILY_OR_INCOMPLETE_REFERENCE must name the unbound discriminator "
                "(a variant axis) or the candidate exact references; otherwise the "
                "disposition is unfalsifiable"
            )
        return self

    @model_validator(mode="after")
    def _contradictory_shows_the_rival_readings(self) -> ProductIdentity:
        if self.disposition is IdentityDisposition.CONTRADICTORY and len(self.candidate_mpns) < 2:
            raise ValueError("CONTRADICTORY must list at least two rival readings")
        return self

    @property
    def is_exact(self) -> bool:
        return self.disposition is IdentityDisposition.EXACT


class ProductAttribute(BaseModel):
    """One ETIM feature on the record, with everything needed to defend or refuse it.

    Three independent axes, deliberately not collapsed into one enum:
      * `applicability` — does this feature apply to this product at all?
      * `status`        — did we accept a value?
      * `support_grade` / `withheld_reason` — how strong, or why not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_feature_id: str = Field(pattern=r"^EF\d{6}$")
    name: str = Field(min_length=1)
    feature_type: EtimFeatureType
    expected_unit: str | None = Field(default=None, description="Unit ETIM mandates for the class")
    buyer_critical: bool = Field(
        default=False, description="In the hand-reviewed buyer-critical subset for this class"
    )

    applicability: Applicability = Applicability.UNKNOWN
    status: AttributeStatus
    value: AttributeValue | None = None
    bound_conditions: ConditionSet = Field(default_factory=ConditionSet)
    family_invariance: FamilyInvariance = FamilyInvariance.NOT_REQUIRED

    support_grade: SupportGrade | None = None
    support_factors: SupportFactors | None = None
    withheld_reason: WithheldReason | None = None

    evidence_groups: tuple[EvidenceGroup, ...] = ()
    conflicts: tuple[Conflict, ...] = ()

    # ---- invariants ----------------------------------------------------------

    @model_validator(mode="after")
    def _status_and_value_agree(self) -> ProductAttribute:
        if self.status is AttributeStatus.ACCEPTED and self.value is None:
            raise ValueError("ACCEPTED requires a value")
        if self.status is AttributeStatus.WITHHELD and self.value is not None:
            raise ValueError("WITHHELD must not carry a value")
        return self

    @model_validator(mode="after")
    def _withheld_explains_itself(self) -> ProductAttribute:
        if self.status is AttributeStatus.WITHHELD and self.withheld_reason is None:
            raise ValueError("WITHHELD requires a withheld_reason; the user must know why")
        if self.status is AttributeStatus.ACCEPTED and self.withheld_reason is not None:
            raise ValueError("ACCEPTED must not carry a withheld_reason")
        return self

    @model_validator(mode="after")
    def _not_applicable_is_consistent(self) -> ProductAttribute:
        na = Applicability.NOT_APPLICABLE
        if self.applicability is na and self.status is AttributeStatus.ACCEPTED:
            raise ValueError("a NOT_APPLICABLE feature cannot carry an accepted value")
        if (
            self.withheld_reason is WithheldReason.NOT_APPLICABLE
            and self.applicability is not na
        ):
            raise ValueError("withheld as NOT_APPLICABLE but applicability is not NOT_APPLICABLE")
        return self

    @model_validator(mode="after")
    def _value_matches_the_etim_feature_type(self) -> ProductAttribute:
        if self.value is None:
            return self
        expected = VALUE_KIND_FOR_FEATURE_TYPE[self.feature_type]
        if self.value.kind != expected:
            raise ValueError(
                f"feature {self.etim_feature_id} is ETIM type {self.feature_type} and requires a "
                f"{expected!r} value, got {self.value.kind!r}"
            )
        if (
            self.expected_unit
            and self.value.kind in {"numeric", "range"}
            and self.value.unit != self.expected_unit
        ):
            raise ValueError(
                f"feature {self.etim_feature_id} mandates unit {self.expected_unit!r}, "
                f"value carries {self.value.unit!r}; normalize before accepting"
            )
        return self

    @model_validator(mode="after")
    def _evidence_group_ids_are_unique(self) -> ProductAttribute:
        seen: set[str] = set()
        for group in self.evidence_groups:
            if group.group_id in seen:
                raise ValueError(
                    f"duplicate evidence group id {group.group_id!r} on attribute "
                    f"{self.etim_feature_id}; group ids must identify a group uniquely "
                    "so conflicts and the UI can reference them"
                )
            seen.add(group.group_id)
        return self

    @model_validator(mode="after")
    def _conflicts_reference_groups_that_exist(self) -> ProductAttribute:
        """A conflict pointing at a group we do not hold is unresolvable by a reviewer."""
        known = {g.group_id for g in self.evidence_groups}
        for conflict in self.conflicts:
            dangling = [gid for gid in conflict.group_ids if gid not in known]
            if dangling:
                raise ValueError(
                    f"conflict on {self.etim_feature_id} references unknown evidence "
                    f"group(s) {', '.join(sorted(dangling))}; known groups are "
                    f"{', '.join(sorted(known)) or '(none)'}"
                )
        return self

    @model_validator(mode="after")
    def _bound_conditions_are_supported_by_licensing_evidence(self) -> ProductAttribute:
        """An accepted value may only claim an operating point its evidence states.

        Two failures are possible and both are caught:

        * the attribute claims a qualifier that contradicts a verified span
          (18 A at AC-1, evidence says AC-3); and
        * the attribute claims a qualifier no verified span mentions at all, which
          would be an operating point we invented rather than read.

        Withheld attributes are left free. Representing a conflict, an incomplete
        qualifier set, or a variant-dependent value *requires* holding conditions
        that no single piece of evidence supports, and constraining that would make
        the abstention states unusable.
        """
        if self.status is not AttributeStatus.ACCEPTED:
            return self
        licensing = [e for g in self.evidence_groups for e in g.verified_members]
        for ev in licensing:
            clash = ev.conditions.conflicting_kinds(self.bound_conditions)
            if clash:
                raise ValueError(
                    f"attribute {self.etim_feature_id} claims operating conditions that "
                    f"contradict evidence {ev.evidence_id} on "
                    f"{', '.join(k.value for k in clash)}"
                )
        unsupported = [
            condition.display()
            for condition in self.bound_conditions.conditions
            if not any(
                ev.conditions.supports(ConditionSet(conditions=(condition,)))
                for ev in licensing
            )
        ]
        if unsupported:
            raise ValueError(
                f"attribute {self.etim_feature_id} binds conditions no verified span "
                f"states: {', '.join(unsupported)}"
            )
        return self

    @model_validator(mode="after")
    def _proven_family_invariance_is_backed_by_evidence(self) -> ProductAttribute:
        """PROVEN is a claim about evidence, not a trust-me flag.

        It requires either a span that itself proves the value spans the family, or
        agreement across two or more distinct exact child references. Observing one
        child proves nothing about its siblings.
        """
        if self.family_invariance is not FamilyInvariance.PROVEN:
            return self
        verified = [e for g in self.evidence_groups for e in g.verified_members]
        if any(e.proves_family_scope for e in verified):
            return self
        children = {
            e.artifact.covers_mpn
            for e in verified
            if e.identity_scope is IdentityScope.EXACT_SKU and e.artifact.covers_mpn
        }
        if len(children) >= 2:
            return self
        raise ValueError(
            f"family_invariance=PROVEN on {self.etim_feature_id} is not backed: needs a "
            "span that proves family scope, or verified spans from at least two distinct "
            f"exact child references (found {len(children)})"
        )

    @model_validator(mode="after")
    def _accepted_values_have_a_verified_span(self) -> ProductAttribute:
        """The central promise: no acceptance without a span we located ourselves.

        A normalized value does not need its own quote — lineage through
        `value.derivation` back to a verified raw fragment is what supports it.
        """
        if self.status is not AttributeStatus.ACCEPTED:
            return self
        verified = [e for g in self.evidence_groups for e in g.verified_members]
        if not verified:
            raise ValueError(
                f"attribute {self.etim_feature_id} accepts a value with no verified span; "
                "unverified evidence may not support an accepted value"
            )
        return self

    @model_validator(mode="after")
    def _support_grade_is_derived_not_asserted(self) -> ProductAttribute:
        """The grade must equal what the documented rule produces from this evidence."""
        if self.status is not AttributeStatus.ACCEPTED:
            if self.support_grade is not None:
                raise ValueError("a withheld attribute must not carry a support grade")
            return self

        factors = compute_support_factors(
            [e for g in self.evidence_groups for e in g.members],
            family_invariance=self.family_invariance,
            condition_completeness=self.bound_conditions.completeness,
        )
        expected = derive_support_grade(factors)
        if expected is None:
            raise ValueError(
                "the support rule refuses to grade this evidence, so the value must be "
                "withheld rather than accepted"
            )
        if self.support_grade != expected:
            raise ValueError(
                f"support_grade {self.support_grade} was asserted, but the rule "
                f"({factors.rule_version}) derives {expected}; grades are computed, not set"
            )
        return self

    @model_validator(mode="after")
    def _unproven_family_invariance_blocks_acceptance(self) -> ProductAttribute:
        if (
            self.status is AttributeStatus.ACCEPTED
            and self.family_invariance is FamilyInvariance.UNPROVEN
        ):
            raise ValueError(
                "family invariance is UNPROVEN, so this value is not in scope for the "
                "resolved identity and must be withheld"
            )
        return self

    # ---- convenience ---------------------------------------------------------

    @property
    def is_accepted(self) -> bool:
        return self.status is AttributeStatus.ACCEPTED

    @property
    def counts_toward_coverage(self) -> bool:
        """Only applicable features can be a gap or a fill."""
        return self.applicability is Applicability.APPLICABLE

    @property
    def all_evidence(self) -> list[Evidence]:
        return [e for g in self.evidence_groups for e in g.members]


def accepted_attribute_factors(attr: ProductAttribute) -> SupportFactors:
    """Recompute the factor bag for display. Kept public so the UI and eval agree."""
    return compute_support_factors(
        attr.all_evidence,
        family_invariance=attr.family_invariance,
        condition_completeness=attr.bound_conditions.completeness,
        independent_root_count=len(attr.evidence_groups),
    )


class RunProvenance(BaseModel):
    """How this run's external interactions were obtained.

    A REPLAY run replays interactions that were really captured earlier. It is not
    synthetic, and it is not fresh. `captured_at` is mandatory for REPLAY and MIXED so
    the UI can always state the age of what it is showing.

    **MIXED is a defensive truth state, not an operating mode.** Nothing in the normal
    flow requests it. It exists so that a run which did end up partly recorded and
    partly live can say so, instead of being mislabelled as one or the other. It is
    rejected by published evaluation and by the public demo, and it must never be
    offered as a user-selectable option.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mode: RunMode
    captured_at: datetime | None = Field(
        default=None, description="When the replayed interactions were originally recorded"
    )
    cassette_id: str | None = None
    extraction_model: str | None = None
    provider_surface: str | None = Field(default=None, description="e.g. 'vertex-ai:us-central1'")
    sdk_version: str | None = None

    @model_validator(mode="after")
    def _replay_states_its_capture_date(self) -> RunProvenance:
        if self.mode in {RunMode.REPLAY, RunMode.MIXED} and self.captured_at is None:
            raise ValueError(
                f"{self.mode} must record captured_at; a replayed run must never be able to "
                "present itself as fresh"
            )
        return self

    @property
    def is_publishable_evaluation(self) -> bool:
        """Published evaluation must be wholly recorded or wholly live, never both."""
        return self.mode is not RunMode.MIXED

    @property
    def is_public_demo_safe(self) -> bool:
        """The public, ungated demo serves recorded runs only.

        LIVE is gated behind an admin secret and a spend budget; MIXED is never
        served to anyone, including judges.
        """
        return self.mode is RunMode.REPLAY

    @property
    def is_requestable(self) -> bool:
        """Whether a caller may ask for this mode. MIXED can only be *observed*."""
        return self.mode is not RunMode.MIXED

    def banner(self) -> str:
        if self.mode is RunMode.LIVE:
            return "LIVE RUN"
        stamp = self.captured_at.date().isoformat() if self.captured_at else "unknown date"
        label = "RECORDED REPLAY" if self.mode is RunMode.REPLAY else "MIXED LIVE/REPLAY"
        return f"{label} — captured {stamp}"


class RunCost(BaseModel):
    """Measured, never estimated. Absent is better than guessed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int = 0
    output_tokens: int = 0
    usd: float = 0.0
    model_calls: int = 0
    search_queries: int = 0
    artifacts_fetched: int = 0
    cache_hits: int = 0
    wall_seconds: float = 0.0


class GoldenRecord(BaseModel):
    """The output of one enrichment run."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: str
    run_id: str
    created_at: datetime
    provenance: RunProvenance

    input: ProductInput
    identity: ProductIdentity

    etim_release: str = Field(default="10.0", description="ETIM release the schema came from")
    etim_language: str = Field(default="EN", description="ETIM language code")
    etim_class_id: str | None = Field(default=None, pattern=r"^EC\d{6}$")
    etim_class_name: str | None = None

    attributes: tuple[ProductAttribute, ...] = ()
    coverage: CoverageReport | None = None
    cost: RunCost = Field(default_factory=RunCost)

    @model_validator(mode="after")
    def _non_exact_identity_gates_attribute_acceptance(self) -> GoldenRecord:
        """Identity is a hard gate, not advice.

        When identity is not EXACT, an accepted value must be explicitly proven
        invariant at the family scope. Observing one child is not proof, and the
        contract will not let a stage skip that step.
        """
        if self.identity.is_exact:
            return self
        offenders = [
            a.etim_feature_id
            for a in self.attributes
            if a.is_accepted and a.family_invariance is not FamilyInvariance.PROVEN
        ]
        if offenders:
            raise ValueError(
                f"identity is {self.identity.disposition}, so accepted attributes must have "
                f"family_invariance=PROVEN; offending features: {', '.join(offenders)}"
            )
        return self

    @model_validator(mode="after")
    def _exact_identity_does_not_claim_family_proofs(self) -> GoldenRecord:
        if not self.identity.is_exact:
            return self
        offenders = [
            a.etim_feature_id
            for a in self.attributes
            if a.family_invariance is FamilyInvariance.PROVEN
        ]
        if offenders:
            raise ValueError(
                "identity is EXACT, so family invariance is NOT_REQUIRED; "
                f"remove the PROVEN claim from: {', '.join(offenders)}"
            )
        return self

    @property
    def accepted(self) -> list[ProductAttribute]:
        return [a for a in self.attributes if a.is_accepted]

    @property
    def withheld(self) -> list[ProductAttribute]:
        return [a for a in self.attributes if not a.is_accepted]

    def build_coverage(self) -> CoverageReport:
        """Derive the coverage report from the attributes actually on the record."""
        applicable = [a for a in self.attributes if a.applicability is Applicability.APPLICABLE]
        not_applicable = [
            a for a in self.attributes if a.applicability is Applicability.NOT_APPLICABLE
        ]
        unknown = [a for a in self.attributes if a.applicability is Applicability.UNKNOWN]
        critical = [a for a in self.attributes if a.buyer_critical]
        critical_applicable = [
            a for a in critical if a.applicability is Applicability.APPLICABLE
        ]
        return CoverageReport(
            etim_class_id=self.etim_class_id,
            etim_features_total=len(self.attributes),
            applicable_total=len(applicable),
            not_applicable_total=len(not_applicable),
            applicability_unknown_total=len(unknown),
            accepted_total=sum(1 for a in applicable if a.is_accepted),
            buyer_critical_total=len(critical),
            buyer_critical_applicable=len(critical_applicable),
            buyer_critical_accepted=sum(1 for a in critical_applicable if a.is_accepted),
        )


__all__ = [
    "ConditionCompleteness",
    "GoldenRecord",
    "ProductAttribute",
    "ProductIdentity",
    "ProductInput",
    "RunCost",
    "RunProvenance",
    "VariantAxis",
    "accepted_attribute_factors",
]
