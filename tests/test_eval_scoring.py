"""Scoring semantics: what counts, what does not, and what stays unmeasured."""

from __future__ import annotations

import pytest
from conftest_eval import (
    AC1_400V,
    AC3_400V,
    AMPS_18,
    AMPS_32,
    ENUM_AC,
    ENUM_DC,
    OTHER_SHA,
    case,
    citation,
    evidence_fixture,
    expected_attr,
    family_case,
    manifest,
    predicted_attr,
    prediction,
    withheld_attr,
)
from skutruth.contracts import (
    Applicability,
    AttributeStatus,
    ConditionCompleteness,
    ConditionSet,
    IdentityDisposition,
    NumericValue,
    RangeValue,
    SupportGrade,
    WithheldReason,
)
from skutruth.eval import (
    CaseOutcome,
    CasePrediction,
    Ratio,
    Split,
    build_report,
    conditions_agree,
    score_all,
    values_agree,
)


def report_for(cases, predictions, split=Split.DEV):
    return build_report(manifest(cases), {p.case_id: p for p in predictions}, split=split)


class TestRatioSemantics:
    def test_counts_are_retained(self):
        r = Ratio(numerator=49, denominator=50)
        assert (r.numerator, r.denominator) == (49, 50)
        assert r.rate == pytest.approx(0.98)

    def test_a_zero_denominator_gives_no_rate(self):
        """Not 0%, not 100%. Nothing was measured."""
        r = Ratio(numerator=0, denominator=0)
        assert r.rate is None
        assert not r.is_measured
        assert "n/a" in r.display()

    def test_a_numerator_larger_than_its_denominator_is_a_bug(self):
        with pytest.raises(ValueError, match="exceeds denominator"):
            Ratio(numerator=3, denominator=2)

    def test_the_complement_keeps_the_denominator(self):
        assert Ratio(numerator=8, denominator=10).complement() == Ratio(
            numerator=2, denominator=10
        )


class TestValueComparison:
    def test_the_same_claim_written_differently_agrees(self):
        assert values_agree(AMPS_18, NumericValue(raw="18.0 A", number=18.0, unit="A"))

    def test_a_different_unit_does_not_agree(self):
        assert not values_agree(AMPS_18, NumericValue(raw="18 mA", number=18.0, unit="mA"))

    def test_a_different_number_does_not_agree(self):
        assert not values_agree(AMPS_18, AMPS_32)

    def test_enum_identity_uses_the_etim_value_id(self):
        assert values_agree(ENUM_AC, ENUM_AC)
        assert not values_agree(ENUM_AC, ENUM_DC)

    def test_ranges_compare_both_bounds_and_unit(self):
        a = RangeValue(raw="24-230 V", minimum=24.0, maximum=230.0, unit="V")
        assert values_agree(a, RangeValue(raw="24...230 V", minimum=24.0, maximum=230.0, unit="V"))
        assert not values_agree(a, RangeValue(raw="24-240 V", minimum=24.0, maximum=240.0,
                                              unit="V"))
        assert not values_agree(a, RangeValue(raw="24-230 mV", minimum=24.0, maximum=230.0,
                                              unit="mV"))

    def test_operating_points_must_match_exactly(self):
        assert conditions_agree(AC3_400V, AC3_400V)
        assert not conditions_agree(AC3_400V, AC1_400V)
        assert not conditions_agree(AC3_400V, ConditionSet())


class TestIdentityScoring:
    def test_a_correct_exact_identity_scores(self):
        rep = report_for([case()], [prediction()])
        assert rep.identity.accuracy == Ratio(numerator=1, denominator=1)

    def test_an_exact_prediction_naming_the_wrong_reference_is_wrong(self):
        """Right disposition, wrong sibling: the failure the system exists to prevent."""
        rep = report_for([case()], [prediction(identity_mpn="TEST-100-B")])
        assert rep.identity.accuracy == Ratio(numerator=0, denominator=1)

    def test_a_correct_family_identity_scores(self):
        rep = report_for(
            [family_case()],
            [
                prediction(
                    case_id="TEST-200",
                    identity_disposition=IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE,
                    identity_mpn=None,
                    attributes=(),
                )
            ],
        )
        assert rep.identity.accuracy == Ratio(numerator=1, denominator=1)
        assert rep.identity.false_exact == Ratio(numerator=0, denominator=1)

    def test_claiming_exact_on_a_family_case_is_a_false_exact(self):
        rep = report_for(
            [family_case()],
            [
                prediction(
                    case_id="TEST-200",
                    identity_disposition=IdentityDisposition.EXACT,
                    identity_mpn="TEST-200-A",
                    attributes=(),
                )
            ],
        )
        assert rep.identity.false_exact == Ratio(numerator=1, denominator=1)
        assert rep.identity.accuracy == Ratio(numerator=0, denominator=1)

    def test_abstaining_on_a_family_case_is_not_a_false_exact(self):
        """Being wrong by abstaining is not the same error, and is not counted as one."""
        rep = report_for(
            [family_case()],
            [
                prediction(
                    case_id="TEST-200",
                    identity_disposition=IdentityDisposition.UNKNOWN,
                    identity_mpn=None,
                    attributes=(),
                )
            ],
        )
        assert rep.identity.false_exact == Ratio(numerator=0, denominator=1)
        assert rep.identity.accuracy == Ratio(numerator=0, denominator=1)

    def test_exact_cases_are_excluded_from_the_false_exact_denominator(self):
        rep = report_for([case()], [prediction()])
        assert rep.identity.false_exact.denominator == 0
        assert rep.identity.false_exact.rate is None


