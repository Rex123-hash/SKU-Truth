"""The contract invariants are the product. These tests are the lock on them."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest import (
    AC1_400V,
    AC3_400V,
    make_artifact,
    make_attribute,
    make_evidence,
    make_group,
)
from pydantic import ValidationError
from skutruth.contracts import (
    AlphanumericValue,
    Applicability,
    AttributeStatus,
    Condition,
    ConditionCompleteness,
    ConditionKind,
    ConditionSet,
    Conflict,
    ConflictCause,
    Derivation,
    DerivationKind,
    EtimFeatureType,
    EvidenceModality,
    EvidenceVerification,
    FamilyInvariance,
    GoldenRecord,
    IdentityDisposition,
    IdentityScope,
    LogicalValue,
    NumericValue,
    ProductIdentity,
    ProductInput,
    RangeValue,
    ResolvedBy,
    RunMode,
    RunProvenance,
    SourceType,
    SupportGrade,
    VariantAxis,
    WithheldReason,
    compute_support_factors,
    derive_support_grade,
)

# --------------------------------------------------------------------------------------
# Invariant 1 — no acceptance without a span we located ourselves
# --------------------------------------------------------------------------------------


class TestAcceptedValuesNeedAVerifiedSpan:
    def test_accepted_value_with_no_evidence_is_rejected(self):
        with pytest.raises(ValidationError, match="no verified span"):
            make_attribute(evidence_groups=())

    def test_unverified_evidence_cannot_support_acceptance(self):
        """A model can fabricate a quote. Only a located span licenses acceptance."""
        unverified = make_group(
            members=[make_evidence(verification=EvidenceVerification.UNVERIFIED, page=None)]
        )
        with pytest.raises(ValidationError, match="no verified span"):
            make_attribute(evidence_groups=(unverified,))

    def test_exact_span_supports_acceptance(self):
        assert make_attribute().is_accepted

    def test_fuzzy_ocr_span_supports_acceptance_at_a_lower_grade(self):
        group = make_group(
            members=[
                make_evidence(
                    verification=EvidenceVerification.FUZZY_OCR_SPAN,
                    modality=EvidenceModality.IMAGE_OCR,
                    match_score=0.91,
                )
            ]
        )
        attr = make_attribute(evidence_groups=(group,))
        assert attr.support_grade is SupportGrade.A  # still manufacturer + exact + conditions

    def test_verified_span_must_record_a_page(self):
        with pytest.raises(ValidationError, match="no page is recorded"):
            make_evidence(page=None)

    def test_fuzzy_span_must_record_its_match_score(self):
        with pytest.raises(ValidationError, match="match_score"):
            make_evidence(verification=EvidenceVerification.FUZZY_OCR_SPAN, match_score=None)


# --------------------------------------------------------------------------------------
# Invariant 2 — status, applicability and reason are separate axes
# --------------------------------------------------------------------------------------


class TestStatusApplicabilityAndReasonAreSeparate:
    def test_withheld_must_say_why(self):
        with pytest.raises(ValidationError, match="requires a withheld_reason"):
            make_attribute(
                status=AttributeStatus.WITHHELD,
                value=None,
                support_grade=None,
                evidence_groups=(),
            )

    @pytest.mark.parametrize(
        "reason",
        [
            WithheldReason.NOT_FOUND,
            WithheldReason.VARIANT_DEPENDENT,
            WithheldReason.CONFLICTED,
            WithheldReason.UNSUPPORTED_SPAN,
            WithheldReason.OUT_OF_IDENTITY_SCOPE,
        ],
        ids=lambda r: r.value,
    )
    def test_each_withheld_reason_is_representable(self, reason):
        attr = make_attribute(
            status=AttributeStatus.WITHHELD,
            value=None,
            support_grade=None,
            withheld_reason=reason,
            evidence_groups=(),
        )
        assert attr.withheld_reason is reason
        assert not attr.is_accepted

    def test_withheld_may_retain_evidence_for_the_reviewer(self):
        """A variant-dependent abstention still shows what it found per variant."""
        attr = make_attribute(
            status=AttributeStatus.WITHHELD,
            value=None,
            support_grade=None,
            withheld_reason=WithheldReason.VARIANT_DEPENDENT,
            evidence_groups=(make_group("eg_1", number=24.0), make_group("eg_2", number=230.0)),
        )
        assert len(attr.evidence_groups) == 2

    def test_accepted_must_not_carry_a_reason(self):
        with pytest.raises(ValidationError, match="must not carry a withheld_reason"):
            make_attribute(withheld_reason=WithheldReason.NOT_FOUND)

    def test_accepted_requires_a_value(self):
        with pytest.raises(ValidationError, match="ACCEPTED requires a value"):
            make_attribute(value=None)

    def test_withheld_must_not_carry_a_value(self):
        with pytest.raises(ValidationError, match="must not carry a value"):
            make_attribute(
                status=AttributeStatus.WITHHELD,
                withheld_reason=WithheldReason.NOT_FOUND,
                support_grade=None,
            )


class TestApplicability:
    def test_not_applicable_cannot_be_accepted(self):
        with pytest.raises(ValidationError, match="NOT_APPLICABLE feature cannot carry"):
            make_attribute(applicability=Applicability.NOT_APPLICABLE)

    def test_not_applicable_reason_requires_not_applicable_applicability(self):
        with pytest.raises(ValidationError, match="applicability is not NOT_APPLICABLE"):
            make_attribute(
                status=AttributeStatus.WITHHELD,
                value=None,
                support_grade=None,
                withheld_reason=WithheldReason.NOT_APPLICABLE,
                applicability=Applicability.APPLICABLE,
                evidence_groups=(),
            )

    def test_not_applicable_is_not_a_gap(self):
        attr = make_attribute(
            status=AttributeStatus.WITHHELD,
            value=None,
            support_grade=None,
            withheld_reason=WithheldReason.NOT_APPLICABLE,
            applicability=Applicability.NOT_APPLICABLE,
            evidence_groups=(),
        )
        assert not attr.counts_toward_coverage


# --------------------------------------------------------------------------------------
# Invariant 3 — support grade is derived from evidence quality, not cluster count
# --------------------------------------------------------------------------------------


class TestSupportGradeRule:
    def test_single_exact_manufacturer_span_reaches_grade_a(self):
        """The correction to the earlier rule: one strong source is enough for A."""
        attr = make_attribute(evidence_groups=(make_group(),))
        assert len(attr.evidence_groups) == 1
        assert attr.support_grade is SupportGrade.A

    def test_distributor_source_drops_to_grade_b(self):
        group = make_group(
            members=[
                make_evidence(
                    artifact=make_artifact(source_type=SourceType.AUTHORIZED_DISTRIBUTOR)
                )
            ]
        )
        attr = make_attribute(evidence_groups=(group,), support_grade=SupportGrade.B)
        assert attr.support_grade is SupportGrade.B

    def test_family_scope_artifact_drops_to_grade_b(self):
        group = make_group(
            members=[make_evidence(artifact=make_artifact(scope=IdentityScope.FAMILY))]
        )
        attr = make_attribute(
            evidence_groups=(group,),
            family_invariance=FamilyInvariance.NOT_REQUIRED,
            support_grade=SupportGrade.B,
        )
        assert attr.support_grade is SupportGrade.B

    def test_partial_conditions_drop_to_grade_b(self):
        partial = ConditionSet(
            conditions=(Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3"),),
            completeness=ConditionCompleteness.PARTIAL,
            missing_kinds=(ConditionKind.VOLTAGE,),
        )
        group = make_group(members=[make_evidence(conditions=partial)], conditions=partial)
        attr = make_attribute(
            bound_conditions=partial, evidence_groups=(group,), support_grade=SupportGrade.B
        )
        assert attr.support_grade is SupportGrade.B

    def test_two_weaknesses_drop_to_grade_c(self):
        group = make_group(
            members=[
                make_evidence(
                    artifact=make_artifact(
                        source_type=SourceType.GENERAL_WEB, scope=IdentityScope.RANGE
                    ),
                    modality=EvidenceModality.PROSE,
                )
            ]
        )
        attr = make_attribute(evidence_groups=(group,), support_grade=SupportGrade.C)
        assert attr.support_grade is SupportGrade.C

    def test_grade_cannot_be_hand_set(self):
        group = make_group(
            members=[
                make_evidence(
                    artifact=make_artifact(source_type=SourceType.GENERAL_WEB),
                )
            ]
        )
        with pytest.raises(ValidationError, match="grades are computed, not set"):
            make_attribute(evidence_groups=(group,), support_grade=SupportGrade.A)

    def test_withheld_attribute_must_not_carry_a_grade(self):
        with pytest.raises(ValidationError, match="must not carry a support grade"):
            make_attribute(
                status=AttributeStatus.WITHHELD,
                value=None,
                withheld_reason=WithheldReason.NOT_FOUND,
                evidence_groups=(),
                support_grade=SupportGrade.C,
            )

    def test_extra_agreeing_members_do_not_raise_the_grade_in_p0(self):
        """Until evidence-root deduplication exists, copies must not buy confidence."""
        weak = make_artifact(source_type=SourceType.AUTHORIZED_DISTRIBUTOR)
        one = make_group(members=[make_evidence(evidence_id="ev_1", artifact=weak)])
        three = make_group(
            members=[
                make_evidence(evidence_id="ev_1", artifact=weak),
                make_evidence(evidence_id="ev_2", artifact=weak),
                make_evidence(evidence_id="ev_3", artifact=weak),
            ]
        )
        assert make_attribute(
            evidence_groups=(one,), support_grade=SupportGrade.B
        ).support_grade is make_attribute(
            evidence_groups=(three,), support_grade=SupportGrade.B
        ).support_grade

    def test_rule_refuses_to_grade_unverified_evidence(self):
        factors = compute_support_factors(
            [make_evidence(verification=EvidenceVerification.UNVERIFIED, page=None)],
            family_invariance=FamilyInvariance.NOT_REQUIRED,
            condition_completeness=ConditionCompleteness.COMPLETE,
        )
        assert derive_support_grade(factors) is None

    def test_factors_record_why(self):
        factors = compute_support_factors(
            [make_evidence(artifact=make_artifact(source_type=SourceType.GENERAL_WEB))],
            family_invariance=FamilyInvariance.NOT_REQUIRED,
            condition_completeness=ConditionCompleteness.COMPLETE,
        )
        assert any("No manufacturer artifact" in n for n in factors.notes)
        assert factors.factors["manufacturer_origin"] == 0.0

    def test_independent_root_count_is_logged_but_unused(self):
        """Logged from day one so P1 clustering has history; not read by the P0 rule."""
        base = compute_support_factors(
            [make_evidence()],
            family_invariance=FamilyInvariance.NOT_REQUIRED,
            condition_completeness=ConditionCompleteness.COMPLETE,
        )
        logged = compute_support_factors(
            [make_evidence()],
            family_invariance=FamilyInvariance.NOT_REQUIRED,
            condition_completeness=ConditionCompleteness.COMPLETE,
            independent_root_count=4,
        )
        assert "independent_root_count" not in base.factors
        assert logged.factors["independent_root_count"] == 4.0
        assert derive_support_grade(base) is derive_support_grade(logged)


# --------------------------------------------------------------------------------------
# Invariant 4 — identity gates acceptance; family invariance must be proven
# --------------------------------------------------------------------------------------


class TestIdentityDisposition:
    def test_incomplete_reference_must_name_its_discriminator(self):
        with pytest.raises(ValidationError, match="must name the unbound discriminator"):
            ProductIdentity(
                disposition=IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE,
                reasoning="looks incomplete",
            )

    def test_incomplete_reference_with_a_variant_axis_is_accepted(self):
        identity = ProductIdentity(
            disposition=IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE,
            brand_normalized="Schneider Electric",
            mpn_normalized="LC1D18",
            reasoning=(
                "Exact Schneider references append a coil-voltage code (e.g. LC1D18P7, "
                "LC1D18BD); the supplied reference leaves that discriminator unbound."
            ),
            variant_axes=(
                VariantAxis(
                    name="Rated control supply voltage",
                    observed_options=("24 V DC", "230 V AC"),
                    example_mpns=("LC1D18BD", "LC1D18P7"),
                    evidence_ids=("ev_1",),
                ),
            ),
        )
        assert not identity.is_exact

    def test_contradictory_lists_rival_readings(self):
        with pytest.raises(ValidationError, match="at least two rival readings"):
            ProductIdentity(
                disposition=IdentityDisposition.CONTRADICTORY,
                reasoning="two products match",
                candidate_mpns=("LC1D18P7",),
            )

    def test_unknown_needs_no_extra_structure(self):
        identity = ProductIdentity(
            disposition=IdentityDisposition.UNKNOWN,
            reasoning="No artifact anywhere mentions this reference.",
        )
        assert identity.disposition is IdentityDisposition.UNKNOWN


def _record(identity: ProductIdentity, attributes: tuple, **overrides) -> GoldenRecord:
    kwargs = {
        "record_id": "rec_1",
        "run_id": "run_1",
        "created_at": datetime(2026, 8, 9, tzinfo=UTC),
        "provenance": RunProvenance(
            mode=RunMode.REPLAY, captured_at=datetime(2026, 8, 9, tzinfo=UTC)
        ),
        "input": ProductInput(brand="Schneider Electric", mpn="LC1D18", description="Contactor"),
        "identity": identity,
        "etim_class_id": "EC000066",
        "etim_class_name": "Power contactor, AC switching",
        "attributes": attributes,
    }
    kwargs.update(overrides)
    return GoldenRecord(**kwargs)


EXACT_IDENTITY = ProductIdentity(
    disposition=IdentityDisposition.EXACT,
    mpn_normalized="LC1D18P7",
    reasoning="Exact reference located in a manufacturer datasheet.",
)

FAMILY_IDENTITY = ProductIdentity(
    disposition=IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE,
    mpn_normalized="LC1D18",
    reasoning="Coil-voltage discriminator unbound.",
    variant_axes=(
        VariantAxis(name="Rated control supply voltage", observed_options=("24 V DC", "230 V AC")),
    ),
)


class TestIdentityGatesAcceptance:
    def test_family_identity_blocks_unproven_attributes(self):
        """Observing one child does not prove invariance across the family."""
        with pytest.raises(ValidationError, match="family_invariance=PROVEN"):
            _record(FAMILY_IDENTITY, (make_attribute(),))

    def test_family_identity_allows_proven_invariants(self):
        attr = make_attribute(family_invariance=FamilyInvariance.PROVEN)
        record = _record(FAMILY_IDENTITY, (attr,))
        assert record.accepted[0].family_invariance is FamilyInvariance.PROVEN

    def test_family_identity_withholds_variant_dependent_attributes(self):
        withheld = make_attribute(
            etim_feature_id="EF003978",
            name="Rated control supply voltage AC 50 Hz",
            feature_type=EtimFeatureType.RANGE,
            expected_unit="V",
            status=AttributeStatus.WITHHELD,
            value=None,
            support_grade=None,
            withheld_reason=WithheldReason.VARIANT_DEPENDENT,
            family_invariance=FamilyInvariance.UNPROVEN,
            evidence_groups=(),
        )
        record = _record(FAMILY_IDENTITY, (withheld,))
        assert record.withheld[0].withheld_reason is WithheldReason.VARIANT_DEPENDENT

    def test_unproven_invariance_cannot_be_accepted_at_all(self):
        with pytest.raises(ValidationError, match="must be withheld"):
            make_attribute(family_invariance=FamilyInvariance.UNPROVEN)

    def test_exact_identity_must_not_claim_family_proofs(self):
        with pytest.raises(ValidationError, match="family invariance is NOT_REQUIRED"):
            _record(EXACT_IDENTITY, (make_attribute(family_invariance=FamilyInvariance.PROVEN),))

    def test_exact_identity_accepts_normally(self):
        record = _record(EXACT_IDENTITY, (make_attribute(),))
        assert len(record.accepted) == 1


# --------------------------------------------------------------------------------------
# Conditions — the AC-1 / AC-3 distinction
# --------------------------------------------------------------------------------------


class TestConditions:
    def test_different_utilization_categories_are_different_operating_points(self):
        """18 A at AC-3 and 32 A at AC-1 are not a contradiction."""
        assert not AC3_400V.describes_same_operating_point_as(AC1_400V)

    def test_condition_key_is_order_independent(self):
        reversed_set = ConditionSet(
            conditions=(
                Condition(kind=ConditionKind.VOLTAGE, value="400 V"),
                Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3"),
            ),
            completeness=ConditionCompleteness.COMPLETE,
        )
        assert AC3_400V.describes_same_operating_point_as(reversed_set)

    def test_missing_kinds_are_recorded(self):
        partial = ConditionSet(
            conditions=(Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3"),),
            completeness=ConditionCompleteness.PARTIAL,
            missing_kinds=(ConditionKind.VOLTAGE,),
        )
        assert not partial.is_complete
        assert ConditionKind.VOLTAGE in partial.missing_kinds

    def test_lookup_by_kind(self):
        assert AC3_400V.get(ConditionKind.UTILIZATION_CATEGORY).value == "AC-3"
        assert AC3_400V.get(ConditionKind.TEMPERATURE) is None


class TestConflicts:
    def test_qualifier_difference_is_not_a_factual_conflict(self):
        conflict = Conflict(
            cause=ConflictCause.QUALIFIER,
            group_ids=["eg_1", "eg_2"],
            explanation="18 A is the AC-3 400 V rating; 32 A is the AC-1 rating.",
            resolution="Bound each value to its own ETIM feature.",
            resolved_by=ResolvedBy.DETERMINISTIC,
        )
        assert conflict.cause is not ConflictCause.FACTUAL

    def test_a_model_may_not_resolve_a_factual_conflict(self):
        with pytest.raises(ValidationError, match="may not be resolved by a model"):
            Conflict(
                cause=ConflictCause.FACTUAL,
                group_ids=["eg_1", "eg_2"],
                explanation="Same SKU, same conditions, different values.",
                resolution="picked the datasheet",
                resolved_by=ResolvedBy.ESCALATED_MODEL,
            )

    def test_a_factual_conflict_may_go_to_a_person(self):
        conflict = Conflict(
            cause=ConflictCause.FACTUAL,
            group_ids=["eg_1", "eg_2"],
            explanation="Same SKU, same conditions, different values.",
            resolved_by=ResolvedBy.HUMAN,
        )
        assert conflict.resolved_by is ResolvedBy.HUMAN


# --------------------------------------------------------------------------------------
# Values, derivation lineage, and ETIM type binding
# --------------------------------------------------------------------------------------


class TestValueTyping:
    def test_value_kind_must_match_the_etim_feature_type(self):
        with pytest.raises(ValidationError, match="requires a 'numeric' value"):
            make_attribute(value=AlphanumericValue(raw="18 A", text="18 A"))

    def test_unit_must_match_what_etim_mandates(self):
        with pytest.raises(ValidationError, match="mandates unit 'A'"):
            make_attribute(value=NumericValue(raw="18000 mA", number=18000.0, unit="mA"))

    def test_logical_feature_takes_a_boolean(self):
        attr = make_attribute(
            etim_feature_id="EF001126",
            name="Suitable for distribution board",
            feature_type=EtimFeatureType.LOGICAL,
            expected_unit=None,
            value=LogicalValue(raw="yes", boolean=True),
        )
        assert attr.value.display() == "Yes"


class TestDerivationLineage:
    def test_normalized_value_needs_lineage_not_a_second_quote(self):
        """18000 mA -> 18 A is supported by the quote for the raw value plus a transform."""
        group = make_group(
            members=[
                make_evidence(number=18000.0),  # source said 18000 mA; quote covers the raw text
            ]
        )
        attr = make_attribute(
            value=NumericValue(
                raw="18000 mA",
                number=18.0,
                unit="A",
                derivation=Derivation(
                    kind=DerivationKind.UNIT_CONVERSION,
                    transform_id="unit_conversion@v1",
                    detail="18000 mA -> 18 A (x1e-3)",
                ),
            ),
            evidence_groups=(group,),
        )
        assert attr.value.number == 18.0
        assert attr.value.raw == "18000 mA"
        assert attr.value.derivation.kind is DerivationKind.UNIT_CONVERSION

    def test_non_verbatim_derivation_must_explain_itself(self):
        with pytest.raises(ValidationError, match="must record a `detail` trace"):
            Derivation(kind=DerivationKind.UNIT_CONVERSION, transform_id="unit_conversion@v1")

    def test_verbatim_is_the_default(self):
        assert NumericValue(raw="18 A", number=18.0, unit="A").derivation.is_verbatim


class TestRangeIsWellFormed:
    def test_inverted_range_is_rejected(self):
        with pytest.raises(ValidationError, match="exceeds maximum"):
            RangeValue(raw="230-24 V", minimum=230.0, maximum=24.0, unit="V")

    def test_ordered_range_is_accepted(self):
        assert RangeValue(raw="24-230 V", minimum=24.0, maximum=230.0, unit="V").maximum == 230.0

    def test_degenerate_range_is_allowed(self):
        assert RangeValue(raw="24 V", minimum=24.0, maximum=24.0, unit="V").minimum == 24.0


# --------------------------------------------------------------------------------------
# Evidence presentation and locators
# --------------------------------------------------------------------------------------


class TestEvidencePresentation:
    def test_best_member_prefers_verified_exact_manufacturer_table(self):
        group = make_group(
            members=[
                make_evidence(
                    evidence_id="ev_web",
                    artifact=make_artifact(
                        artifact_id="art_web",
                        source_type=SourceType.GENERAL_WEB,
                        scope=IdentityScope.RANGE,
                    ),
                    modality=EvidenceModality.MARKETING,
                ),
                make_evidence(evidence_id="ev_ds"),
            ]
        )
        assert group.best_member.evidence_id == "ev_ds"

    def test_verified_members_excludes_unverified(self):
        group = make_group(
            members=[
                make_evidence(evidence_id="ev_ok"),
                make_evidence(
                    evidence_id="ev_bad",
                    verification=EvidenceVerification.UNVERIFIED,
                    page=None,
                ),
            ]
        )
        assert [e.evidence_id for e in group.verified_members] == ["ev_ok"]

    def test_locator_carries_table_structure(self):
        ev = make_evidence()
        assert ev.locator.is_tabular
        assert "row “Rated operational current Ie”" in ev.locator.human()

    def test_discovery_url_and_final_url_are_distinct_fields(self):
        """A search citation URL is not necessarily the artifact we actually read."""
        artifact = make_artifact().model_copy(
            update={"discovery_url": "https://vertexaisearch.example/redirect/abc"}
        )
        assert artifact.discovery_url != artifact.final_url


# --------------------------------------------------------------------------------------
# Run provenance
# --------------------------------------------------------------------------------------


class TestRunProvenance:
    def test_replay_must_record_its_capture_date(self):
        with pytest.raises(ValidationError, match="must record captured_at"):
            RunProvenance(mode=RunMode.REPLAY)

    def test_mixed_must_record_its_capture_date(self):
        with pytest.raises(ValidationError, match="must record captured_at"):
            RunProvenance(mode=RunMode.MIXED)

    def test_live_needs_no_capture_date(self):
        assert RunProvenance(mode=RunMode.LIVE).banner() == "LIVE RUN"

    def test_replay_banner_states_the_capture_date(self):
        prov = RunProvenance(mode=RunMode.REPLAY, captured_at=datetime(2026, 8, 12, tzinfo=UTC))
        assert prov.banner() == "RECORDED REPLAY — captured 2026-08-12"

    def test_mixed_is_barred_from_published_evaluation(self):
        prov = RunProvenance(mode=RunMode.MIXED, captured_at=datetime(2026, 8, 12, tzinfo=UTC))
        assert not prov.is_publishable_evaluation
        assert RunProvenance(mode=RunMode.LIVE).is_publishable_evaluation


# --------------------------------------------------------------------------------------
# Coverage — ETIM feature coverage is not business completeness
# --------------------------------------------------------------------------------------


class TestCoverage:
    def _record_with(self, attrs) -> GoldenRecord:
        return _record(EXACT_IDENTITY, tuple(attrs))

    def test_inapplicable_features_leave_the_denominator(self):
        accepted = make_attribute()
        not_applicable = make_attribute(
            etim_feature_id="EF011960",
            name="Rated operation power NEMA",
            applicability=Applicability.NOT_APPLICABLE,
            status=AttributeStatus.WITHHELD,
            value=None,
            support_grade=None,
            withheld_reason=WithheldReason.NOT_APPLICABLE,
            buyer_critical=False,
            evidence_groups=(),
        )
        coverage = self._record_with([accepted, not_applicable]).build_coverage()
        assert coverage.etim_features_total == 2
        assert coverage.applicable_total == 1
        assert coverage.not_applicable_total == 1
        assert coverage.etim_feature_coverage == 1.0

    def test_buyer_critical_coverage_is_separate_from_etim_coverage(self):
        critical_missing = make_attribute(
            etim_feature_id="EF001364",
            name="Rated operation power at AC-3, 400 V",
            expected_unit="kW",
            buyer_critical=True,
            status=AttributeStatus.WITHHELD,
            value=None,
            support_grade=None,
            withheld_reason=WithheldReason.NOT_FOUND,
            evidence_groups=(),
        )
        non_critical_filled = make_attribute(
            etim_feature_id="EF000008",
            name="Width",
            expected_unit="mm",
            buyer_critical=False,
            value=NumericValue(raw="45 mm", number=45.0, unit="mm"),
        )
        coverage = self._record_with([critical_missing, non_critical_filled]).build_coverage()
        assert coverage.etim_feature_coverage == 0.5
        assert coverage.buyer_critical_coverage == 0.0

    def test_coverage_counts_must_be_consistent(self):
        from skutruth.contracts import CoverageReport

        with pytest.raises(ValidationError, match="does not sum to etim_features_total"):
            CoverageReport(
                etim_features_total=10,
                applicable_total=5,
                not_applicable_total=2,
                applicability_unknown_total=1,
                accepted_total=5,
                buyer_critical_total=3,
                buyer_critical_applicable=3,
                buyer_critical_accepted=3,
            )

    def test_accepted_cannot_exceed_applicable(self):
        from skutruth.contracts import CoverageReport

        with pytest.raises(ValidationError, match="accepted_total exceeds applicable_total"):
            CoverageReport(
                etim_features_total=3,
                applicable_total=1,
                not_applicable_total=1,
                applicability_unknown_total=1,
                accepted_total=2,
                buyer_critical_total=0,
                buyer_critical_applicable=0,
                buyer_critical_accepted=0,
            )
