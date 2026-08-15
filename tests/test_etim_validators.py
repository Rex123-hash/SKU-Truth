"""Deterministic validation against EC000066 — Power contactor, AC switching.

The class is pinned as the primary target because it really does carry all four ETIM
feature types, so no type coverage here needs a fabricated feature.
"""

from __future__ import annotations

import pytest
from skutruth.contracts import (
    AlphanumericValue,
    Condition,
    ConditionCompleteness,
    ConditionKind,
    ConditionSet,
    DerivationKind,
    LogicalValue,
    NumericValue,
    RangeValue,
)
from skutruth.etim import (
    RawFeatureValue,
    ValidationCode,
    build_value,
    load_demo_class,
    load_etim,
    resolve_conditions,
    validate_conditions,
    validate_feature_value,
)

# Real EC000066 features, one per ETIM type.
CURRENT = "EF001392"  # N, unit A   — Rated operation current Ie at AC-3, 400 V
POWER = "EF001364"  # N, unit kW  — Rated operation power at AC-3, 400 V
COIL_V = "EF003978"  # R, unit V   — Rated control supply voltage AC 50 Hz
NO_MAIN = "EF001374"  # N, no unit  — Number of NO contacts as main contact
ACT_TYPE = "EF008242"  # A          — Voltage type for actuating {AC, DC, AC/DC}
CONNECT = "EF006819"  # A          — Type of electrical connection of main circuit
DIST_BOARD = "EF001126"  # L       — Suitable for distribution board
WIDTH = "EF000008"  # N, unit mm


@pytest.fixture(scope="module")
def contactor():
    return load_etim().require("EC000066")


@pytest.fixture(scope="module")
def config():
    return load_demo_class("EC000066")


def raw(**kw) -> RawFeatureValue:
    kw.setdefault("raw_text", "Rated operational current Ie AC-3 400 V 18 A")
    kw.setdefault("page", 2)
    return RawFeatureValue(**kw)


class TestDemoClassConfiguration:
    def test_config_matches_the_loaded_etim_class(self, config, contactor):
        """Guards against the reviewed config drifting from the ETIM release."""
        assert config.check_against(contactor) == []

    def test_buyer_critical_is_a_subset_not_the_whole_class(self, config, contactor):
        assert 0 < len(config.buyer_critical) < len(contactor)

    def test_every_rule_records_a_rationale(self, config):
        assert all(r.rationale for r in config.qualifier_rules.values())

    def test_expected_values_only_pin_required_kinds(self, config):
        for rule in config.qualifier_rules.values():
            for kind, _ in rule.expected:
                assert kind in rule.required_kinds


class TestFeatureLookup:
    def test_unknown_feature_id_is_rejected(self, contactor):
        value, result = build_value(contactor, "EF999999", raw(number=1.0, unit="A"))
        assert value is None
        assert result.has(ValidationCode.UNKNOWN_FEATURE)

    def test_a_feature_from_another_class_is_rejected(self, contactor):
        """EF000021 exists in ETIM but is not on this class."""
        other = load_etim().require("EC000001")
        foreign = next(f for f in other.features if f.feature_id not in contactor.feature_ids)
        _, result = build_value(contactor, foreign.feature_id, raw(number=1.0))
        assert result.has(ValidationCode.UNKNOWN_FEATURE)


class TestNumericFeatures:
    def test_a_value_already_in_the_etim_unit_passes_through(self, contactor):
        value, result = build_value(contactor, CURRENT, raw(number=18.0, unit="A"))
        assert result.ok
        assert isinstance(value, NumericValue)
        assert (value.number, value.unit) == (18.0, "A")
        assert value.derivation.is_verbatim

    def test_milliamps_are_converted_with_lineage(self, contactor):
        value, result = build_value(
            contactor, CURRENT, raw(number=18000.0, unit="mA", raw_text="18000 mA")
        )
        assert result.ok
        assert (value.number, value.unit) == (18.0, "A")
        assert value.raw == "18000 mA"
        assert value.derivation.kind is DerivationKind.UNIT_CONVERSION

    def test_an_incompatible_unit_is_refused(self, contactor):
        value, result = build_value(contactor, CURRENT, raw(number=400.0, unit="V"))
        assert value is None
        assert result.has(ValidationCode.INCOMPATIBLE_UNIT)

    def test_an_unknown_unit_is_refused_not_guessed(self, contactor):
        value, result = build_value(contactor, CURRENT, raw(number=18.0, unit="amps"))
        assert value is None
        assert result.has(ValidationCode.UNKNOWN_UNIT)

    def test_a_missing_unit_is_refused(self, contactor):
        value, result = build_value(contactor, CURRENT, raw(number=18.0))
        assert value is None
        assert result.has(ValidationCode.MISSING_UNIT)

    def test_a_unitless_feature_rejects_a_unit(self, contactor):
        value, result = build_value(contactor, NO_MAIN, raw(number=3.0, unit="A"))
        assert value is None
        assert result.has(ValidationCode.UNEXPECTED_UNIT)

    def test_a_unitless_feature_accepts_a_bare_number(self, contactor):
        value, result = build_value(contactor, NO_MAIN, raw(number=3.0, raw_text="3 NO"))
        assert result.ok
        assert value.number == 3.0

    def test_a_non_finite_number_is_refused(self, contactor):
        value, result = build_value(contactor, CURRENT, raw(number=float("inf"), unit="A"))
        assert value is None
        assert result.has(ValidationCode.NON_FINITE_NUMBER)

    def test_a_missing_number_is_malformed(self, contactor):
        value, result = build_value(contactor, CURRENT, raw(unit="A"))
        assert value is None
        assert result.has(ValidationCode.MALFORMED_PAYLOAD)

    def test_kilowatt_feature_keeps_its_own_unit(self, contactor):
        value, result = build_value(contactor, POWER, raw(number=7500.0, unit="W"))
        assert result.ok
        assert (value.number, value.unit) == (7.5, "kW")

    def test_millimetre_feature(self, contactor):
        value, result = build_value(contactor, WIDTH, raw(number=4.5, unit="cm"))
        assert result.ok
        assert (value.number, value.unit) == (45.0, "mm")