class TestCommittedValuePrecision:
    def test_a_correct_accepted_value_scores(self):
        rep = report_for([case()], [prediction()])
        assert rep.attributes.committed_value_precision == Ratio(numerator=1, denominator=1)

    def test_an_incorrect_accepted_value_scores_against(self):
        rep = report_for([case()], [prediction(attributes=(predicted_attr(value=AMPS_32),))])
        assert rep.attributes.committed_value_precision == Ratio(numerator=0, denominator=1)

    def test_the_right_value_at_the_wrong_operating_point_is_wrong(self):
        """18 A @ AC-1 is not the AC-3 rating, however right the number looks."""
        rep = report_for(
            [case()], [prediction(attributes=(predicted_attr(bound_conditions=AC1_400V),))]
        )
        assert rep.attributes.committed_value_precision == Ratio(numerator=0, denominator=1)

    def test_the_right_value_with_missing_qualifiers_is_wrong(self):
        rep = report_for(
            [case()],
            [prediction(attributes=(predicted_attr(bound_conditions=ConditionSet()),))],
        )
        assert rep.attributes.committed_value_precision == Ratio(numerator=0, denominator=1)

    def test_withholding_never_counts_as_a_wrong_committed_value(self):
        rep = report_for([case()], [prediction(attributes=(withheld_attr(),))])
        assert rep.attributes.committed_value_precision == Ratio(numerator=0, denominator=0)
        assert rep.attributes.committed_value_precision.rate is None

    def test_withholding_reduces_coverage_instead(self):
        rep = report_for([case()], [prediction(attributes=(withheld_attr(),))])
        assert rep.attributes.coverage == Ratio(numerator=0, denominator=1)

    def test_selective_risk_is_the_complement_of_precision(self):
        rep = report_for([case()], [prediction()])
        assert rep.attributes.selective_risk == pytest.approx(0.0)

    def test_selective_risk_is_none_when_nothing_was_committed(self):
        rep = report_for([case()], [prediction(attributes=(withheld_attr(),))])
        assert rep.attributes.selective_risk is None

    def test_precision_is_broken_out_by_support_grade(self):
        c = case(
            expected_attributes=(
                expected_attr(),
                expected_attr(etim_feature_id="EF001364", value=AMPS_18, buyer_critical=False),
            )
        )
        p = prediction(
            attributes=(
                predicted_attr(support_grade=SupportGrade.A),
                predicted_attr(
                    etim_feature_id="EF001364", value=AMPS_32, support_grade=SupportGrade.C
                ),
            )
        )
        rep = report_for([c], [p])
        by_grade = rep.attributes.precision_by_support_grade
        assert by_grade["A"] == Ratio(numerator=1, denominator=1)
        assert by_grade["C"] == Ratio(numerator=0, denominator=1)


class TestApplicability:
    def test_not_applicable_leaves_every_coverage_denominator(self):
        c = case(
            expected_attributes=(
                expected_attr(
                    applicability=Applicability.NOT_APPLICABLE,
                    value=None,
                    expected_status=None,
                    buyer_critical=False,
                ),
            )
        )
        rep = report_for([c], [prediction(attributes=())])
        assert rep.attributes.coverage == Ratio(numerator=0, denominator=0)
        assert rep.buyer_critical.applicable == 0

    def test_accepting_a_not_applicable_feature_is_an_error(self):
        c = case(
            expected_attributes=(
                expected_attr(
                    applicability=Applicability.NOT_APPLICABLE,
                    value=None,
                    expected_status=None,
                    buyer_critical=False,
                ),
            )
        )
        rep = report_for([c], [prediction()])
        assert rep.attributes.committed_value_precision == Ratio(numerator=0, denominator=1)

    def test_unknown_applicability_counts_neither_way(self):
        """Guessing would move a denominator on no evidence."""
        c = case(
            expected_attributes=(
                expected_attr(
                    applicability=Applicability.UNKNOWN, value=None, expected_status=None
                ),
            )
        )
        rep = report_for([c], [prediction(attributes=())])
        assert rep.attributes.coverage.denominator == 0
        assert rep.buyer_critical.applicable == 0
        assert rep.buyer_critical.unknown_applicability == 1


