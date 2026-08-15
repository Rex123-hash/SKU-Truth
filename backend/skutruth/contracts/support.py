"""The support-grade rule.

FROZEN CONTRACT — see contracts/README.md before changing anything here.

This replaces the earlier "VERIFIED requires >= 2 independent evidence clusters"
invariant, which was wrong in a specific way: it made a second, weaker corroborating
source *necessary*, so a single exact-SKU manufacturer datasheet with a mechanically
verified span could never reach top support — while two mutually-copied distributor
pages could. Cluster count is a poor proxy for evidence quality.

The rule below grades on the axes that actually bear on whether a value is safe to
accept, and cluster count is not one of them in P0. Conservative evidence-root
deduplication is P1; until it exists, additional agreeing members never raise a grade.

The rule is a pure function of an attribute's own evidence, so `ProductAttribute`
recomputes it and refuses a hand-set grade.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .conditions import ConditionCompleteness
from .enums import (
    EvidenceModality,
    EvidenceVerification,
    FamilyInvariance,
    IdentityScope,
    SupportGrade,
)
from .evidence import Evidence
from .mpn import mpn_matches

#: Bumped whenever the factor set or the grade rule changes, so that stored records
#: record which version graded them. The factor bag is intentionally open: new
#: factors can be logged without a contract break, and only the documented keys
#: participate in the rule.
#:
#: v2 replaced the `exact_identity_scope` factor with `scope_established`, which a
#: family-scoped span can satisfy when it proves the value holds across the family.
#:
#: v3 changed *which evidence is eligible to grade a value*. Grading now sees only
#: spans that support the accepted value (or its deterministic derivation) and that
#: are anchored to the resolved MPN. The same serialized evidence can therefore grade
#: differently than it did under v2 — an exact-SKU artifact for another part used to
#: set `scope_established`, and no longer can — so a stored v2 grade is not
#: reproducible under v3 and the version had to move.
SUPPORT_RULE_VERSION = "support@v3"

#: Factors we log today. Logging is not the same as using: `independent_root_count`
#: is recorded from day one so P1 clustering has history to work with, but it does
#: not influence the P0 grade.
KNOWN_FACTOR_KEYS = (
    "verified_span",
    "manufacturer_origin",
    "scope_established",
    "conditions_complete",
    "structured_modality",
    "family_invariance_ok",
    "independent_root_count",  # logged only in P0
)


class SupportFactors(BaseModel):
    """Measurable, model-free properties of the evidence behind a value.

    Extensible on purpose: `factors` is an open mapping so the set can grow without
    a contract break, and `rule_version` records which rule read it. No language
    model produces any entry here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    rule_version: str = SUPPORT_RULE_VERSION
    factors: dict[str, float] = Field(default_factory=dict)
    notes: tuple[str, ...] = Field(
        default=(), description="Human-readable reasons shown in the Evidence Drawer"
    )

    def get(self, key: str, default: float = 0.0) -> float:
        return self.factors.get(key, default)


def _is_structured(modality: EvidenceModality) -> bool:
    return modality in {
        EvidenceModality.STRUCTURED_API,
        EvidenceModality.SPEC_TABLE,
        EvidenceModality.SPEC_LINE,
    }


def is_eligible_evidence(ev: Evidence, identity_anchor_mpn: str | None) -> bool:
    """Whether this span is allowed to speak for the product the record resolved to.

    An artifact scoped to one exact commercial reference only speaks for *that*
    reference. When the record resolved to an exact MPN, such an artifact is eligible
    only if it covers that MPN — an exact-SKU datasheet for a different part is not
    weak evidence about this product, it is evidence about a different product.
    An artifact that does not say which reference it covers cannot be shown to cover
    this one, so it is ineligible too.

    Family- and range-scoped artifacts are not filtered here. They legitimately
    describe a set that includes this reference, and whether they establish scope is
    decided separately by `_establishes_scope`.

    When `identity_anchor_mpn` is `None` — the record is family-level, unknown, or
    contradictory — nothing is filtered. Exact child artifacts are precisely what
    proves invariance across a family, and demanding they match a family stem would
    break that.
    """
    if identity_anchor_mpn is None:
        return True
    if ev.identity_scope is not IdentityScope.EXACT_SKU:
        return True
    return mpn_matches(ev.artifact.covers_mpn, identity_anchor_mpn)


