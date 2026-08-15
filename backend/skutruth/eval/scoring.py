"""Deterministic scoring of predictions against reviewed truth.

Written before the system it will measure, so that the metrics cannot be chosen to
flatter whatever the system turns out to do.

Value comparison reuses the frozen contract's own notions of sameness —
`AttributeValue.semantic_key()` and `ConditionSet.key()` — rather than inventing a
second one. `18 A` and `18.0 A` are the same claim; `18 mA` is not; and `18 A @ AC-3`
is not the same claim as `18 A @ AC-1`, because a rating without its operating point
is not a specification.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from skutruth.contracts import (
    Applicability,
    AttributeValue,
    ConditionSet,
    IdentityDisposition,
    SupportGrade,
)
from skutruth.contracts.mpn import mpn_matches

from .metrics import Tally
from .models import (
    CaseOutcome,
    CasePrediction,
    CitationOutcome,
    EvalCase,
    ExpectedAttribute,
    PredictedAttribute,
)


def values_agree(expected: AttributeValue, predicted: AttributeValue) -> bool:
    """Same claim, ignoring how it was written.

    Delegates to the contract's `semantic_key`, so `raw` text and derivation lineage
    are irrelevant while number, unit, and ETIM value id are decisive.
    """
    return expected.semantic_key() == predicted.semantic_key()


def conditions_agree(expected: ConditionSet, predicted: ConditionSet) -> bool:
    """Same operating point.

    Exact equality, not the looser compatibility rule the evidence layer uses for
    corroboration. Truth states the operating point the value belongs to; a
    prediction that omits half of it has not made the same claim, even though nothing
    it said was contradicted.
    """
    return expected.describes_same_operating_point_as(predicted)


@dataclass(frozen=True, slots=True)
class AttributeJudgement:
    """Why one attribute scored the way it did. Kept for failure inspection."""

    etim_feature_id: str
    accepted: bool
    judgeable: bool
    value_correct: bool | None
    conditions_correct: bool | None
    normalization_correct: bool | None
    supported: bool | None
    citation: CitationOutcome
    note: str = ""


@dataclass
class ScoreAccumulator:
    """Running totals across cases. Every field keeps numerator and denominator."""

    identity: Tally = field(default_factory=Tally)
    false_exact: Tally = field(default_factory=Tally)

    committed_precision: Tally = field(default_factory=Tally)
    normalization: Tally = field(default_factory=Tally)
    supported_claims: Tally = field(default_factory=Tally)
    coverage: Tally = field(default_factory=Tally)

    buyer_critical_accepted: int = 0
    buyer_critical_applicable: int = 0
    buyer_critical_withheld: int = 0
    buyer_critical_not_applicable: int = 0
    buyer_critical_unknown: int = 0

    citations_valid: int = 0
    citations_invalid: int = 0
    citations_not_evaluated: int = 0

    precision_by_grade: dict[str, Tally] = field(default_factory=dict)
    outcomes: dict[str, int] = field(default_factory=dict)
    judgements: list[AttributeJudgement] = field(default_factory=list)

    def grade_tally(self, grade: SupportGrade | None) -> Tally:
        key = grade.value if grade is not None else "UNGRADED"
        return self.precision_by_grade.setdefault(key, Tally())

    def record_outcome(self, outcome: CaseOutcome) -> None:
        self.outcomes[outcome.value] = self.outcomes.get(outcome.value, 0) + 1


def score_case(
    case: EvalCase, prediction: CasePrediction | None, acc: ScoreAccumulator
) -> None:
    """Score one case into the accumulator.

    A missing or failed prediction is not skipped. It still occupies the identity
    denominator (nothing was identified) and the coverage denominator (nothing was
    filled), because a system that crashes has not thereby avoided being wrong.
    """
    if prediction is None:
        acc.record_outcome(CaseOutcome.MISSING_PREDICTION)
        _score_absent(case, acc)
        return

    acc.record_outcome(prediction.outcome)
    if not prediction.succeeded:
        _score_absent(case, acc)
        return

    _score_identity(case, prediction, acc)
    for expected in case.expected_attributes:
        _score_attribute(case, expected, prediction.attribute(expected.etim_feature_id), acc)


def _score_absent(case: EvalCase, acc: ScoreAccumulator) -> None:
    """A case that produced nothing: counted as identified-wrong and filled-nothing."""
    acc.identity.add_denominator_only()
    for expected in case.expected_attributes:
        if expected.applicability is Applicability.NOT_APPLICABLE:
            if expected.buyer_critical:  # pragma: no cover - rejected by validation
                acc.buyer_critical_not_applicable += 1
            continue
        if expected.is_judgeable:
            acc.coverage.add_denominator_only()
        if expected.buyer_critical:
            acc.buyer_critical_applicable += 1
            acc.buyer_critical_withheld += 1


def _score_identity(case: EvalCase, prediction: CasePrediction, acc: ScoreAccumulator) -> None:
    expected = case.expected_identity
    predicted = prediction.identity_disposition
    correct = predicted is expected.disposition

    # An EXACT prediction must also name the right reference. Getting the disposition
    # right while pointing at a sibling is the failure this whole system exists to
    # prevent, so it is not scored as a success.
    if correct and expected.disposition is IdentityDisposition.EXACT:
        correct = mpn_matches(prediction.identity_mpn, expected.exact_mpn)

    acc.identity.add(correct=correct)

    # False exact: truth is not EXACT, prediction claims EXACT. Measured over every
    # case whose truth is not EXACT, so abstaining never inflates it.
    if expected.disposition is not IdentityDisposition.EXACT:
        acc.false_exact.add(correct=predicted is IdentityDisposition.EXACT)


def _score_attribute(
    case: EvalCase,
    expected: ExpectedAttribute,
    predicted: PredictedAttribute | None,
    acc: ScoreAccumulator,
) -> None:
    accepted = predicted is not None and predicted.is_accepted

    # Applicability first: an inapplicable feature is not a gap, and must not sit in
    # any coverage denominator.
    if expected.applicability is Applicability.NOT_APPLICABLE:
        if expected.buyer_critical:  # pragma: no cover - rejected by validation
            acc.buyer_critical_not_applicable += 1
        if accepted:
            # Filling a field that does not apply is a real error, and the only place
            # it shows up is here.
            acc.committed_precision.add(correct=False)
            acc.judgements.append(
                AttributeJudgement(
                    expected.etim_feature_id, True, True, False, None, None, None,
                    CitationOutcome.NOT_EVALUATED,
                    "accepted a value for a NOT_APPLICABLE feature",
                )
            )
        return

    if expected.applicability is Applicability.UNKNOWN:
        # Neither counted as filled nor as missing: we do not know whether it applies,
        # and guessing either way would move a denominator on no evidence.
        if expected.buyer_critical:
            acc.buyer_critical_unknown += 1
        return

    if expected.buyer_critical:
        acc.buyer_critical_applicable += 1
        if accepted:
            acc.buyer_critical_accepted += 1
        else:
            acc.buyer_critical_withheld += 1

    if expected.is_judgeable:
        acc.coverage.add(correct=accepted)

    if not accepted:
        return

    assert predicted is not None
    # Support is tallied positively and inverted once, in the report. Counting
    # "unsupported" here and inverting again there is how a double negative turns
    # a perfectly supported claim into a reported violation.
    supported = predicted.has_verified_evidence
    acc.supported_claims.add(correct=supported)

    if not expected.is_judgeable:
        acc.judgements.append(
            AttributeJudgement(
                expected.etim_feature_id, True, False, None, None, None, supported,
                _score_citation(expected, predicted),
                "accepted, but truth records no value to judge it against",
            )
        )
        return

    value_ok = predicted.value is not None and values_agree(expected.value, predicted.value)
    conditions_ok = conditions_agree(expected.conditions, predicted.bound_conditions)
    correct = value_ok and conditions_ok

    acc.committed_precision.add(correct=correct)
    acc.grade_tally(predicted.support_grade).add(correct=correct)
    # Normalization is scored on the representation alone — number, unit, enum id —
    # so a correctly normalized value bound to the wrong operating point still shows
    # up as a conditions failure rather than a unit failure.
    acc.normalization.add(correct=value_ok)

    citation = _score_citation(expected, predicted)
    if citation is CitationOutcome.VALID:
        acc.citations_valid += 1
    elif citation is CitationOutcome.INVALID:
        acc.citations_invalid += 1
    else:
        acc.citations_not_evaluated += 1

    note = ""
    if not value_ok:
        note = "value differs from truth"
    elif not conditions_ok:
        note = "correct value bound to the wrong operating point"
    acc.judgements.append(
        AttributeJudgement(
            expected.etim_feature_id, True, True, value_ok, conditions_ok, value_ok,
            supported, citation, note,
        )
    )


def _score_citation(
    expected: ExpectedAttribute, predicted: PredictedAttribute
) -> CitationOutcome:
    """Score a citation against fixture data, or decline to score it.

    Full citation validity needs an ingested artifact and a located span, neither of
    which exists yet. What can be checked now is whether the prediction cites the
    artifact, hash, and page a reviewer recorded — and whether it claims the span was
    verified at all. Anything beyond that returns `NOT_EVALUATED`, because scoring an
    unperformed check as a pass would manufacture a number.
    """
    fixture = expected.evidence
    if fixture is None or not fixture.is_sufficient_for_citation_scoring:
        return CitationOutcome.NOT_EVALUATED
    cited = predicted.citation
    if cited is None:
        return CitationOutcome.INVALID
    if cited.span_verified is not True:
        return CitationOutcome.INVALID
    if cited.artifact_sha256 is None or cited.page is None:
        return CitationOutcome.INVALID
    if cited.artifact_sha256 != fixture.artifact_sha256:
        return CitationOutcome.INVALID
    if cited.page != fixture.page:
        return CitationOutcome.INVALID
    if fixture.identity_scope is not None and cited.identity_scope != fixture.identity_scope:
        return CitationOutcome.INVALID
    return CitationOutcome.VALID


def score_all(
    cases: tuple[EvalCase, ...], predictions: dict[str, CasePrediction]
) -> ScoreAccumulator:
    """Score a whole split. Cases with no prediction are scored as failures."""
    acc = ScoreAccumulator()
    for case in cases:
        score_case(case, predictions.get(case.case_id), acc)
    return acc


def unexpected_predictions(
    cases: tuple[EvalCase, ...], predictions: dict[str, CasePrediction]
) -> tuple[str, ...]:
    """Prediction ids with no matching case. Surfaced rather than ignored."""
    known = {c.case_id for c in cases}
    return tuple(sorted(cid for cid in predictions if cid not in known))


__all__ = [
    "AttributeJudgement",
    "ScoreAccumulator",
    "conditions_agree",
    "score_all",
    "score_case",
    "unexpected_predictions",
    "values_agree",
]
