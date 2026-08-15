"""The evaluation report.

Deliberately has **no overall score.** There is no `SKUTruth Score = 91.4`, and there
will not be one. A single number would let a collapse in identity accuracy be paid
for with a rise in coverage, which is precisely the trade the reader most needs to
see. Identity, precision, unsupported claims, coverage, citations, normalisation and
cost are reported side by side, each with its own denominator.

Every rate is a `Ratio`, so the counts survive serialisation and rounding is left to
whatever finally prints the thing.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from skutruth.contracts import RunMode

from .manifest import CoverageSummary, EvaluationManifest
from .metrics import LatencySummary, Ratio
from .models import CasePrediction, Split
from .scoring import ScoreAccumulator, score_all, unexpected_predictions


class IdentityMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accuracy: Ratio
    false_exact: Ratio = Field(
        description="Truth was not EXACT and the system said EXACT. The most dangerous "
        "error available: it attaches correct specifications to the wrong reference."
    )


class AttributeMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    committed_value_precision: Ratio = Field(
        description="Correct accepted values / accepted values that truth can judge. "
        "Abstaining never counts as a wrong committed value."
    )
    unsupported_claim_rate: Ratio = Field(
        description="Accepted claims lacking verified evidence / all accepted claims."
    )
    coverage: Ratio = Field(
        description="Accepted / judgeable applicable claims. The price of abstention, "
        "kept separate from precision so the trade stays visible."
    )
    normalization_accuracy: Ratio = Field(
        description="Correct normalized representation — number, unit, ETIM value id — "
        "regardless of operating point."
    )
    precision_by_support_grade: dict[str, Ratio] = Field(
        default_factory=dict,
        description="Precision within each grade. A coarse ordering, not a probability: "
        "grade A does not mean 95% confident.",
    )

    @property
    def selective_risk(self) -> float | None:
        """1 - precision. `None` when nothing was committed, never 0."""
        rate = self.committed_value_precision.rate
        return None if rate is None else 1.0 - rate


class CitationMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    valid: int = Field(ge=0)
    invalid: int = Field(ge=0)
    not_evaluated: int = Field(
        ge=0,
        description="Claims whose citation could not be judged from fixture data. "
        "Reported rather than assumed valid; full verification awaits ingestion.",
    )

    @property
    def validity(self) -> Ratio:
        """Over the *evaluated* denominator only. `not_evaluated` is excluded."""
        return Ratio(numerator=self.valid, denominator=self.valid + self.invalid)


class BuyerCriticalMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    accepted: int = Field(ge=0)
    applicable: int = Field(ge=0)
    withheld: int = Field(ge=0)
    not_applicable: int = Field(ge=0)
    unknown_applicability: int = Field(ge=0)

    @property
    def coverage(self) -> Ratio:
        """Accepted / applicable. Inapplicable features are not gaps and are excluded."""
        return Ratio(numerator=self.accepted, denominator=self.applicable)


class UsageTotals(BaseModel):
    """Summed usage, with absence preserved.

    A field stays `None` when no prediction reported it. Turning "nobody told us" into
    zero would understate cost and let an unmeasured run look free.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost_by_currency: dict[str, float] = Field(
        default_factory=dict,
        description="Keyed by currency. Costs in different currencies are never summed, "
        "because there is no exchange rate we would be entitled to invent.",
    )
    predictions_reporting_cost: int = Field(default=0, ge=0)


class OperationsMetrics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: int = Field(ge=0)
    interactions: int = Field(ge=0)
    run_mode_counts: dict[str, int] = Field(default_factory=dict)
    usage: UsageTotals = Field(default_factory=UsageTotals)
    provider_latency: LatencySummary = Field(
        description="Latency the provider took, from cassette capture. On a replayed "
        "run this is the recorded figure, not what replay just cost."
    )
    evaluation_latency: LatencySummary = Field(
        description="Wall time this evaluation spent. Replaying a cassette is fast and "
        "says nothing about the provider."
    )
    outcome_counts: dict[str, int] = Field(
        default_factory=dict, description="Every case outcome, failures included"
    )
    failed_cases: int = Field(default=0, ge=0)


