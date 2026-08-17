"""What adjudication decides, and what it hands to the delivery record.

Three questions, deliberately kept apart:

* **verification** — does the manufacturer evidence support this claim?
* **adjudication** — is a supported claim safe to commit to *this* output?
* **mapping** — where and how should an approved fact appear in the Unilog record?

The first is already answered and frozen. This module is the vocabulary for the other
two.

## Why not `ProductAttribute`

The frozen `ProductAttribute` is the right contract for an ETIM golden record and the
wrong one for this stage, on four counts that are not stylistic:

1. `etim_feature_id` is `^EF\\d{6}$`. Source keys here are opaque by design — an ETIM
   feature id today, `unilog:raw_width` later — and a pattern that admits only one
   vocabulary cannot express the thing this milestone exists to build.
2. `feature_type: EtimFeatureType` is mandatory. A Unilog attribute has no ETIM type.
3. `ACCEPTED` requires `licensing_evidence`, built from `EvidenceGroup`/`Evidence`.
   Verification produces a `VerificationOutcome`, which is a different and narrower
   record. Manufacturing `Evidence` objects to satisfy the validator would mean
   inventing the very provenance the contract exists to check.
4. `_support_grade_is_derived_not_asserted` *requires* a derived `SupportGrade` on
   every accepted attribute and raises when the rule declines to grade. Support grade
   depends on publisher authority and source policy, which this stage does not assess,
   so grading here would be manufacturing a grade out of `EXACT_SPAN` alone.

So `AdjudicatedFact` is narrow and new. It reuses `AttributeValue`, `ConditionSet`, and
`VerificationOutcome` unchanged, and it carries **no support grade and no confidence** —
a test enforces that.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import AttributeValue, ConditionSet, EvidenceVerification
from skutruth.verification import VerificationOutcome


class MappingAuthority(StrEnum):
    """Where a mapping rule came from, and therefore how much it may be trusted.

    This distinction is not decoration. We hold no official Unilog LOV, UOM master, or
    category rule file, so every mapping in use today was written by hand from two
    worked examples. Recording that on the rule itself is what keeps a demonstration
    from being reported as compliance, and it is what lets `OFFICIAL` data replace
    `DEMO` data later without touching a line of adjudication logic.
    """

    #: Derived from an organizer-supplied LOV, UOM master, or category rule file.
    OFFICIAL = "OFFICIAL"
    #: Hand-written to demonstrate the mechanism. Not authoritative, not compliance.
    DEMO = "DEMO"
    #: Operator-supplied for a local run.
    LOCAL = "LOCAL"

    @property
    def is_authoritative(self) -> bool:
        return self is MappingAuthority.OFFICIAL


class ConditionPolicy(StrEnum):
    """How a target attribute handles the operating point a value was stated under.

    A verified fact can still be unsafe for a scalar field. `7.5 kW` is true *under
    AC-3 at 400 V, 50/60 Hz*; writing `Power = 7.5 kW` into a bare column throws that
    away and produces a confident, unqualified, wrong-in-context specification — which
    is the exact failure the verifier was built to catch, reintroduced one stage later.

    So there is no policy that silently discards conditions. Every option either
    refuses them, matches them exactly, or keeps them.
    """

    #: The target is a plain scalar. Any bound condition means the value cannot be
    #: represented, and the fact goes to review. The safe default.
    REJECT_IF_CONDITIONED = "REJECT_IF_CONDITIONED"

    #: The target label itself names the operating point — "Rated Operational Power at
    #: AC-3, 400 V". The spec must declare `required_conditions`, and the fact's
    #: conditions must match that set exactly; nothing is lost because the label says it.
    TARGET_ENCODES_CONDITIONS = "TARGET_ENCODES_CONDITIONS"

    #: Conditions are carried on the mapped attribute and in the assembly result, but
    #: not into the CSV cell. The author is asserting the structured record retains
    #: them, which is true — `MappedUnilogAttribute.conditions` is never dropped.
    PRESERVE_AS_METADATA = "PRESERVE_AS_METADATA"


class AdjudicationDecision(StrEnum):
    """What happened to one candidate fact. Categorical, never a score."""

    #: Verified, mapped, safe. Occupies an attribute slot.
    COMMIT = "COMMIT"
    #: Must not populate any output value.
    WITHHOLD = "WITHHOLD"
    #: A person must decide. Visible, not discarded.
    REVIEW = "REVIEW"
    #: Verified, but no mapping rule exists for its source key. Not an error — it is
    #: the honest statement "we believe this and have nowhere approved to put it".
    UNMAPPED = "UNMAPPED"

    @property
    def is_committed(self) -> bool:
        return self is AdjudicationDecision.COMMIT


class AdjudicationReason(StrEnum):
    """Why a decision came out the way it did. Typed, never parsed from prose."""

    #: Verified, mapped, and nothing objected.
    ELIGIBLE = "ELIGIBLE"
    #: The verifier did not reach EXACT_SPAN. The specific verification failure is
    #: retained on the outcome and never reinterpreted here.
    VERIFICATION_FAILED = "VERIFICATION_FAILED"
    #: No mapping rule for this source key.
    NO_MAPPING = "NO_MAPPING"
    #: Committing would drop the operating point the value was stated under.
    CONDITION_LOSS = "CONDITION_LOSS"
    #: The target unit and the source unit cannot be reconciled by the reviewed
    #: registry. Not guessed at.
    UNIT_INCOMPATIBLE = "UNIT_INCOMPATIBLE"
    #: The value kind is not what the mapping declares the target holds.
    VALUE_KIND_MISMATCH = "VALUE_KIND_MISMATCH"
    #: Two facts state different values for one target under the same operating point.
    CONFLICT = "CONFLICT"
    #: Several verified facts target one scalar attribute under *different* operating
    #: points. Not a factual conflict — they may all be true — but a single scalar
    #: cell cannot represent them, so a person decides.
    MULTIPLE_OPERATING_POINTS = "MULTIPLE_OPERATING_POINTS"
    #: More committed attributes than the delivery template has slots.
    SLOT_CAPACITY = "SLOT_CAPACITY"
    #: The identity this run resolved is not an exact reference, or not this one.
    IDENTITY_NOT_EXACT = "IDENTITY_NOT_EXACT"
    #: An identical fact was already committed to this target.
    DUPLICATE_MERGED = "DUPLICATE_MERGED"


#: Value kinds that can currently reach `EXACT_SPAN`. Ranges and logicals are excluded
#: because the frozen verifier withholds them as `UNSUPPORTED_VALUE_KIND` — they never
#: arrive here verified, and pretending to support them would be dead code claiming a
#: capability.
SUPPORTED_VALUE_KINDS: frozenset[str] = frozenset({"numeric", "alphanumeric"})


class AttributeMappingSpec(BaseModel):
    """One rule: how a source fact becomes a Unilog attribute.

    `source_key` is **opaque**. The adjudicator never inspects it, never pattern-matches
    it, and does not care whether it reads `EF000008` or `unilog:manufacturer_width`.
    That is the whole point of the seam: when official category rules arrive, they land
    here as data.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: str = Field(min_length=1, description="Opaque source fact identifier")
    target_label: str = Field(min_length=1, description="ATTRIBUTE_LABEL text to emit")
    authority: MappingAuthority
    priority: int = Field(
        description="Slot ordering. Lower first. Explicit, so a future category "
        "sequence plugs straight in without re-sorting."
    )

    target_uom: str | None = Field(
        default=None, description="Unit to express the value in, via the reviewed registry"
    )
    expected_value_kind: str | None = Field(
        default=None, description="'numeric' or 'alphanumeric'; None accepts either"
    )
    condition_policy: ConditionPolicy = ConditionPolicy.REJECT_IF_CONDITIONED
    required_conditions: ConditionSet = Field(
        default_factory=ConditionSet,
        description="The operating point the target label encodes, for "
        "TARGET_ENCODES_CONDITIONS",
    )
    note: str = Field(default="", description="Why this rule exists. For reviewers.")

    @model_validator(mode="after")
    def _expected_kind_is_one_we_can_receive(self) -> AttributeMappingSpec:
        if self.expected_value_kind is not None and (
            self.expected_value_kind not in SUPPORTED_VALUE_KINDS
        ):
            raise ValueError(
                f"expected_value_kind {self.expected_value_kind!r} is not one of "
                f"{sorted(SUPPORTED_VALUE_KINDS)}; no other kind currently reaches "
                f"EXACT_SPAN, so a rule expecting one could never fire"
            )
        return self

    @model_validator(mode="after")
    def _encoded_conditions_are_named(self) -> AttributeMappingSpec:
        """`TARGET_ENCODES_CONDITIONS` has to say *which* conditions it encodes.

        Without that it is an unfalsifiable assertion that the label covers whatever
        turns up, which is silent condition loss wearing a policy's clothing.
        """
        policy = ConditionPolicy.TARGET_ENCODES_CONDITIONS
        if self.condition_policy is policy and not self.required_conditions.conditions:
            raise ValueError(
                f"{self.target_label!r} declares {policy.value} but names no "
                f"required_conditions; the operating point the label encodes must be "
                f"stated so it can be checked"
            )
        if self.condition_policy is not policy and self.required_conditions.conditions:
            raise ValueError(
                f"{self.target_label!r} declares required_conditions under "
                f"{self.condition_policy.value}, which does not use them"
            )
        return self


