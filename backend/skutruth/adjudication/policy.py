"""The commit policy: what a supported claim must satisfy to reach an output.

Verification already answered "does the evidence support this?". This module answers a
different question — "is that supported claim safe to commit *here*?" — and it is
allowed to refuse a perfectly well-verified fact. Most of the refusals below do exactly
that.

## The six requirements

A fact becomes committable only when all of them hold:

1. verification reached `EXACT_SPAN`;
2. it carries a value of a kind that can be represented;
3. it belongs to the resolved exact product;
4. a mapping rule explicitly defines its target;
5. any unit change is one the reviewed registry can perform;
6. applying the mapping does not silently discard the operating point.

Conflicts are the seventh requirement and are settled in `conflicts`, because they are
a property of a *set* of facts rather than of one.

## Mapping never upgrades verification

A mapping may know that `screw clamp terminals` and `Screw connection` are the same
thing. It still cannot make an `UNVERIFIED` outcome committable here. Licensing a
controlled-vocabulary substitution is a separate deterministic normalisation stage
backed by a published synonym list; until that exists, `UNVERIFIED` means no commit,
and this module never reinterprets a verification failure — it carries it.
"""

from __future__ import annotations

from collections.abc import Sequence

from skutruth.contracts import (
    AttributeValue,
    ConditionSet,
    EvidenceVerification,
    IdentityDisposition,
)
from skutruth.contracts.mpn import mpn_matches
from skutruth.etim import units
from skutruth.identity.models import IdentityResolution
from skutruth.verification import VerificationOutcome

from .mapping import MappingRegistry
from .models import (
    SUPPORTED_VALUE_KINDS,
    AdjudicatedFact,
    AdjudicationDecision,
    AdjudicationReason,
    AttributeMappingSpec,
    ConditionPolicy,
)


def render_value(value: AttributeValue) -> str:
    """The cell text for a value. Presentation only — never a conversion."""
    if value.kind == "numeric":
        return f"{value.number:g}"
    if value.kind == "alphanumeric":
        return value.text
    return value.display()


def render_uom(value: AttributeValue) -> str:
    """The UOM cell. Empty for values that carry no unit, which is legitimate."""
    return getattr(value, "unit", None) or ""


def _refuse(
    outcome: VerificationOutcome,
    decision: AdjudicationDecision,
    reason: AdjudicationReason,
    detail: str,
    *,
    spec: AttributeMappingSpec | None = None,
) -> AdjudicatedFact:
    """Any non-commit outcome. Carries no value: only a commit has one."""
    return AdjudicatedFact(
        outcome=outcome, decision=decision, reason=reason, detail=detail, spec=spec
    )


def _conditions_are_representable(
    spec: AttributeMappingSpec, conditions: ConditionSet
) -> tuple[bool, str]:
    """Whether the target can carry this fact's operating point without losing it."""
    if spec.condition_policy is ConditionPolicy.PRESERVE_AS_METADATA:
        return True, ""

    if spec.condition_policy is ConditionPolicy.TARGET_ENCODES_CONDITIONS:
        if conditions.describes_same_operating_point_as(spec.required_conditions):
            return True, ""
        return False, (
            f"{spec.target_label!r} encodes the operating point "
            f"'{spec.required_conditions.display()}', but the fact is stated under "
            f"'{conditions.display()}'"
        )

    # REJECT_IF_CONDITIONED
    if not conditions.conditions:
        return True, ""
    return False, (
        f"the value is stated under '{conditions.display()}' and "
        f"{spec.target_label!r} is a plain scalar; committing it would drop the "
        f"operating point"
    )


def _value_for_target(
    spec: AttributeMappingSpec, value: AttributeValue
) -> tuple[AttributeValue | None, str]:
    """The value expressed as the target requires, or a reason it cannot be.

    Unit conversion is delegated to the reviewed registry, which carries derivation
    lineage and refuses unknown units, cross-dimension conversions, and affine scales.
    No Unilog-specific unit rule is invented here — we do not have the UOM master, and
    a conversion we cannot justify is worse than an abstention.
    """
    if spec.target_uom is None or value.kind != "numeric":
        return value, ""
    try:
        return units.normalize_numeric(value, spec.target_uom), ""
    except units.UnitError as exc:
        return None, (
            f"cannot express {value.display()!r} in {spec.target_uom!r} for "
            f"{spec.target_label!r}: {exc}"
        )