class TestBuyerCriticalCoverage:
    def test_accepted_buyer_critical_features_count(self):
        rep = report_for([case()], [prediction()])
        assert rep.buyer_critical.coverage == Ratio(numerator=1, denominator=1)

    def test_withheld_buyer_critical_features_reduce_coverage(self):
        rep = report_for([case()], [prediction(attributes=(withheld_attr(),))])
        assert rep.buyer_critical.coverage == Ratio(numerator=0, denominator=1)
        assert rep.buyer_critical.withheld == 1

    def test_non_critical_features_stay_out_of_the_denominator(self):
        c = case(
            expected_attributes=(
                expected_attr(),
                expected_attr(etim_feature_id="EF000008", buyer_critical=False),
            )
        )
        rep = report_for([c], [prediction()])
        assert rep.buyer_critical.applicable == 1


class TestUnsupportedClaims:
    def test_an_accepted_claim_without_verified_evidence_is_unsupported(self):
        rep = report_for(
            [case()], [prediction(attributes=(predicted_attr(has_verified_evidence=False),))]
        )
        assert rep.attributes.unsupported_claim_rate == Ratio(numerator=1, denominator=1)

    def test_a_supported_claim_is_not_counted(self):
        rep = report_for([case()], [prediction()])
        assert rep.attributes.unsupported_claim_rate == Ratio(numerator=0, denominator=1)

    def test_withheld_attributes_are_outside_the_denominator(self):
        rep = report_for([case()], [prediction(attributes=(withheld_attr(),))])
        assert rep.attributes.unsupported_claim_rate.denominator == 0


class TestNormalizationAccuracy:
    def test_a_correctly_normalized_value_scores(self):
        rep = report_for([case()], [prediction()])
        assert rep.attributes.normalization_accuracy == Ratio(numerator=1, denominator=1)

    def test_a_wrong_unit_fails_normalization(self):
        wrong = NumericValue(raw="18 mA", number=18.0, unit="mA")
        rep = report_for([case()], [prediction(attributes=(predicted_attr(value=wrong),))])
        assert rep.attributes.normalization_accuracy == Ratio(numerator=0, denominator=1)

    def test_normalization_ignores_the_operating_point(self):
        """A correctly normalized value bound wrongly fails precision, not normalization."""
        rep = report_for(
            [case()], [prediction(attributes=(predicted_attr(bound_conditions=AC1_400V),))]
        )
        assert rep.attributes.normalization_accuracy == Ratio(numerator=1, denominator=1)
        assert rep.attributes.committed_value_precision == Ratio(numerator=0, denominator=1)

    def test_a_wrong_enum_value_id_fails(self):
        c = case(expected_attributes=(expected_attr(etim_feature_id="EF008242", value=ENUM_AC),))
        p = prediction(
            attributes=(predicted_attr(etim_feature_id="EF008242", value=ENUM_DC),)
        )
        assert report_for([c], [p]).attributes.normalization_accuracy == Ratio(
            numerator=0, denominator=1
        )


class TestCitationScoring:
    def test_a_matching_citation_is_valid(self):
        c = case(expected_attributes=(expected_attr(evidence=evidence_fixture()),))
        p = prediction(attributes=(predicted_attr(citation=citation()),))
        rep = report_for([c], [p])
        assert (rep.citations.valid, rep.citations.invalid) == (1, 0)

    def test_a_wrong_hash_is_invalid(self):
        c = case(expected_attributes=(expected_attr(evidence=evidence_fixture()),))
        p = prediction(attributes=(predicted_attr(citation=citation(artifact_sha256=OTHER_SHA)),))
        assert report_for([c], [p]).citations.invalid == 1

    def test_a_wrong_page_is_invalid(self):
        c = case(expected_attributes=(expected_attr(evidence=evidence_fixture()),))
        p = prediction(attributes=(predicted_attr(citation=citation(page=9)),))
        assert report_for([c], [p]).citations.invalid == 1

    def test_an_unverified_span_is_invalid(self):
        c = case(expected_attributes=(expected_attr(evidence=evidence_fixture()),))
        p = prediction(attributes=(predicted_attr(citation=citation(span_verified=None)),))
        assert report_for([c], [p]).citations.invalid == 1

    def test_a_missing_citation_is_invalid(self):
        c = case(expected_attributes=(expected_attr(evidence=evidence_fixture()),))
        p = prediction(attributes=(predicted_attr(citation=None),))
        assert report_for([c], [p]).citations.invalid == 1

    def test_an_insufficient_fixture_is_not_evaluated(self):
        """Scoring an unperformed check as a pass would manufacture a number."""
        c = case(
            expected_attributes=(
                expected_attr(evidence=evidence_fixture(artifact_sha256=None, page=None)),
            )
        )
        p = prediction(attributes=(predicted_attr(citation=citation()),))
        rep = report_for([c], [p])
        assert rep.citations.not_evaluated == 1
        assert (rep.citations.valid, rep.citations.invalid) == (0, 0)

    def test_no_fixture_at_all_is_not_evaluated(self):
        rep = report_for([case()], [prediction()])
        assert rep.citations.not_evaluated == 1

    def test_validity_excludes_the_unevaluated_from_its_denominator(self):
        c = case(
            expected_attributes=(
                expected_attr(evidence=evidence_fixture()),
                expected_attr(etim_feature_id="EF001364", buyer_critical=False),
            )
        )
        p = prediction(
            attributes=(
                predicted_attr(citation=citation()),
                predicted_attr(etim_feature_id="EF001364"),
            )
        )
        rep = report_for([c], [p])
        assert rep.citations.validity == Ratio(numerator=1, denominator=1)
        assert rep.citations.not_evaluated == 1