def _establishes_scope(ev: Evidence) -> bool:
    """Whether this span pins the value to the product we are describing.

    Two ways to satisfy it, and the distinction is the whole point:

    * the artifact is about one exact commercial reference; or
    * the artifact is family-scoped **and the span itself proves the value holds
      across the family** — a variant table row spanning every child, say.

    A family document that merely happens to list one child's value satisfies
    neither, and cannot establish scope. Grade is a statement about how well the
    *attribute* is supported, not about how the document happens to be scoped.

    Callers pass only eligible evidence (see `is_eligible_evidence`), so an
    exact-SKU artifact reaching here is already known to cover this reference.
    """
    if ev.identity_scope is IdentityScope.EXACT_SKU:
        return True
    return ev.identity_scope is IdentityScope.FAMILY and ev.proves_family_scope


def compute_support_factors(
    evidence: list[Evidence],
    *,
    family_invariance: FamilyInvariance,
    condition_completeness: ConditionCompleteness,
    independent_root_count: int | None = None,
) -> SupportFactors:
    """Reduce an attribute's evidence to the factor bag the grade rule reads."""
    verified = [e for e in evidence if e.may_support_accepted_value]
    notes: list[str] = []

    has_verified = bool(verified)
    manufacturer = any(e.source_type.is_manufacturer for e in verified)
    scope_established = any(_establishes_scope(e) for e in verified)
    structured = any(_is_structured(e.modality) for e in verified)
    conditions_ok = condition_completeness is ConditionCompleteness.COMPLETE
    invariance_ok = family_invariance in {FamilyInvariance.NOT_REQUIRED, FamilyInvariance.PROVEN}

    if not has_verified:
        notes.append("No supporting span was located in an ingested artifact.")
    else:
        exact_spans = sum(1 for e in verified if e.verification is EvidenceVerification.EXACT_SPAN)
        notes.append(
            f"{exact_spans} exact span(s) and {len(verified) - exact_spans} fuzzy span(s) "
            "located in ingested artifacts."
        )
    if has_verified and not manufacturer:
        notes.append("No manufacturer artifact among the verified spans.")
    if has_verified and not scope_established:
        notes.append(
            "No verified span pins the value to this reference: none is exact-SKU scoped, "
            "and no family-scoped span proves the value holds across the family."
        )
    elif any(e.proves_family_scope for e in verified):
        notes.append("A family-scoped span explicitly proves the value across variants.")
    if not conditions_ok:
        notes.append(f"Operating conditions are {condition_completeness.value.lower()}.")
    if family_invariance is FamilyInvariance.PROVEN:
        notes.append("Value proven invariant across the family.")
    elif family_invariance is FamilyInvariance.UNPROVEN:
        notes.append("Family invariance not proven from the available evidence.")

    factors = {
        "verified_span": float(has_verified),
        "manufacturer_origin": float(manufacturer),
        "scope_established": float(scope_established),
        "conditions_complete": float(conditions_ok),
        "structured_modality": float(structured),
        "family_invariance_ok": float(invariance_ok),
    }
    if independent_root_count is not None:
        # Logged for P1 clustering work. Deliberately absent from `derive_support_grade`.
        factors["independent_root_count"] = float(independent_root_count)

    return SupportFactors(factors=factors, notes=tuple(notes))


def derive_support_grade(factors: SupportFactors) -> SupportGrade | None:
    """Map factors to a coarse grade, or `None` when the value must not be accepted.

    ``None`` means "do not commit": either no span verified, or the value is not in
    scope for the resolved identity. Both are refusals, not weak acceptances.

        A  verified span, manufacturer origin, scope established, conditions complete,
           and in scope for the resolved identity.
        B  verified span and in scope, but exactly one of {manufacturer origin,
           scope established, complete conditions} is missing.
        C  verified span and in scope, but two or more of those are missing.

    Two deliberate properties of this rule:

    * Grade A does **not** require a second source. One manufacturer datasheet whose
      span we located ourselves is the strongest evidence available for an industrial
      part, and cluster count is not an input at all.
    * Grade A does **not** require an exact-SKU-scoped *document*. What it requires is
      that some verified span establishes the value applies to this reference — which
      an exact-SKU artifact does by construction, and which a family variant table can
      do explicitly. A family document that merely lists one child's value does not.
    """
    if not factors.get("verified_span"):
        return None
    if not factors.get("family_invariance_ok"):
        return None

    strengths = (
        factors.get("manufacturer_origin"),
        factors.get("scope_established"),
        factors.get("conditions_complete"),
    )
    missing = sum(1 for s in strengths if not s)
    if missing == 0:
        return SupportGrade.A
    if missing == 1:
        return SupportGrade.B
    return SupportGrade.C
