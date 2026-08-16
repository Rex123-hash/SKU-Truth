"""Mechanical evidence verification.

**LOCATING A QUOTE IS NOT VERIFYING A CLAIM.**

Finding `18 A` somewhere on a page proves that the characters `18 A` are on the page. It
does not establish that this product is rated 18 A, still less that it is rated 18 A under
AC-3 at 440 V. To reach `EXACT_SPAN` the verifier must establish, from one coherent unit
of the real artifact:

1. the artifact is the one the claim's provenance names, and its stored bytes still hash
   to that digest;
2. the page exists and the model's fragment actually occurs on it;
3. the occurrence is unambiguous, or every occurrence supports the claim identically;
4. the artifact's own text — not the model's quote — states the claimed value, in a
   compatible unit, with a matching relation;
5. every bound condition is supported by that same unit;
6. the evidence belongs to the target product.

Any failure returns `UNVERIFIED` with a specific reason. There is no partial credit: a
claim whose value checks out but whose operating point does not is not "mostly verified",
it is a rating attached to the wrong conditions.

## Requirement 6 has two admissible proofs, and the caller supplies neither

A `ProductClaim` always names an exact reference, so something has to establish that the
evidence is about *that* reference rather than a sibling sharing the page. Two mechanisms
qualify, and both are properties of the document:

* **artifact scope** — the document's own provenance says it covers this exact reference
  (`identity_scope == EXACT_SKU` and `covers_mpn` matching under `canonical_mpn`). This is
  what a per-SKU datasheet has, and it is the only thing available on the text path.
* **table row identity** — a body row on the page carries a cell matching the reference.
  A range catalogue legitimately proves exact applicability this way, because the page
  itself draws the row.

A caller-supplied `IdentityResolution` is **not** a third mechanism. Identity answers
"which product did we resolve?"; scope answers "does this evidence belong to it?" A
matching `EXACT` identity cannot upgrade a range catalogue into exact-SKU evidence, and a
coincidental occurrence of the reference in page text cannot either — that is the
family-to-exact leap the whole identity stage exists to prevent.

## Verified is not accepted

This module produces verified *evidence*. It never builds a `ProductAttribute`, never sets
`proves_family_scope`, and never assigns a support grade — grading also depends on
authoritativeness and scope, which is adjudication's job. Nothing here has a confidence
score, because the answer is not probabilistic: either the artifact says it or it does not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from skutruth.contracts import (
    ConditionSet,
    EvidenceVerification,
    IdentityDisposition,
    IdentityScope,
)
from skutruth.contracts.mpn import mpn_matches
from skutruth.identity.models import IdentityResolution
from skutruth.ingest.errors import ArtifactStoreError
from skutruth.ingest.models import IngestedArtifact
from skutruth.ingest.storage import ArtifactStore
from skutruth.ingest.tables import PageTableExtraction

from .errors import ArtifactBindingError
from .matching import contains_phrase
from .models import (
    ConditionOutcome,
    EvidenceMode,
    EvidenceUnit,
    ProductClaim,
    TextMatchMode,
    VerificationFailure,
    VerificationOutcome,
)
from .quantities import Quantity, Relation, parse_quantities, quantity_supports
from .table import find_row_evidence
from .text import LocatedUnit, locate_units

#: Bumped when a change here could alter whether a claim verifies. v2 enforces exact
#: artifact scope on the text path and matches text values on phrase boundaries; both
#: can turn a previously verified claim into a refusal.
VERIFIER_VERSION = "mechanical-verify@v2"


def _outcome(
    claim: ProductClaim,
    status: EvidenceVerification,
    *,
    failure: VerificationFailure | None = None,
    detail: str = "",
    mode: EvidenceMode = EvidenceMode.NONE,
    match_mode: TextMatchMode | None = None,
    matched_text: str = "",
    evidence: EvidenceUnit | None = None,
    conditions: tuple[ConditionOutcome, ...] = (),
    value_detail: str = "",
) -> VerificationOutcome:
    return VerificationOutcome(
        key=claim.key,
        exact_mpn=claim.exact_mpn,
        value=claim.value,
        conditions=claim.conditions,
        artifact_sha256=claim.artifact_sha256,
        page_number=claim.page_number,
        status=status,
        failure=failure,
        failure_detail=detail,
        evidence_mode=mode,
        match_mode=match_mode,
        proposed_fragment=claim.source_fragment,
        matched_text=matched_text,
        evidence=evidence,
        condition_outcomes=conditions,
        value_detail=value_detail,
        verifier_version=VERIFIER_VERSION,
    )


# ---------------------------------------------------------------------------------
# Value support
# ---------------------------------------------------------------------------------


def _value_supported(
    claim: ProductClaim, stated: tuple[Quantity, ...], unit_text: str
) -> tuple[bool, VerificationFailure | None, str]:
    """Whether the evidence unit states the claimed value."""
    value = claim.value

    if value.kind == "numeric":
        target_unit = value.unit
        if not stated:
            return False, VerificationFailure.VALUE_NOT_SUPPORTED, "no quantity in the unit"
        for quantity in stated:
            if quantity_supports(
                quantity, number=value.number, unit=target_unit, relation=Relation.EQ
            ):
                return True, None, f"matched {quantity.text!r}"
        # Distinguish a relation problem from a plain disagreement, because they have
        # very different causes and the operator case is a known model failure mode.
        for quantity in stated:
            if quantity.relation is not Relation.EQ and quantity_supports(
                quantity.__class__(
                    number=quantity.number,
                    unit=quantity.unit,
                    relation=Relation.EQ,
                    text=quantity.text,
                    start=quantity.start,
                    end=quantity.end,
                    enumerated=quantity.enumerated,
                ),
                number=value.number,
                unit=target_unit,
                relation=Relation.EQ,
            ):
                return (
                    False,
                    VerificationFailure.OPERATOR_MISMATCH,
                    f"source states {quantity.text!r} ({quantity.relation.value}); the claim "
                    f"asserts a point value",
                )
        same_dimension = [q for q in stated if q.as_unit(target_unit or "") is not None]
        if target_unit and not same_dimension:
            return (
                False,
                VerificationFailure.UNIT_NOT_SUPPORTED,
                f"no quantity in {target_unit} or a convertible unit",
            )
        return (
            False,
            VerificationFailure.VALUE_NOT_SUPPORTED,
            f"unit states {[q.text for q in stated][:4]}",
        )

    if value.kind == "alphanumeric":
        needle = (value.text or "").strip()
        if not needle:
            return False, VerificationFailure.VALUE_NOT_SUPPORTED, "empty text value"
        # Phrase boundaries, never bare containment: `AC` must not be read out of
        # `VACUUM`, and `AC-3` is not `AC`. See `matching`.
        if contains_phrase(unit_text, needle):
            return True, None, f"phrase present in unit: {needle!r}"
        return (
            False,
            VerificationFailure.VALUE_NOT_SUPPORTED,
            f"{needle!r} does not occur as a whole phrase in the evidence unit",
        )

    # Ranges and logical values need semantics this version does not implement. Withheld
    # rather than approximated: a wrong range is a wrong specification.
    return (
        False,
        VerificationFailure.UNSUPPORTED_VALUE_KIND,
        f"{value.kind} values are not mechanically verified yet",
    )


# ---------------------------------------------------------------------------------
# Condition support
# ---------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConditionCheck:
    """The result of comparing one qualifier against one evidence unit.

    The comparison decides `failure` itself. Nothing downstream re-derives the reason by
    reading `detail`: prose is for people, and classification that depends on it silently
    changes meaning when the wording is edited.
    """

    supported: bool
    failure: VerificationFailure | None
    detail: str

    @classmethod
    def ok(cls, detail: str) -> ConditionCheck:
        return cls(supported=True, failure=None, detail=detail)

    @classmethod
    def failed(cls, failure: VerificationFailure, detail: str) -> ConditionCheck:
        return cls(supported=False, failure=failure, detail=detail)


def _condition_supported(
    condition_value: str, stated: tuple[Quantity, ...], unit_text: str
) -> ConditionCheck:
    """Whether one qualifier is supported by this unit.

    Quantitative qualifiers (`440 V`, `50 Hz`) must match a stated quantity *including its
    relation*. `<= 440 V` therefore does not support a condition of `440 V`: the source
    states a ceiling, the claim states the operating point a measurement was taken at.

    An enumerated source such as `50/60 Hz` supports either member, because the document
    asserts both discretely — that is set membership, not range containment. An enumerated
    *claim* is the mirror image and needs **every** alternative supported: a rating stated
    for `50/60 Hz` is not established by a source that only speaks about 50 Hz.

    A qualifier carrying two independent quantities (`400 V 50 Hz` as one condition) is
    refused outright. Checking the first and discarding the second would report the whole
    operating point as verified having examined half of it.
    """
    claimed = parse_quantities(condition_value)
    quantitative = [q for q in claimed if q.unit is not None]

    if quantitative:
        # Alternatives of one `a/b` enumeration share a span; separate spans mean
        # separate assertions, which this version does not reason about.
        spans = {(q.start, q.end) for q in quantitative}
        if len(spans) > 1:
            return ConditionCheck.failed(
                VerificationFailure.CONDITION_NOT_SUPPORTED,
                f"{condition_value!r} states {len(spans)} independent quantities "
                f"({', '.join(sorted({q.text for q in quantitative}))}); a multi-quantity "
                f"qualifier is refused rather than verified on its first term alone",
            )

        matches: list[str] = []
        for wanted in quantitative:
            found = next(
                (
                    q
                    for q in stated
                    if quantity_supports(
                        q, number=wanted.number, unit=wanted.unit, relation=wanted.relation
                    )
                ),
                None,
            )
            if found is None:
                relation_clash = next(
                    (
                        q
                        for q in stated
                        if q.relation is not wanted.relation and q.unit == wanted.unit
                    ),
                    None,
                )
                if relation_clash is not None:
                    return ConditionCheck.failed(
                        VerificationFailure.OPERATOR_MISMATCH,
                        f"source states {relation_clash.text!r} "
                        f"({relation_clash.relation.value}) but the condition asserts "
                        f"{condition_value!r} ({wanted.relation.value})",
                    )
                unmet = f"{wanted.text!r} of {condition_value!r}" if len(quantitative) > 1 else ""
                return ConditionCheck.failed(
                    VerificationFailure.CONDITION_NOT_SUPPORTED,
                    f"no quantity supporting {unmet or repr(condition_value)}",
                )
            note = " (enumerated alternative)" if found.enumerated else ""
            matches.append(f"{found.text!r}{note}")
        return ConditionCheck.ok(f"matched {', '.join(matches)}")

    # Categorical qualifier such as AC-3, matched on phrase boundaries within the unit,
    # which is bounded — so this can pick up neither a token from elsewhere on the page
    # nor `AC` sitting inside `VACUUM`.
    token = condition_value.strip()
    if token and contains_phrase(unit_text, token):
        return ConditionCheck.ok(f"categorical qualifier present: {token!r}")
    return ConditionCheck.failed(
        VerificationFailure.CONDITION_NOT_SUPPORTED,
        f"{condition_value!r} does not occur as a whole phrase in the evidence unit",
    )


def _check_conditions(
    conditions: ConditionSet, stated: tuple[Quantity, ...], unit_text: str
) -> tuple[tuple[ConditionOutcome, ...], bool]:
    outcomes = []
    for condition in conditions.conditions:
        check = _condition_supported(condition.value, stated, unit_text)
        outcomes.append(
            ConditionOutcome(
                kind=condition.kind.value,
                value=condition.value,
                supported=check.supported,
                failure=check.failure,
                detail=check.detail,
            )
        )
    return tuple(outcomes), all(o.supported for o in outcomes)


# ---------------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------------


class ScopeBinding(Enum):
    """What the artifact's own provenance says about the claim's exact reference."""

    #: The document states it covers this exact reference.
    EXACT = "EXACT"
    #: The document states it covers a *different* exact reference.
    CONTRADICTED = "CONTRADICTED"
    #: A range catalogue, or a document whose scope was never established. Not a
    #: judgement that the evidence is wrong — only that provenance alone cannot bind it.
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


def artifact_scope_binding(artifact: IngestedArtifact, exact_mpn: str) -> ScopeBinding:
    """Classify the artifact's scope against one exact reference.

    `CONTRADICTED` is worth separating from `NOT_ESTABLISHED`: a datasheet that says it is
    about a sibling is making a positive statement that this evidence is the wrong
    product's, which no other mechanism should be allowed to override.
    """
    if artifact_scope_supports_exact(artifact, exact_mpn):
        return ScopeBinding.EXACT
    source = artifact.source
    if source.identity_scope is IdentityScope.EXACT_SKU and source.covers_mpn is not None:
        return ScopeBinding.CONTRADICTED
    return ScopeBinding.NOT_ESTABLISHED


def _load_artifact(
    claim: ProductClaim, store: ArtifactStore, artifact: IngestedArtifact | None
) -> IngestedArtifact:
    """Get the artifact the claim names, re-validating its stored integrity."""
    if artifact is not None:
        if artifact.sha256 != claim.artifact_sha256:
            raise ArtifactBindingError(
                f"claim names artifact {claim.artifact_sha256[:12]}… but was handed "
                f"{artifact.sha256[:12]}…"
            )
        return artifact
    return store.load(claim.artifact_sha256, verify_original=True)


def verify_claim(
    claim: ProductClaim,
    *,
    store: ArtifactStore,
    identity: IdentityResolution | None = None,
    artifact: IngestedArtifact | None = None,
    tables: PageTableExtraction | None = None,
) -> VerificationOutcome:
    """Decide whether the artifact mechanically supports `claim`."""
    if identity is not None:
        if identity.disposition is not IdentityDisposition.EXACT or not identity.exact_mpn:
            return _outcome(
                claim,
                EvidenceVerification.UNVERIFIED,
                failure=VerificationFailure.PRODUCT_SCOPE_NOT_SUPPORTED,
                detail=f"identity is {identity.disposition.value}, not EXACT",
            )
        if not mpn_matches(identity.exact_mpn, claim.exact_mpn):
            return _outcome(
                claim,
                EvidenceVerification.UNVERIFIED,
                failure=VerificationFailure.PRODUCT_REFERENCE_MISMATCH,
                detail=f"claim targets {claim.exact_mpn}, identity resolved {identity.exact_mpn}",
            )

    try:
        loaded = _load_artifact(claim, store, artifact)
    except ArtifactBindingError as exc:
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.ARTIFACT_MISMATCH,
            detail=str(exc),
        )
    except ArtifactStoreError as exc:
        # Corrupt or missing stored artifact. Fail closed: unverifiable provenance is
        # not weak evidence, it is none.
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.ARTIFACT_UNREADABLE,
            detail=str(exc),
        )

    # The artifact's own provenance, checked before its contents. A document asserting it
    # covers a different reference is not weak evidence for this one.
    binding = artifact_scope_binding(loaded, claim.exact_mpn)
    if binding is ScopeBinding.CONTRADICTED:
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.PRODUCT_REFERENCE_MISMATCH,
            detail=f"the artifact states it covers {loaded.source.covers_mpn}, not "
            f"{claim.exact_mpn}",
        )

    page = loaded.page(claim.page_number)
    if page is None:
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.PAGE_NOT_FOUND,
            detail=f"page {claim.page_number} of {loaded.page_count}",
        )

    # A table row identifying itself as the target binds the evidence to the product on
    # its own, which is how a range catalogue legitimately supports an exact claim.
    if tables is not None:
        table_outcome = _verify_against_tables(claim, tables)
        if table_outcome is not None:
            return table_outcome

    # Text has no such per-unit binding, so the document's scope has to carry it. Without
    # that, a line about a sibling on a shared page would verify for this reference.
    if binding is not ScopeBinding.EXACT:
        scope = loaded.source.identity_scope
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.PRODUCT_SCOPE_NOT_SUPPORTED,
            detail=f"artifact scope is {scope.value if scope else 'unstated'} and does not "
            f"establish that it covers {claim.exact_mpn}; text evidence carries no other "
            f"binding to the product",
        )

    return _verify_against_text(claim, page)


def _verify_against_text(claim: ProductClaim, page) -> VerificationOutcome:
    located = locate_units(page, claim.source_fragment)
    if not located:
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.SOURCE_FRAGMENT_NOT_FOUND,
            detail=f"the model's fragment does not occur on page {claim.page_number}",
        )

    results = [(unit, _assess_text_unit(claim, unit)) for unit in located]
    verified = [(u, r) for u, r in results if r[0]]

    # Several occurrences are only safe when they agree. If some support the claim and
    # others do not, there is no deterministic rule for choosing, so nothing is chosen.
    if verified and len(verified) != len(results):
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.AMBIGUOUS_MATCH,
            detail=f"{len(results)} occurrences of the fragment support the claim "
            f"inconsistently ({len(verified)} of {len(results)})",
        )

    unit, (ok, failure, detail, conditions, value_detail) = verified[0] if verified else results[0]
    evidence = EvidenceUnit(
        mode=EvidenceMode.TEXT_UNIT, text=unit.text, start=unit.start, end=unit.end
    )
    return _outcome(
        claim,
        EvidenceVerification.EXACT_SPAN if ok else EvidenceVerification.UNVERIFIED,
        failure=failure,
        detail=detail,
        mode=EvidenceMode.TEXT_UNIT,
        match_mode=unit.match_mode,
        matched_text=unit.matched_text,
        evidence=evidence,
        conditions=conditions,
        value_detail=value_detail,
    )


def _assess_text_unit(
    claim: ProductClaim, unit: LocatedUnit
) -> tuple[bool, VerificationFailure | None, str, tuple[ConditionOutcome, ...], str]:
    """Value and every condition, against this one unit and nothing else."""
    stated = parse_quantities(unit.text)
    value_ok, value_failure, value_detail = _value_supported(claim, stated, unit.text)
    if not value_ok:
        return False, value_failure, value_detail, (), value_detail

    outcomes, all_supported = _check_conditions(claim.conditions, stated, unit.text)
    if not all_supported:
        unmet = [o for o in outcomes if not o.supported]
        # Each outcome already carries the reason its own comparison decided. A dropped
        # relation is the more specific diagnosis, so it wins when both are present.
        failure = next(
            (o.failure for o in unmet if o.failure is VerificationFailure.OPERATOR_MISMATCH),
            unmet[0].failure or VerificationFailure.CONDITION_NOT_SUPPORTED,
        )
        return (
            False,
            failure,
            "; ".join(f"{o.kind}={o.value}: {o.detail}" for o in unmet),
            outcomes,
            value_detail,
        )
    return True, None, "", outcomes, value_detail


def _verify_against_tables(
    claim: ProductClaim, tables: PageTableExtraction
) -> VerificationOutcome | None:
    """Try the structured table view. Returns None to fall through to text."""
    rows = find_row_evidence(tables, claim.exact_mpn)
    if not rows:
        return None

    for evidence in rows:
        unit_text = evidence.text()
        stated = parse_quantities(unit_text)
        value_ok, failure, detail = _value_supported(claim, stated, unit_text)
        if not value_ok:
            continue
        outcomes, all_supported = _check_conditions(claim.conditions, stated, unit_text)
        if not all_supported:
            continue
        return _outcome(
            claim,
            EvidenceVerification.EXACT_SPAN,
            mode=EvidenceMode.TABLE_UNIT,
            match_mode=TextMatchMode.TABLE_CELL,
            matched_text=evidence.identity_cell,
            evidence=EvidenceUnit(
                mode=EvidenceMode.TABLE_UNIT,
                text=unit_text,
                table_index=evidence.table_index,
                row_index=evidence.row_index,
                column_index=evidence.identity_column,
                bbox=evidence.bbox,
            ),
            conditions=outcomes,
            value_detail=detail or "matched in table row",
        )
    return None


def verify_table_claim(claim: ProductClaim, tables: PageTableExtraction) -> VerificationOutcome:
    """Table-only verification, with an explicit reason when no row applies."""
    from skutruth.ingest.tables import TableExtractionStatus

    if tables.status is not TableExtractionStatus.TABLES_EXTRACTED:
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.TABLE_STRUCTURE_UNRESOLVED,
            detail=f"table extraction reported {tables.status.value}",
        )
    outcome = _verify_against_tables(claim, tables)
    if outcome is not None:
        return outcome
    if not find_row_evidence(tables, claim.exact_mpn):
        return _outcome(
            claim,
            EvidenceVerification.UNVERIFIED,
            failure=VerificationFailure.PRODUCT_REFERENCE_MISMATCH,
            detail=f"no table row identifies itself as {claim.exact_mpn}",
        )
    return _outcome(
        claim,
        EvidenceVerification.UNVERIFIED,
        failure=VerificationFailure.VALUE_NOT_SUPPORTED,
        detail="the target row does not state the claimed value under the claimed conditions",
    )


def artifact_scope_supports_exact(artifact: IngestedArtifact, exact_mpn: str) -> bool:
    """Whether this artifact's own metadata binds it to one commercial reference.

    A `RANGE` catalogue may still be evidence — but it stays range evidence, and this
    returns False for it rather than manufacturing exact applicability.
    """
    source = artifact.source
    if source.identity_scope is not IdentityScope.EXACT_SKU:
        return False
    if source.covers_mpn is None:
        return False
    return mpn_matches(source.covers_mpn, exact_mpn)


__all__ = [
    "VERIFIER_VERSION",
    "ConditionCheck",
    "ScopeBinding",
    "artifact_scope_binding",
    "artifact_scope_supports_exact",
    "verify_claim",
    "verify_table_claim",
]