class TestFailuresRemainCounted:
    def test_a_missing_prediction_still_occupies_the_denominators(self):
        rep = report_for([case()], [])
        assert rep.identity.accuracy == Ratio(numerator=0, denominator=1)
        assert rep.attributes.coverage == Ratio(numerator=0, denominator=1)
        assert rep.operations.failed_cases == 1
        assert rep.operations.outcome_counts["MISSING_PREDICTION"] == 1

    @pytest.mark.parametrize(
        "outcome",
        [CaseOutcome.EXECUTION_ERROR, CaseOutcome.REPLAY_MISS, CaseOutcome.INVALID_OUTPUT],
        ids=lambda o: o.value,
    )
    def test_a_failed_case_is_never_silently_dropped(self, outcome):
        failed = CasePrediction(
            case_id="TEST-100", outcome=outcome, error_message="synthetic failure"
        )
        rep = report_for([case()], [failed])
        assert rep.identity.accuracy.denominator == 1
        assert rep.operations.failed_cases == 1

    def test_a_failed_case_commits_nothing_so_precision_is_unmeasured(self):
        failed = CasePrediction(
            case_id="TEST-100", outcome=CaseOutcome.REPLAY_MISS, error_message="no cassette"
        )
        rep = report_for([case()], [failed])
        assert rep.attributes.committed_value_precision.denominator == 0

    def test_a_failure_outcome_must_explain_itself(self):
        with pytest.raises(ValueError, match="requires an error_message"):
            CasePrediction(case_id="TEST-100", outcome=CaseOutcome.EXECUTION_ERROR)

    def test_predictions_for_unknown_cases_are_surfaced(self):
        rep = report_for([case()], [prediction(), prediction(case_id="GHOST")])
        assert rep.unexpected_prediction_ids == ("GHOST",)


class TestScoreAccumulatorDirectly:
    def test_judgements_record_why_something_failed(self):
        acc = score_all(
            (case(),),
            {"TEST-100": prediction(attributes=(predicted_attr(bound_conditions=AC1_400V),))},
        )
        assert any("wrong operating point" in j.note for j in acc.judgements)

    def test_an_accepted_value_truth_cannot_judge_is_recorded_but_not_scored(self):
        c = case(
            expected_attributes=(
                expected_attr(value=None, expected_status=None),
            )
        )
        acc = score_all((c,), {"TEST-100": prediction()})
        assert acc.committed_precision.denominator == 0
        assert acc.supported_claims.denominator == 1
        assert any(not j.judgeable for j in acc.judgements)


class TestExpectedWithholding:
    def test_a_case_may_expect_a_withholding(self):
        c = case(
            expected_attributes=(
                expected_attr(
                    expected_status=AttributeStatus.WITHHELD,
                    acceptable_withheld_reasons=(WithheldReason.VARIANT_DEPENDENT,),
                ),
            )
        )
        rep = report_for(
            [c], [prediction(attributes=(withheld_attr(WithheldReason.VARIANT_DEPENDENT),))]
        )
        assert rep.attributes.committed_value_precision.denominator == 0
        assert rep.attributes.coverage == Ratio(numerator=0, denominator=1)

    def test_partial_conditions_do_not_satisfy_a_conditioned_truth(self):
        partial = ConditionSet(
            conditions=AC3_400V.conditions[:1], completeness=ConditionCompleteness.PARTIAL
        )
        rep = report_for(
            [case()], [prediction(attributes=(predicted_attr(bound_conditions=partial),))]
        )
        assert rep.attributes.committed_value_precision == Ratio(numerator=0, denominator=1)