class EvaluationReport(BaseModel):
    """A complete, self-describing evaluation result."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_id: str
    manifest_version: str
    manifest_fingerprint: str = Field(
        description="Ties these numbers to an exact set of truth. If the locked truth "
        "moves, the fingerprint moves with it."
    )
    split: Split
    generated_at: datetime
    system_label: str = Field(
        default="skutruth", description="Which system produced the predictions"
    )
    contains_only_synthetic_cases: bool = Field(
        default=False,
        description="True when every case is a structural fixture. Such a report is "
        "proof the scorer works, and must never be quoted as benchmark performance.",
    )

    coverage_summary: CoverageSummary
    identity: IdentityMetrics
    attributes: AttributeMetrics
    citations: CitationMetrics
    buyer_critical: BuyerCriticalMetrics
    operations: OperationsMetrics
    unexpected_prediction_ids: tuple[str, ...] = ()

    def headline_lines(self) -> list[str]:
        """Each metric with its counts. No composite, by design."""
        a = self.attributes
        lines = [
            f"identity accuracy            {self.identity.accuracy.display()}",
            f"false exact                  {self.identity.false_exact.display()}",
            f"committed value precision    {a.committed_value_precision.display()}",
            f"unsupported claim rate       {a.unsupported_claim_rate.display()}",
            f"coverage                     {a.coverage.display()}",
            f"normalization accuracy       {a.normalization_accuracy.display()}",
            f"citation validity            {self.citations.validity.display()} "
            f"({self.citations.not_evaluated} not evaluated)",
            f"buyer-critical coverage      {self.buyer_critical.coverage.display()}",
            f"failed cases                 {self.operations.failed_cases}",
        ]
        if self.contains_only_synthetic_cases:
            lines.insert(0, "SYNTHETIC FIXTURES — NOT A BENCHMARK RESULT")
        return lines


def build_report(
    manifest: EvaluationManifest,
    predictions: dict[str, CasePrediction],
    *,
    split: Split,
    system_label: str = "skutruth",
    generated_at: datetime | None = None,
) -> EvaluationReport:
    """Score a split of a manifest and assemble the report."""
    cases = manifest.for_split(split)
    acc = score_all(cases, predictions)
    relevant = [predictions[c.case_id] for c in cases if c.case_id in predictions]

    return EvaluationReport(
        manifest_id=manifest.manifest_id,
        manifest_version=manifest.manifest_version,
        manifest_fingerprint=manifest.fingerprint(),
        split=split,
        generated_at=generated_at or datetime.now(UTC),
        system_label=system_label,
        contains_only_synthetic_cases=bool(cases) and all(c.is_synthetic for c in cases),
        coverage_summary=manifest.coverage(split),
        identity=IdentityMetrics(
            accuracy=acc.identity.to_ratio(), false_exact=acc.false_exact.to_ratio()
        ),
        attributes=AttributeMetrics(
            committed_value_precision=acc.committed_precision.to_ratio(),
            unsupported_claim_rate=acc.supported_claims.to_ratio().complement(),
            coverage=acc.coverage.to_ratio(),
            normalization_accuracy=acc.normalization.to_ratio(),
            precision_by_support_grade={
                grade: tally.to_ratio() for grade, tally in sorted(acc.precision_by_grade.items())
            },
        ),
        citations=CitationMetrics(
            valid=acc.citations_valid,
            invalid=acc.citations_invalid,
            not_evaluated=acc.citations_not_evaluated,
        ),
        buyer_critical=BuyerCriticalMetrics(
            accepted=acc.buyer_critical_accepted,
            applicable=acc.buyer_critical_applicable,
            withheld=acc.buyer_critical_withheld,
            not_applicable=acc.buyer_critical_not_applicable,
            unknown_applicability=acc.buyer_critical_unknown,
        ),
        operations=_operations(cases, relevant, acc),
        unexpected_prediction_ids=unexpected_predictions(cases, predictions),
    )


def _operations(cases, predictions: list[CasePrediction], acc: ScoreAccumulator):
    modes: dict[str, int] = {}
    for p in predictions:
        if p.provenance is not None:
            key = p.provenance.mode.value
            modes[key] = modes.get(key, 0) + 1

    provider_latency = [s for p in predictions for s in p.provider_latency_seconds]
    eval_latency = [p.evaluation_seconds for p in predictions if p.evaluation_seconds is not None]

    usage = UsageTotals(
        input_tokens=_sum_or_none(p.input_tokens for p in predictions),
        output_tokens=_sum_or_none(p.output_tokens for p in predictions),
        total_tokens=_sum_or_none(p.total_tokens for p in predictions),
        cost_by_currency=_cost_by_currency(predictions),
        predictions_reporting_cost=sum(1 for p in predictions if p.provider_reported_cost),
    )

    return OperationsMetrics(
        cases=len(cases),
        interactions=sum(p.interaction_count for p in predictions),
        run_mode_counts=dict(sorted(modes.items())),
        usage=usage,
        provider_latency=LatencySummary.from_samples(provider_latency),
        evaluation_latency=LatencySummary.from_samples(eval_latency),
        outcome_counts=dict(sorted(acc.outcomes.items())),
        failed_cases=sum(n for k, n in acc.outcomes.items() if k != "SCORED"),
    )


def _sum_or_none(values) -> int | None:
    """Sum reported values, or `None` if none were reported. Never a fabricated zero."""
    present = [v for v in values if v is not None]
    return sum(present) if present else None


def _cost_by_currency(predictions: list[CasePrediction]) -> dict[str, float]:
    """Costs bucketed by currency, and only where the provider actually reported one."""
    out: dict[str, float] = {}
    for p in predictions:
        if p.provider_reported_cost is None:
            continue
        currency = p.currency or "UNSPECIFIED"
        out[currency] = out.get(currency, 0.0) + p.provider_reported_cost
    return dict(sorted(out.items()))


def assert_no_composite_score(report: EvaluationReport) -> None:
    """Guard against a future 'overall score' creeping in.

    A composite would let a collapse in identity accuracy be paid for with a rise in
    coverage. Keeping the metrics separate is a design commitment, so it is tested.
    """
    banned = {"overall_score", "score", "skutruth_score", "composite", "grade"}
    present = set(EvaluationReport.model_fields) & banned
    if present:  # pragma: no cover - guarded by test
        raise AssertionError(f"report exposes a composite score field: {sorted(present)}")


__all__ = [
    "AttributeMetrics",
    "BuyerCriticalMetrics",
    "CitationMetrics",
    "EvaluationReport",
    "IdentityMetrics",
    "OperationsMetrics",
    "RunMode",
    "UsageTotals",
    "assert_no_composite_score",
    "build_report",
]
