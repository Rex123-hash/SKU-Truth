"""Shared builders for contract tests.

Defaults describe the hero case: an exact-SKU Schneider datasheet span for
`Rated operation current Ie at AC-3, 400 V` = 18 A, verified on page 2.
"""

from __future__ import annotations

from datetime import UTC, datetime

from skutruth.contracts import (
    Applicability,
    AttributeStatus,
    Condition,
    ConditionCompleteness,
    ConditionKind,
    ConditionSet,
    DiscoveryMethod,
    EtimFeatureType,
    Evidence,
    EvidenceGroup,
    EvidenceModality,
    EvidenceVerification,
    FamilyInvariance,
    IdentityScope,
    NumericValue,
    ProductAttribute,
    RunMode,
    SourceArtifact,
    SourceType,
    SpanLocator,
    SupportGrade,
)

DATASHEET_URL = "https://iportal.se.com/Contents/docs/SQD-LC1D18P7_DATASHEET.PDF"

AC3_400V = ConditionSet(
    conditions=(
        Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3", raw="AC-3"),
        Condition(kind=ConditionKind.VOLTAGE, value="400 V", raw="400 V"),
    ),
    completeness=ConditionCompleteness.COMPLETE,
)

AC1_400V = ConditionSet(
    conditions=(
        Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-1", raw="AC-1"),
        Condition(kind=ConditionKind.VOLTAGE, value="400 V", raw="400 V"),
    ),
    completeness=ConditionCompleteness.COMPLETE,
)


def make_artifact(
    *,
    artifact_id: str = "art_1",
    url: str = DATASHEET_URL,
    source_type: SourceType = SourceType.MANUFACTURER_DATASHEET,
    scope: IdentityScope = IdentityScope.EXACT_SKU,
    sha: str | None = None,
    discovery: DiscoveryMethod = DiscoveryMethod.CURATED_CORPUS,
) -> SourceArtifact:
    return SourceArtifact(
        artifact_id=artifact_id,
        sha256=sha or ("a" * 64),
        final_url=url,
        discovery_method=discovery,
        publisher="Schneider Electric",
        source_type=source_type,
        page_count=5,
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
        identity_scope=scope,
    )


def make_evidence(
    *,
    evidence_id: str = "ev_1",
    artifact: SourceArtifact | None = None,
    verification: EvidenceVerification = EvidenceVerification.EXACT_SPAN,
    modality: EvidenceModality = EvidenceModality.SPEC_TABLE,
    conditions: ConditionSet | None = None,
    number: float = 18.0,
    page: int | None = 2,
    match_score: float | None = None,
) -> Evidence:
    return Evidence(
        evidence_id=evidence_id,
        artifact=artifact or make_artifact(),
        locator=SpanLocator(
            page=page,
            section="Main characteristics",
            row_header="Rated operational current Ie",
            column_header="AC-3 400 V",
            table_index=0,
            row_index=7,
        ),
        raw_fragment="Rated operational current Ie  AC-3 400 V  18 A",
        normalized_quote="rated operational current ie ac-3 400 v 18 a",
        modality=modality,
        verification=verification,
        match_score=match_score,
        observed_value=NumericValue(raw=f"{number:g} A", number=number, unit="A"),
        conditions=conditions if conditions is not None else AC3_400V,
        extraction_model="gemini-3.1-flash-lite",
        prompt_version="extract@v1",
        schema_version="etim-class@v1",
        run_mode=RunMode.REPLAY,
        run_id="run_1",
    )


def make_group(
    group_id: str = "eg_1",
    *,
    number: float = 18.0,
    members: list[Evidence] | None = None,
    conditions: ConditionSet | None = None,
) -> EvidenceGroup:
    return EvidenceGroup(
        group_id=group_id,
        representative_value=NumericValue(raw=f"{number:g} A", number=number, unit="A"),
        conditions=conditions if conditions is not None else AC3_400V,
        members=members or [make_evidence(number=number)],
    )


def make_attribute(**overrides) -> ProductAttribute:
    """An accepted, grade-A rated-current attribute unless overridden."""
    kwargs = {
        "etim_feature_id": "EF001392",
        "name": "Rated operation current Ie at AC-3, 400 V",
        "feature_type": EtimFeatureType.NUMERIC,
        "expected_unit": "A",
        "buyer_critical": True,
        "applicability": Applicability.APPLICABLE,
        "status": AttributeStatus.ACCEPTED,
        "value": NumericValue(raw="18 A", number=18.0, unit="A"),
        "bound_conditions": AC3_400V,
        "family_invariance": FamilyInvariance.NOT_REQUIRED,
        "support_grade": SupportGrade.A,
        "evidence_groups": (make_group(),),
    }
    kwargs.update(overrides)
    return ProductAttribute(**kwargs)
