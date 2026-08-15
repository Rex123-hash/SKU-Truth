"""Extraction schema generation for EC000066.

The schema exists to remove choices from the model, so most of these tests assert
what it forbids rather than what it permits.
"""

from __future__ import annotations

import json

import pytest
from skutruth.contracts import ConditionKind, EtimFeatureType
from skutruth.etim import (
    EXTRACTION_SCHEMA_VERSION,
    RawFeatureValue,
    build_extraction_schema,
    load_demo_class,
    load_etim,
)
from skutruth.etim.schema_gen import FORBIDDEN_SCHEMA_KEYS

CURRENT = "EF001392"
ACT_TYPE = "EF008242"
COIL_V = "EF003978"
DIST_BOARD = "EF001126"
NO_MAIN = "EF001374"


@pytest.fixture(scope="module")
def contactor():
    return load_etim().require("EC000066")


@pytest.fixture(scope="module")
def schema(contactor):
    return build_extraction_schema(contactor, load_demo_class("EC000066"))


class TestSchemaShape:
    def test_covers_every_feature_on_the_class(self, schema, contactor):
        assert schema.feature_ids == contactor.feature_ids

    def test_carries_release_and_version_metadata(self, schema):
        assert schema.etim_class_id == "EC000066"
        assert schema.etim_release == "10.0"
        assert schema.etim_language == "EN"
        assert schema.schema_version == EXTRACTION_SCHEMA_VERSION

    def test_class_id_is_a_single_member_enum(self, schema):
        prop = schema.json_schema()["properties"]["etim_class_id"]
        assert prop["enum"] == ["EC000066"]

    def test_feature_properties_use_only_real_feature_ids(self, schema, contactor):
        props = schema.json_schema()["properties"]["features"]["properties"]
        assert set(props) == set(contactor.feature_ids)

    def test_a_subset_schema_can_be_generated_for_targeted_re_extraction(self, contactor):
        subset = build_extraction_schema(contactor, feature_ids=(CURRENT, ACT_TYPE))
        assert subset.feature_ids == (ACT_TYPE, CURRENT) or set(subset.feature_ids) == {
            CURRENT,
            ACT_TYPE,
        }

    def test_a_subset_cannot_smuggle_in_a_foreign_feature(self, contactor):
        subset = build_extraction_schema(contactor, feature_ids=(CURRENT, "EF999999"))
        assert subset.feature_ids == (CURRENT,)


class TestFeatureConstraints:
    def _prop(self, schema, feature_id):
        return schema.json_schema()["properties"]["features"]["properties"][feature_id]

    def test_a_picklist_is_a_closed_enum_of_the_real_values(self, schema):
        prop = self._prop(schema, ACT_TYPE)
        assert set(prop["properties"]["text"]["enum"]) == {"AC", "DC", "AC/DC"}

    def test_a_numeric_feature_accepts_only_dimensionally_compatible_units(self, schema):
        prop = self._prop(schema, CURRENT)
        assert set(prop["properties"]["unit"]["enum"]) == {"A", "mA", "kA"}

    def test_the_unit_enum_permits_the_conversion_path(self, schema):
        """mA must be offerable, or 18000 mA could never be reported and converted."""
        assert "mA" in self._prop(schema, CURRENT)["properties"]["unit"]["enum"]

    def test_a_range_feature_asks_for_both_bounds(self, schema):
        prop = self._prop(schema, COIL_V)
        assert {"minimum", "maximum"} <= set(prop["properties"])
        assert {"minimum", "maximum"} <= set(prop["required"])

    def test_a_logical_feature_asks_for_a_boolean(self, schema):
        prop = self._prop(schema, DIST_BOARD)
        assert prop["properties"]["boolean"]["type"] == "boolean"

    def test_a_unitless_feature_offers_no_unit_field(self, schema):
        assert "unit" not in self._prop(schema, NO_MAIN)["properties"]

    def test_every_feature_is_nullable_so_the_model_can_decline(self, schema):
        props = schema.json_schema()["properties"]["features"]["properties"]
        assert all(p["nullable"] for p in props.values())

    def test_every_feature_demands_verbatim_text_and_a_page(self, schema):
        props = schema.json_schema()["properties"]["features"]["properties"]
        for prop in props.values():
            assert {"raw_text", "page"} <= set(prop["required"])

    def test_conditions_are_a_closed_kind_enum(self, schema):
        cond = self._prop(schema, CURRENT)["properties"]["conditions"]["items"]
        assert set(cond["properties"]["kind"]["enum"]) == {k.value for k in ConditionKind}

    def test_the_description_carries_the_fixed_operating_point(self, schema):
        assert "AC-3" in self._prop(schema, CURRENT)["description"]