class TestRangeFeatures:
    def test_a_range_is_built_and_converted(self, contactor):
        value, result = build_value(
            contactor, COIL_V, raw(minimum=24000.0, maximum=230000.0, unit="mV")
        )
        assert result.ok
        assert isinstance(value, RangeValue)
        assert (value.minimum, value.maximum, value.unit) == (24.0, 230.0, "V")

    def test_an_inverted_range_is_refused(self, contactor):
        """Reachable here because the raw payload has not been typed yet."""
        value, result = build_value(
            contactor, COIL_V, raw(minimum=230.0, maximum=24.0, unit="V")
        )
        assert value is None
        assert result.has(ValidationCode.RANGE_INVERTED)

    def test_a_degenerate_range_is_allowed(self, contactor):
        value, result = build_value(contactor, COIL_V, raw(minimum=24.0, maximum=24.0, unit="V"))
        assert result.ok
        assert value.minimum == value.maximum == 24.0

    def test_a_half_specified_range_is_malformed(self, contactor):
        value, result = build_value(contactor, COIL_V, raw(minimum=24.0, unit="V"))
        assert value is None
        assert result.has(ValidationCode.MALFORMED_PAYLOAD)


class TestPicklistFeatures:
    def test_an_allowed_value_is_accepted_with_its_etim_id(self, contactor):
        value, result = build_value(contactor, ACT_TYPE, raw(text="AC", raw_text="AC coil"))
        assert result.ok
        assert isinstance(value, AlphanumericValue)
        assert value.text == "AC"
        assert value.value_id.startswith("EV")

    def test_a_value_outside_the_picklist_is_refused(self, contactor):
        value, result = build_value(contactor, ACT_TYPE, raw(text="240V"))
        assert value is None
        assert result.has(ValidationCode.NOT_IN_PICKLIST)

    def test_case_and_spacing_are_mapped_onto_the_etim_spelling(self, contactor):
        value, result = build_value(
            contactor, CONNECT, raw(text="  screw connection ", raw_text="screw terminals")
        )
        assert result.ok
        assert value.text == "Screw connection"
        assert value.derivation.kind is DerivationKind.ENUM_MAP
        assert "Screw connection" in value.derivation.detail

    def test_a_picklist_feature_rejects_a_unit(self, contactor):
        value, result = build_value(contactor, ACT_TYPE, raw(text="AC", unit="V"))
        assert value is None
        assert result.has(ValidationCode.UNEXPECTED_UNIT)

    def test_missing_text_is_malformed(self, contactor):
        value, result = build_value(contactor, ACT_TYPE, raw(text="   "))
        assert value is None
        assert result.has(ValidationCode.MALFORMED_PAYLOAD)


class TestLogicalFeatures:
    def test_a_boolean_is_accepted(self, contactor):
        value, result = build_value(
            contactor, DIST_BOARD, raw(boolean=True, raw_text="suitable for distribution boards")
        )
        assert result.ok
        assert isinstance(value, LogicalValue)
        assert value.boolean is True

    def test_a_missing_boolean_is_malformed(self, contactor):
        value, result = build_value(contactor, DIST_BOARD, raw(text="yes"))
        assert value is None
        assert result.has(ValidationCode.MALFORMED_PAYLOAD)