def adjudicate_one(
    outcome: VerificationOutcome,
    registry: MappingRegistry,
    *,
    identity: IdentityResolution | None = None,
) -> AdjudicatedFact:
    """Decide one candidate fact against the mapping rules."""
    if identity is not None:
        if identity.disposition is not IdentityDisposition.EXACT or not identity.exact_mpn:
            return _refuse(
                outcome,
                AdjudicationDecision.WITHHOLD,
                AdjudicationReason.IDENTITY_NOT_EXACT,
                f"identity resolved to {identity.disposition.value}; nothing may be "
                f"committed for a reference we cannot name",
            )
        if not mpn_matches(identity.exact_mpn, outcome.exact_mpn):
            return _refuse(
                outcome,
                AdjudicationDecision.WITHHOLD,
                AdjudicationReason.IDENTITY_NOT_EXACT,
                f"the fact targets {outcome.exact_mpn} but this run resolved "
                f"{identity.exact_mpn}",
            )

    if outcome.status is not EvidenceVerification.EXACT_SPAN:
        failure = outcome.failure.value if outcome.failure else "UNVERIFIED"
        return _refuse(
            outcome,
            AdjudicationDecision.WITHHOLD,
            AdjudicationReason.VERIFICATION_FAILED,
            f"verification returned {failure}; a mapping cannot upgrade it",
        )

    spec = registry.spec_for(outcome.key)
    if spec is None:
        return _refuse(
            outcome,
            AdjudicationDecision.UNMAPPED,
            AdjudicationReason.NO_MAPPING,
            f"{outcome.key} is verified, but {registry.name} defines no target for it",
        )

    if outcome.value.kind not in SUPPORTED_VALUE_KINDS:
        return _refuse(
            outcome,
            AdjudicationDecision.REVIEW,
            AdjudicationReason.VALUE_KIND_MISMATCH,
            f"{outcome.value.kind} values have no attribute-slot representation yet",
            spec=spec,
        )
    if spec.expected_value_kind is not None and outcome.value.kind != spec.expected_value_kind:
        return _refuse(
            outcome,
            AdjudicationDecision.REVIEW,
            AdjudicationReason.VALUE_KIND_MISMATCH,
            f"{spec.target_label!r} expects a {spec.expected_value_kind} value, the fact "
            f"carries {outcome.value.kind}",
            spec=spec,
        )

    representable, detail = _conditions_are_representable(spec, outcome.conditions)
    if not representable:
        return _refuse(
            outcome,
            AdjudicationDecision.REVIEW,
            AdjudicationReason.CONDITION_LOSS,
            detail,
            spec=spec,
        )

    value, unit_problem = _value_for_target(spec, outcome.value)
    if value is None:
        return _refuse(
            outcome,
            AdjudicationDecision.REVIEW,
            AdjudicationReason.UNIT_INCOMPATIBLE,
            unit_problem,
            spec=spec,
        )

    return AdjudicatedFact(
        outcome=outcome,
        decision=AdjudicationDecision.COMMIT,
        reason=AdjudicationReason.ELIGIBLE,
        spec=spec,
        value=value,
    )


def adjudicate(
    outcomes: Sequence[VerificationOutcome],
    registry: MappingRegistry,
    *,
    identity: IdentityResolution | None = None,
) -> tuple[AdjudicatedFact, ...]:
    """Adjudicate every candidate, preserving input order.

    Order is preserved rather than sorted because these are *findings*, and a reviewer
    reading them alongside the extraction should see them in the same sequence. Slot
    ordering is a separate, explicit decision made from mapping priority.
    """
    return tuple(adjudicate_one(o, registry, identity=identity) for o in outcomes)


__all__ = ["adjudicate", "adjudicate_one", "render_uom", "render_value"]
