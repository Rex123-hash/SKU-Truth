"""Shared builders for contract tests.

Defaults describe the hero case: an exact-SKU Schneider datasheet span for
`Rated operation current Ie at AC-3, 400 V` = 18 A, verified on page 2.
"""

from __future__ import annotations

from datetime import UTC, datetime

from skutruth.contracts import (
    Applicability,
    AttributeStatus,
    AttributeValue,
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
    covers_mpn: str | None = "LC1D18P7",
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
        covers_mpn=covers_mpn,
    )


def make_family_table_artifact(artifact_id: str = "art_family") -> SourceArtifact:
    """The Schneider TeSys D family/variant table: family-scoped, names no single child."""
    return make_artifact(
        artifact_id=artifact_id,
        url="https://example.invalid/tesys-d-family-selection-table.pdf",
        scope=IdentityScope.FAMILY,
        covers_mpn=None,
        sha="f" * 64,
    )


def make_evidence(
    *,
    evidence_id: str = "ev_1",
    artifact: SourceArtifact | None = None,
    verification: EvidenceVerification = EvidenceVerification.EXACT_SPAN,
    modality: EvidenceModality = EvidenceModality.SPEC_TABLE,
    conditions: ConditionSet | None = None,
    number: float = 18.0,
    unit: str = "A",
    observed: AttributeValue | None = None,
    page: int | None = 2,
    match_score: float | None = None,
    proves_family_scope: bool = False,
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
        observed_value=(
            observed
            if observed is not None
            else NumericValue(raw=f"{number:g} {unit}", number=number, unit=unit)
        ),
        conditions=conditions if conditions is not None else AC3_400V,
        proves_family_scope=proves_family_scope,
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
    unit: str = "A",
    members: list[Evidence] | None = None,
    conditions: ConditionSet | None = None,
) -> EvidenceGroup:
    conds = conditions if conditions is not None else AC3_400V
    return EvidenceGroup(
        group_id=group_id,
        representative_value=NumericValue(raw=f"{number:g} {unit}", number=number, unit=unit),
        conditions=conds,
        # The default member inherits the group's operating point; otherwise a caller
        # overriding `conditions` alone would build a group that contradicts itself.
        members=members or [make_evidence(number=number, unit=unit, conditions=conds)],
    )


def group_for(
    value: AttributeValue,
    *,
    group_id: str = "eg_1",
    conditions: ConditionSet | None = None,
) -> EvidenceGroup:
    """A group whose single span observed exactly `value` under `conditions`.

    Fixtures use this so an accepted value is always backed by evidence that actually
    states it. Building an attribute whose evidence says something else is the bug the
    contract now rejects, and it should take deliberate effort to express in a test.
    """
    conds = conditions if conditions is not None else AC3_400V
    return EvidenceGroup(
        group_id=group_id,
        representative_value=value,
        conditions=conds,
        members=[make_evidence(observed=value, conditions=conds)],
    )


def make_family_proof_group(group_id: str = "eg_family") -> EvidenceGroup:
    """A family variant table whose span proves the value holds across every child."""
    return make_group(
        group_id,
        members=[
            make_evidence(
                evidence_id="ev_family_table",
                artifact=make_family_table_artifact(),
                proves_family_scope=True,
            )
        ],
    )


def make_two_child_groups() -> tuple[EvidenceGroup, EvidenceGroup]:
    """Agreement across two distinct exact child references — the other route to PROVEN."""
    return (
        make_group(
            "eg_p7",
            members=[
                make_evidence(
                    evidence_id="ev_p7",
                    artifact=make_artifact(artifact_id="art_p7", covers_mpn="LC1D18P7"),
                )
            ],
        ),
        make_group(
            "eg_bd",
            members=[
                make_evidence(
                    evidence_id="ev_bd",
                    artifact=make_artifact(
                        artifact_id="art_bd", covers_mpn="LC1D18BD", sha="b" * 64
                    ),
                )
            ],
        ),
    )


#: The exact reference the default fixtures resolve to. Matches `EXACT_IDENTITY` and
#: `make_artifact`'s `covers_mpn`, so exact-SKU evidence is eligible by default.
ANCHOR_MPN = "LC1D18P7"


def make_attribute(**overrides) -> ProductAttribute:
    """An accepted, grade-A rated-current attribute unless overridden.

    When a caller overrides `value` or `bound_conditions` without supplying
    `evidence_groups`, the default group is rebuilt to match — otherwise the fixture
    would assert a value its evidence never stated, which the contract now rejects.
    """
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
        "identity_anchor_mpn": ANCHOR_MPN,
        "support_grade": SupportGrade.A,
    }
    kwargs.update(overrides)
    if "evidence_groups" not in overrides:
        value = kwargs["value"]
        kwargs["evidence_groups"] = (
            () if value is None else (group_for(value, conditions=kwargs["bound_conditions"]),)
        )
    return ProductAttribute(**kwargs)
