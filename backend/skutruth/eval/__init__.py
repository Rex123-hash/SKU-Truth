"""Deterministic evaluation.

Built before the model-backed system it measures, so the metrics cannot be chosen to
flatter whatever the system turns out to do. See data/eval/README.md for the process
discipline around locked truth.
"""

from .manifest import (
    DEFAULT_MANIFEST_DIR,
    MANIFEST_SCHEMA_VERSION,
    CoverageSummary,
    EvaluationManifest,
    ManifestValidationError,
    available_manifests,
    load_manifest,
    load_named_manifest,
    validate_against_etim,
    validate_cases,
)
from .metrics import LatencySummary, Ratio, Tally
from .models import (
    CaseOutcome,
    CasePrediction,
    CitationOutcome,
    EvalCase,
    ExpectedAttribute,
    ExpectedEvidence,
    ExpectedIdentity,
    PredictedAttribute,
    PredictedCitation,
    ReviewStatus,
    Split,
    prediction_from_golden_record,
)
from .replay_policy import cassette_store_for, is_locked_evaluation
from .report import (
    AttributeMetrics,
    BuyerCriticalMetrics,
    CitationMetrics,
    EvaluationReport,
    IdentityMetrics,
    OperationsMetrics,
    UsageTotals,
    assert_no_composite_score,
    build_report,
)
from .scoring import (
    AttributeJudgement,
    ScoreAccumulator,
    conditions_agree,
    score_all,
    score_case,
    unexpected_predictions,
    values_agree,
)

__all__ = [
    "DEFAULT_MANIFEST_DIR",
    "MANIFEST_SCHEMA_VERSION",
    "AttributeJudgement",
    "AttributeMetrics",
    "BuyerCriticalMetrics",
    "CaseOutcome",
    "CasePrediction",
    "CitationMetrics",
    "CitationOutcome",
    "CoverageSummary",
    "EvalCase",
    "EvaluationManifest",
    "EvaluationReport",
    "ExpectedAttribute",
    "ExpectedEvidence",
    "ExpectedIdentity",
    "IdentityMetrics",
    "LatencySummary",
    "ManifestValidationError",
    "OperationsMetrics",
    "PredictedAttribute",
    "PredictedCitation",
    "Ratio",
    "ReviewStatus",
    "ScoreAccumulator",
    "Split",
    "Tally",
    "UsageTotals",
    "assert_no_composite_score",
    "available_manifests",
    "build_report",
    "cassette_store_for",
    "conditions_agree",
    "is_locked_evaluation",
    "load_manifest",
    "load_named_manifest",
    "prediction_from_golden_record",
    "score_all",
    "score_case",
    "unexpected_predictions",
    "validate_against_etim",
    "validate_cases",
    "values_agree",
]