class TestTypedValueValidation:
    def test_a_canonical_value_validates(self, contactor):
        v = NumericValue(raw="18 A", number=18.0, unit="A")
        assert validate_feature_value(contactor, CURRENT, v).ok

    def test_the_wrong_value_kind_is_rejected(self, contactor):
        v = AlphanumericValue(raw="18 A", text="18 A")
        result = validate_feature_value(contactor, CURRENT, v)
        assert result.has(ValidationCode.WRONG_VALUE_KIND)

    def test_a_non_canonical_unit_is_rejected(self, contactor):
        """Values must be normalized *before* acceptance, not at accept time."""
        v = NumericValue(raw="18000 mA", number=18000.0, unit="mA")
        result = validate_feature_value(contactor, CURRENT, v)
        assert result.has(ValidationCode.UNEXPECTED_UNIT)

    def test_a_picklist_value_off_the_list_is_rejected(self, contactor):
        v = AlphanumericValue(raw="240V", text="240V")
        assert validate_feature_value(contactor, ACT_TYPE, v).has(ValidationCode.NOT_IN_PICKLIST)

    def test_a_mismatched_value_id_is_rejected(self, contactor):
        v = AlphanumericValue(raw="AC", text="AC", value_id="EV000001")
        assert validate_feature_value(contactor, ACT_TYPE, v).has(
            ValidationCode.VALUE_ID_MISMATCH
        )

    def test_validation_of_an_unknown_feature_reports_it(self, contactor):
        v = NumericValue(raw="1", number=1.0, unit="A")
        assert validate_feature_value(contactor, "EF999999", v).has(
            ValidationCode.UNKNOWN_FEATURE
        )


AC3 = Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3")
AC1 = Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-1")
V400 = Condition(kind=ConditionKind.VOLTAGE, value="400 V")


class TestConditionCompleteness:
    """A model may propose conditions. It may not rule on its own completeness."""

    def test_all_required_qualifiers_present_is_complete(self, config):
        resolved = resolve_conditions(config, CURRENT, ConditionSet(conditions=(AC3, V400)))
        assert resolved.completeness is ConditionCompleteness.COMPLETE
        assert resolved.missing_kinds == ()

    def test_a_missing_qualifier_is_partial_and_named(self, config):
        resolved = resolve_conditions(config, CURRENT, ConditionSet(conditions=(AC3,)))
        assert resolved.completeness is ConditionCompleteness.PARTIAL
        assert resolved.missing_kinds == (ConditionKind.VOLTAGE,)

    def test_missing_kinds_are_deterministic_in_rule_order(self, config):
        resolved = resolve_conditions(config, CURRENT, ConditionSet())
        assert resolved.missing_kinds == (
            ConditionKind.UTILIZATION_CATEGORY,
            ConditionKind.VOLTAGE,
        )

    def test_a_feature_with_no_reviewed_rule_is_unknown(self, config):
        """UNKNOWN is a statement about our knowledge, not about the data."""
        stripped = config.__class__(
            etim_class_id=config.etim_class_id,
            etim_class_name=config.etim_class_name,
            etim_release=config.etim_release,
            etim_language=config.etim_language,
            reviewed_on=config.reviewed_on,
            notes=config.notes,
            buyer_critical=config.buyer_critical,
            qualifier_rules={},
        )
        resolved = resolve_conditions(stripped, CURRENT, ConditionSet(conditions=(AC3, V400)))
        assert resolved.completeness is ConditionCompleteness.UNKNOWN

    def test_no_config_at_all_is_unknown(self):
        resolved = resolve_conditions(None, CURRENT, ConditionSet(conditions=(AC3, V400)))
        assert resolved.completeness is ConditionCompleteness.UNKNOWN

    def test_a_reviewed_no_qualifier_feature_is_complete_not_unknown(self, config):
        """'No qualifier needed' is a finding, and must not read as a gap."""
        resolved = resolve_conditions(config, WIDTH, ConditionSet())
        assert resolved.completeness is ConditionCompleteness.COMPLETE
        assert resolved.missing_kinds == ()

    def test_a_model_supplied_completeness_is_overwritten(self, config):
        """The whole point: a model cannot assert that its own conditions are complete."""
        lying = ConditionSet(
            conditions=(AC3,), completeness=ConditionCompleteness.COMPLETE
        )
        resolved = resolve_conditions(config, CURRENT, lying)
        assert resolved.completeness is ConditionCompleteness.PARTIAL

    def test_resolution_preserves_the_conditions_themselves(self, config):
        resolved = resolve_conditions(config, CURRENT, ConditionSet(conditions=(AC3, V400)))
        assert resolved.get(ConditionKind.UTILIZATION_CATEGORY).value == "AC-3"


class TestConditionValidation:
    def test_a_complete_matching_operating_point_validates(self, config):
        assert validate_conditions(config, CURRENT, ConditionSet(conditions=(AC3, V400))).ok

    def test_a_missing_required_qualifier_is_an_error(self, config):
        result = validate_conditions(config, CURRENT, ConditionSet(conditions=(AC3,)))
        assert result.has(ValidationCode.CONDITIONS_INCOMPLETE)

    def test_the_wrong_utilization_category_is_caught(self, config):
        """AC-1 data bound to the AC-3 feature is a schema-mapping error, not a conflict."""
        result = validate_conditions(config, CURRENT, ConditionSet(conditions=(AC1, V400)))
        assert result.has(ValidationCode.CONDITION_VALUE_MISMATCH)

    def test_the_ac1_feature_accepts_ac1(self, config):
        assert validate_conditions(config, "EF001393", ConditionSet(conditions=(AC1, V400))).ok

    def test_a_feature_without_a_rule_warns_rather_than_failing(self, config):
        result = validate_conditions(None, CURRENT, ConditionSet())
        assert result.ok
        assert result.has(ValidationCode.NO_QUALIFIER_RULE)