class AdjudicatedFact(BaseModel):
    """One candidate fact and what was decided about it.

    Carries the whole `VerificationOutcome`, unmodified. It is a frozen model, so this
    stage structurally cannot rewrite a verification result — and keeping the original
    rather than a copy of selected fields means provenance cannot quietly diverge from
    what the verifier actually found.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    outcome: VerificationOutcome
    decision: AdjudicationDecision
    reason: AdjudicationReason
    detail: str = ""

    spec: AttributeMappingSpec | None = None
    #: The value as it would be committed — possibly unit-converted, with lineage. None
    #: whenever nothing is committable.
    value: AttributeValue | None = None
    #: Source keys of identical facts merged into this one. Excludes this fact's own
    #: key; see `supporting_source_keys` for the whole set.
    merged_source_keys: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _committed_facts_are_complete(self) -> AdjudicatedFact:
        if self.decision is not AdjudicationDecision.COMMIT:
            return self
        if self.outcome.status is not EvidenceVerification.EXACT_SPAN:
            raise ValueError(
                f"{self.source_key} is COMMIT but its verification status is "
                f"{self.outcome.status.value}; only a located span may be committed"
            )
        if self.spec is None or self.value is None:
            raise ValueError(f"{self.source_key} is COMMIT without a mapping and a value")
        return self

    @model_validator(mode="after")
    def _refusals_carry_no_value(self) -> AdjudicatedFact:
        """A withheld fact must not leave a value lying around for someone to read."""
        if self.decision is AdjudicationDecision.WITHHOLD and self.value is not None:
            raise ValueError(f"{self.source_key} is WITHHOLD but still carries a value")
        return self

    @property
    def source_key(self) -> str:
        return self.outcome.key

    @property
    def supporting_source_keys(self) -> tuple[str, ...]:
        """Every source key backing this fact, including its own. Sorted.

        Several sources converging on one target and agreeing is corroboration, and a
        reviewer asking "what backs this cell?" wants the whole list rather than one key
        plus a separate merge record.
        """
        return tuple(sorted({self.source_key, *self.merged_source_keys}))

    @property
    def conditions(self) -> ConditionSet:
        return self.outcome.conditions

    @property
    def is_verified(self) -> bool:
        return self.outcome.verified

    def summary(self) -> str:
        target = f" -> {self.spec.target_label}" if self.spec else ""
        return f"{self.source_key}{target}: {self.decision.value} ({self.reason.value})"


class MappedUnilogAttribute(BaseModel):
    """A committed fact in the shape an attribute slot needs, plus its provenance.

    This is **not** an authoritative Unilog LOV model. It is the safe bridge into the
    generic `ATTRIBUTE_LABEL` / `ATTRIBUTE_VALUE` / `ATTRIBUTE_UOM` triplets, and it
    keeps everything the CSV has nowhere to put: which artifact, which page, what the
    document actually said, and which verifier decided.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    label: str = Field(min_length=1)
    value_text: str = Field(description="Rendered cell value")
    uom_text: str = Field(default="", description="Rendered UOM cell; empty is legitimate")
    order: int = Field(description="Assigned slot index, 1-based")

    source_key: str = Field(min_length=1)
    supporting_source_keys: tuple[str, ...] = Field(
        default=(),
        description="Every source that backs this cell, including `source_key`. More "
        "than one means separate sources converged and agreed.",
    )
    value: AttributeValue
    conditions: ConditionSet = Field(default_factory=ConditionSet)
    authority: MappingAuthority

    # -- provenance, none of which reaches the CSV ------------------------------
    exact_mpn: str
    artifact_sha256: str
    page_number: int
    evidence_text: str = Field(default="", description="The artifact's own words")
    verifier_version: str

    @property
    def is_authoritative(self) -> bool:
        """Whether the rule that produced this attribute came from organizer data."""
        return self.authority.is_authoritative


class AssemblySummary(BaseModel):
    """Deterministic counts for one assembly. Not a score, and not an accuracy claim."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_facts: int = 0
    verified: int = 0
    committed: int = 0
    withheld: int = 0
    unmapped: int = 0
    review: int = 0
    conflicts: int = 0
    attributes_written: int = 0
    slots_available: int = 0

    @property
    def slots_remaining(self) -> int:
        return self.slots_available - self.attributes_written

    def render(self) -> str:
        return (
            f"{self.input_facts} facts · {self.verified} verified · "
            f"{self.committed} committed · {self.review} review · "
            f"{self.unmapped} unmapped · {self.withheld} withheld · "
            f"{self.conflicts} conflicts · "
            f"{self.attributes_written}/{self.slots_available} slots used"
        )


__all__ = [
    "SUPPORTED_VALUE_KINDS",
    "AdjudicatedFact",
    "AdjudicationDecision",
    "AdjudicationReason",
    "AssemblySummary",
    "AttributeMappingSpec",
    "ConditionPolicy",
    "MappedUnilogAttribute",
    "MappingAuthority",
]
