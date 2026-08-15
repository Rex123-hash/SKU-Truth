"""Builders for evaluation tests. All fixtures here are obviously synthetic."""

from __future__ import annotations

from skutruth.contracts import (
    AlphanumericValue,
    Applicability,
    AttributeStatus,
    Condition,
    ConditionCompleteness,
    ConditionKind,
    ConditionSet,
    IdentityDisposition,
    IdentityScope,
    NumericValue,
    ProductInput,
    SupportGrade,
    WithheldReason,
)
from skutruth.eval import (
    CasePrediction,
    EvalCase,
    EvaluationManifest,
    ExpectedAttribute,
    ExpectedEvidence,
    ExpectedIdentity,
    PredictedAttribute,
    PredictedCitation,
    ReviewStatus,
    Split,
)

SHA = "a" * 64
OTHER_SHA = "b" * 64

AC3_400V = ConditionSet(
    conditions=(
        Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3"),
        Condition(kind=ConditionKind.VOLTAGE, value="400 V"),
    ),
    completeness=ConditionCompleteness.COMPLETE,
)
AC1_400V = ConditionSet(
    conditions=(
        Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-1"),
        Condition(kind=ConditionKind.VOLTAGE, value="400 V"),
    ),
    completeness=ConditionCompleteness.COMPLETE,
)

AMPS_18 = NumericValue(raw="18 A", number=18.0, unit="A")
AMPS_32 = NumericValue(raw="32 A", number=32.0, unit="A")


def expected_attr(**overrides) -> ExpectedAttribute:
    kwargs = {
        "etim_feature_id": "EF001392",
        "applicability": Applicability.APPLICABLE,
        "buyer_critical": True,
        "value": AMPS_18,
        "conditions": AC3_400V,
        "expected_status": AttributeStatus.ACCEPTED,
    }
    kwargs.update(overrides)
    return ExpectedAttribute(**kwargs)


def predicted_attr(**overrides) -> PredictedAttribute:
    kwargs = {
        "etim_feature_id": "EF001392",
        "status": AttributeStatus.ACCEPTED,
        "value": AMPS_18,
        "bound_conditions": AC3_400V,
        "applicability": Applicability.APPLICABLE,
        "support_grade": SupportGrade.A,
        "has_verified_evidence": True,
    }
    kwargs.update(overrides)
    return PredictedAttribute(**kwargs)


def withheld_attr(reason: WithheldReason = WithheldReason.NOT_FOUND, **overrides):
    return predicted_attr(
        status=AttributeStatus.WITHHELD,
        value=None,
        support_grade=None,
        withheld_reason=reason,
        has_verified_evidence=False,
        **overrides,
    )


def case(**overrides) -> EvalCase:
    kwargs = {
        "case_id": "TEST-100",
        "split": Split.DEV,
        "input": ProductInput(brand="TestCo", mpn="TEST-100-A", description="Synthetic"),
        "manufacturer": "TestCo",
        "product_family_id": "TEST-FAMILY-100",
        "etim_class_id": "EC000066",
        "expected_identity": ExpectedIdentity(
            disposition=IdentityDisposition.EXACT, exact_mpn="TEST-100-A"
        ),
        "expected_attributes": (expected_attr(),),
        "review_status": ReviewStatus.SYNTHETIC,
    }
    kwargs.update(overrides)
    return EvalCase(**kwargs)


def family_case(**overrides) -> EvalCase:
    kwargs = {
        "case_id": "TEST-200",
        "product_family_id": "TEST-FAMILY-200",
        "input": ProductInput(brand="TestCo", mpn="TEST-200", description="Synthetic family"),
        "expected_identity": ExpectedIdentity(
            disposition=IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE,
            missing_discriminators=("Synthetic coil code",),
        ),
        "expected_attributes": (),
    }
    kwargs.update(overrides)
    return case(**kwargs)


def prediction(**overrides) -> CasePrediction:
    kwargs = {
        "case_id": "TEST-100",
        "identity_disposition": IdentityDisposition.EXACT,
        "identity_mpn": "TEST-100-A",
        "attributes": (predicted_attr(),),
    }
    kwargs.update(overrides)
    return CasePrediction(**kwargs)


def manifest(cases, **overrides) -> EvaluationManifest:
    kwargs = {
        "manifest_id": "unit-test",
        "manifest_version": "1",
        "cases": tuple(cases),
    }
    kwargs.update(overrides)
    return EvaluationManifest.build(**kwargs)


def citation(**overrides) -> PredictedCitation:
    kwargs = {
        "artifact_id": "art-synthetic-1",
        "artifact_sha256": SHA,
        "page": 2,
        "quote": "18 A",
        "identity_scope": IdentityScope.EXACT_SKU,
        "span_verified": True,
    }
    kwargs.update(overrides)
    return PredictedCitation(**kwargs)


def evidence_fixture(**overrides) -> ExpectedEvidence:
    kwargs = {
        "artifact_id": "art-synthetic-1",
        "artifact_sha256": SHA,
        "page": 2,
        "quote": "18 A",
        "identity_scope": IdentityScope.EXACT_SKU,
    }
    kwargs.update(overrides)
    return ExpectedEvidence(**kwargs)


ENUM_AC = AlphanumericValue(raw="AC", text="AC", value_id="EV000123")
ENUM_DC = AlphanumericValue(raw="DC", text="DC", value_id="EV000124")