class TestSchemaSafety:
    def test_the_model_is_never_asked_to_assert_a_trusted_field(self, schema):
        """No confidence, no completeness, and above all no proves_family_scope."""
        blob = schema.canonical_json()
        for forbidden in FORBIDDEN_SCHEMA_KEYS:
            assert forbidden not in blob, f"{forbidden!r} leaked into the extraction schema"

    def test_the_payload_model_matches_the_generated_properties(self, schema):
        """schema_gen and validators must agree on field names or extraction silently fails."""
        allowed = set(RawFeatureValue.model_fields)
        props = schema.json_schema()["properties"]["features"]["properties"]
        for feature_id, prop in props.items():
            unknown = set(prop["properties"]) - allowed
            assert not unknown, f"{feature_id} exposes fields validators cannot read: {unknown}"

    def test_the_payload_model_has_no_field_the_schema_never_fills(self, schema):
        props = schema.json_schema()["properties"]["features"]["properties"]
        offered = {k for prop in props.values() for k in prop["properties"]}
        assert set(RawFeatureValue.model_fields) == offered


class TestDeterminism:
    def test_identical_input_produces_an_identical_fingerprint(self, contactor):
        cfg = load_demo_class("EC000066")
        a = build_extraction_schema(contactor, cfg)
        b = build_extraction_schema(contactor, cfg)
        assert a.fingerprint() == b.fingerprint()
        assert a.canonical_json() == b.canonical_json()

    def test_the_fingerprint_changes_when_the_feature_set_changes(self, contactor):
        full = build_extraction_schema(contactor, load_demo_class("EC000066"))
        subset = build_extraction_schema(contactor, feature_ids=(CURRENT,))
        assert full.fingerprint() != subset.fingerprint()

    def test_the_fingerprint_changes_with_the_reviewed_configuration(self, contactor):
        """Coverage and qualifier rules affect extraction, so they must affect the key."""
        with_config = build_extraction_schema(contactor, load_demo_class("EC000066"))
        without = build_extraction_schema(contactor, None)
        assert with_config.fingerprint() != without.fingerprint()

    def test_canonical_json_is_stable_and_parseable(self, schema):
        parsed = json.loads(schema.canonical_json())
        assert parsed["metadata"]["etim_class_id"] == "EC000066"
        assert json.loads(schema.canonical_json()) == parsed


class TestFeatureMetadata:
    def test_buyer_critical_is_marked_from_the_reviewed_config(self, schema):
        assert schema.feature(CURRENT).buyer_critical is True
        assert schema.feature("EF000008").buyer_critical is False

    def test_required_qualifiers_are_exposed_to_extraction(self, schema):
        f = schema.feature(CURRENT)
        assert f.required_condition_kinds == (
            ConditionKind.UTILIZATION_CATEGORY,
            ConditionKind.VOLTAGE,
        )
        assert dict(f.expected_conditions)[ConditionKind.VOLTAGE] == "400 V"

    def test_feature_types_and_units_come_from_etim(self, schema):
        f = schema.feature(CURRENT)
        assert f.feature_type is EtimFeatureType.NUMERIC
        assert f.unit == "A"

    def test_without_a_config_no_feature_is_buyer_critical_or_qualified(self, contactor):
        bare = build_extraction_schema(contactor, None)
        assert not any(f.buyer_critical for f in bare.features)
        assert not any(f.required_condition_kinds for f in bare.features)
