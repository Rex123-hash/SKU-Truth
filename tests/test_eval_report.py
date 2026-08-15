"""Report assembly: operations aggregation, offline guarantees, no composite score."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest_eval import case, manifest, prediction
from skutruth.contracts import RunMode, RunProvenance
from skutruth.eval import (
    CasePrediction,
    EvaluationReport,
    Ratio,
    Split,
    assert_no_composite_score,
    build_report,
    cassette_store_for,
    is_locked_evaluation,
    prediction_from_golden_record,
)
from skutruth.eval.metrics import LatencySummary

CAPTURED = datetime(2026, 8, 15, tzinfo=UTC)


def report_for(cases, predictions, split=Split.DEV):
    return build_report(manifest(cases), {p.case_id: p for p in predictions}, split=split)


class TestNoCompositeScore:
    def test_the_report_exposes_no_overall_score(self):
        """A composite would let an identity collapse be paid for with coverage."""
        assert_no_composite_score(report_for([case()], [prediction()]))

    def test_no_field_is_named_like_a_composite(self):
        banned = {"overall_score", "score", "skutruth_score", "composite", "total_score"}
        assert not set(EvaluationReport.model_fields) & banned

    def test_headline_lines_show_counts_not_bare_percentages(self):
        lines = report_for([case()], [prediction()]).headline_lines()
        assert any("1/1" in line for line in lines)


class TestReportProvenance:
    def test_the_manifest_fingerprint_is_recorded(self):
        m = manifest([case()])
        rep = build_report(m, {"TEST-100": prediction()}, split=Split.DEV)
        assert rep.manifest_fingerprint == m.fingerprint()
        assert rep.manifest_id == "unit-test"
        assert rep.manifest_version == "1"

    def test_synthetic_sets_are_flagged_on_the_report(self):
        rep = report_for([case()], [prediction()])
        assert rep.contains_only_synthetic_cases
        assert "NOT A BENCHMARK RESULT" in rep.headline_lines()[0]

    def test_the_split_is_recorded(self):
        assert report_for([case()], [prediction()]).split is Split.DEV

    def test_coverage_summary_travels_with_the_report(self):
        rep = report_for([case()], [prediction()])
        assert rep.coverage_summary.cases == 1
        assert rep.coverage_summary.manufacturers == 1

    def test_the_report_round_trips_through_json(self):
        rep = report_for([case()], [prediction()])
        again = EvaluationReport.model_validate_json(rep.model_dump_json())
        assert again.manifest_fingerprint == rep.manifest_fingerprint
        assert again.attributes.committed_value_precision == Ratio(numerator=1, denominator=1)

    def test_raw_counts_survive_serialization(self):
        """Rounding is for presentation; the report keeps numerators and denominators."""
        blob = report_for([case()], [prediction()]).model_dump(mode="json")
        assert blob["identity"]["accuracy"] == {"numerator": 1, "denominator": 1}


class TestOperationsAggregation:
    def test_run_modes_are_counted(self):
        live = prediction(provenance=RunProvenance(mode=RunMode.LIVE))
        rep = report_for([case()], [live])
        assert rep.operations.run_mode_counts == {"live": 1}

    def test_replay_and_live_are_counted_separately(self):
        cases = [case(case_id="A"), case(case_id="B", product_family_id="F-B")]
        preds = [
            prediction(case_id="A", provenance=RunProvenance(mode=RunMode.LIVE)),
            prediction(
                case_id="B",
                provenance=RunProvenance(mode=RunMode.REPLAY, captured_at=CAPTURED),
            ),
        ]
        rep = report_for(cases, preds)
        assert rep.operations.run_mode_counts == {"live": 1, "replay": 1}

    def test_missing_usage_never_becomes_zero_usage(self):
        """'Nobody told us' is not 'it was free'."""
        rep = report_for([case()], [prediction()])
        assert rep.operations.usage.input_tokens is None
        assert rep.operations.usage.output_tokens is None
        assert rep.operations.usage.cost_by_currency == {}

    def test_reported_usage_is_summed(self):
        cases = [case(case_id="A"), case(case_id="B", product_family_id="F-B")]
        preds = [
            prediction(case_id="A", input_tokens=100, output_tokens=10),
            prediction(case_id="B", input_tokens=250, output_tokens=25),
        ]
        rep = report_for(cases, preds)
        assert rep.operations.usage.input_tokens == 350
        assert rep.operations.usage.output_tokens == 35

    def test_partial_usage_reporting_sums_only_what_was_reported(self):
        cases = [case(case_id="A"), case(case_id="B", product_family_id="F-B")]
        preds = [prediction(case_id="A", input_tokens=100), prediction(case_id="B")]
        assert report_for(cases, preds).operations.usage.input_tokens == 100

    def test_costs_in_different_currencies_are_never_summed(self):
        cases = [case(case_id="A"), case(case_id="B", product_family_id="F-B")]
        preds = [
            prediction(case_id="A", provider_reported_cost=0.5, currency="USD"),
            prediction(case_id="B", provider_reported_cost=0.4, currency="EUR"),
        ]
        rep = report_for(cases, preds)
        assert rep.operations.usage.cost_by_currency == {"EUR": 0.4, "USD": 0.5}

    def test_no_cost_is_invented_when_the_provider_reported_none(self):
        rep = report_for([case()], [prediction(input_tokens=1000)])
        assert rep.operations.usage.cost_by_currency == {}
        assert rep.operations.usage.predictions_reporting_cost == 0

    def test_provider_latency_is_kept_apart_from_evaluation_time(self):
        """Replaying a cassette is fast, and says nothing about the provider."""
        p = prediction(provider_latency_seconds=(1.8,), evaluation_seconds=0.002)
        rep = report_for([case()], [p])
        assert rep.operations.provider_latency.total_seconds == pytest.approx(1.8)
        assert rep.operations.evaluation_latency.total_seconds == pytest.approx(0.002)

    def test_interactions_are_counted(self):
        rep = report_for([case()], [prediction(interaction_count=3)])
        assert rep.operations.interactions == 3


class TestLatencySummary:
    def test_percentiles_are_withheld_on_a_tiny_sample(self):
        """A p95 over four points is the maximum in a costume."""
        s = LatencySummary.from_samples([1.0, 2.0, 3.0, 4.0])
        assert s.count == 4
        assert s.mean_seconds == pytest.approx(2.5)
        assert s.p50_seconds is None and s.p95_seconds is None

    def test_percentiles_appear_once_the_sample_is_large_enough(self):
        s = LatencySummary.from_samples([1.0, 2.0, 3.0, 4.0, 5.0])
        assert s.p50_seconds == 3.0
        assert s.p95_seconds == 5.0

    def test_an_empty_sample_reports_nothing_rather_than_zero(self):
        s = LatencySummary.from_samples([])
        assert s.count == 0
        assert s.mean_seconds is None


class TestOfflineAndFailClosed:
    def test_locked_evaluation_reads_curated_fixtures_only(self):
        """A missing fixture must fail closed, not be satisfied by a runtime recording."""
        store = cassette_store_for(Split.LOCKED_TEST)
        assert store.writable is False
        assert store.root.name == "fixtures"

    def test_dev_evaluation_may_read_runtime_recordings(self):
        store = cassette_store_for(Split.DEV)
        assert store.root.name == "runtime"

    def test_the_locked_split_is_identifiable(self):
        assert is_locked_evaluation(Split.LOCKED_TEST)
        assert not is_locked_evaluation(Split.DEV)

    def test_scoring_requires_no_network_or_provenance(self):
        """Predictions without provenance still score every metric that does not need it."""
        rep = report_for([case()], [prediction(provenance=None)])
        assert rep.identity.accuracy == Ratio(numerator=1, denominator=1)
        assert rep.operations.run_mode_counts == {}


class TestGoldenRecordAdapter:
    def test_a_contract_valid_record_converts_into_a_prediction(self):
        import sys
        from pathlib import Path

        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from conftest import EXACT_IDENTITY_RECORD  # noqa: PLC0415

        pred = prediction_from_golden_record(EXACT_IDENTITY_RECORD, case_id="TEST-100")
        assert pred.case_id == "TEST-100"
        assert pred.identity_mpn == "LC1D18P7"
        assert pred.attributes[0].has_verified_evidence is True
        assert pred.attributes[0].citation is not None

    def test_the_adapter_reads_support_from_the_records_own_evidence(self):
        from conftest import EXACT_IDENTITY_RECORD  # noqa: PLC0415

        pred = prediction_from_golden_record(EXACT_IDENTITY_RECORD, case_id="X")
        citation = pred.attributes[0].citation
        assert citation.span_verified is True
        assert citation.page == 2


class TestBaselineInterface:
    def test_a_baseline_prediction_scores_through_the_same_code(self):
        """Naive fill-everything versus selective acceptance, one scorer."""
        naive = CasePrediction.model_validate(
            {
                "case_id": "TEST-100",
                "identity_disposition": "EXACT",
                "identity_mpn": "TEST-100-A",
                "attributes": [
                    {
                        "etim_feature_id": "EF001392",
                        "status": "ACCEPTED",
                        "value": {"kind": "numeric", "raw": "20 A", "number": 20.0, "unit": "A"},
                        "applicability": "APPLICABLE",
                        "has_verified_evidence": False,
                    }
                ],
            }
        )
        rep = report_for([case()], [naive])
        assert rep.attributes.committed_value_precision == Ratio(numerator=0, denominator=1)
        assert rep.attributes.unsupported_claim_rate == Ratio(numerator=1, denominator=1)
        assert rep.attributes.coverage == Ratio(numerator=1, denominator=1)
