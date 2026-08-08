"""The ETIM loader is deterministic infrastructure, so these assert exact counts.

Row counts are pinned to the vendored release (ETIM 10.0, all sectors, CSV, metric,
SHA-256 9b2aa17f…). If the archive is ever replaced, these tests should fail loudly
rather than let a silent data swap through.
"""

from __future__ import annotations

import pytest
from skutruth.contracts import EtimFeatureType
from skutruth.etim import (
    DEFAULT_ARCHIVE,
    EXPECTED_ARCHIVE_SHA256,
    archive_sha256,
    load_etim,
)


@pytest.fixture(scope="module")
def etim():
    return load_etim()


@pytest.fixture(scope="module")
def contactor(etim):
    """EC000066 is the hero-demo class; its schema is pinned in detail below."""
    return etim.require("EC000066")


class TestArchiveParses:
    def test_archive_hash_is_pinned(self):
        """A silent data swap must fail loudly in a project about data quality."""
        assert archive_sha256(DEFAULT_ARCHIVE) == EXPECTED_ARCHIVE_SHA256

    def test_class_count_matches_release(self, etim):
        """5,640 parsed records, headers excluded — matches ETIM's own release note."""
        assert len(etim) == 5640

    def test_units_are_loaded(self, etim):
        assert len(etim.units) == 188
        assert "A" in etim.units.values()
        assert "kW" in etim.units.values()

    def test_loading_is_cached(self, etim):
        assert load_etim() is etim

    def test_release_and_language_are_recorded(self, etim):
        """Required for ODC-BY attribution and stamped onto every exported record."""
        assert etim.release == "10.0"
        assert etim.language == "EN"
        assert etim.version_label == "ETIM 10.0 (EN)"


class TestParsedStatistics:
    """Every ETIM count quoted anywhere must be reproducible by scripts/etim_stats.py."""

    def test_counts_exclude_csv_headers(self, etim):
        assert etim.stats is not None
        assert etim.stats.as_dict() == {
            "classes": 5640,
            "groups": 159,
            "features": 17377,
            "units": 188,
            "values": 16163,
            "class_feature_rows": 76625,
            "class_feature_value_rows": 201284,
            "synonym_rows": 37058,
        }

    def test_stats_agree_with_the_parsed_model(self, etim):
        assert etim.stats.classes == len(etim.classes)
        assert etim.stats.units == len(etim.units)


class TestReferentialIntegrity:
    def test_no_dangling_references_in_the_shipped_release(self, etim):
        assert etim.integrity_issues == ()

    def test_every_class_feature_unit_resolves(self, etim):
        for cls in etim.classes.values():
            for f in cls.features:
                if f.unit is not None:
                    assert f.unit in etim.units.values()

    def test_every_class_belongs_to_a_known_group(self, etim):
        for cls in etim.classes.values():
            assert cls.group_name, f"{cls.class_id} has an unresolved group {cls.group_id}"

    def test_every_picklist_value_has_text(self, etim):
        for cls in etim.classes.values():
            for f in cls.features:
                for v in f.allowed_values:
                    assert v.text.strip()


class TestPowerContactorClass:
    """EC000066 is the hero-demo class; its schema is pinned in detail."""

    def test_identity(self, contactor):
        assert contactor.name == "Power contactor, AC switching"
        assert contactor.group_id.startswith("EG")
        assert contactor.group_name

    def test_expected_feature_count(self, contactor):
        assert len(contactor) == 21

    def test_rated_current_is_numeric_in_amperes(self, contactor):
        f = contactor.feature("EF001392")
        assert f is not None
        assert f.name == "Rated operation current Ie at AC-3, 400 V"
        assert f.feature_type is EtimFeatureType.NUMERIC
        assert f.unit == "A"
        assert f.allowed_values == ()

    def test_rated_power_is_numeric_in_kilowatts(self, contactor):
        f = contactor.feature("EF001364")
        assert f.feature_type is EtimFeatureType.NUMERIC
        assert f.unit == "kW"

    def test_control_supply_voltage_is_a_range_in_volts(self, contactor):
        f = contactor.feature("EF003978")
        assert f.feature_type is EtimFeatureType.RANGE
        assert f.unit == "V"

    def test_actuating_voltage_type_is_a_closed_picklist(self, contactor):
        """The constraint that makes hallucinating this attribute impossible."""
        f = contactor.feature("EF008242")
        assert f.is_picklist
        assert set(f.allowed_texts()) == {"AC", "DC", "AC/DC"}

    def test_connection_type_picklist(self, contactor):
        f = contactor.feature("EF006819")
        assert f.allowed_texts() == (
            "Flat plug-in connection",
            "Bolt connection",
            "PCB connection",
            "Screw connection",
            "Spring clamp connection",
            "Rail connection",
            "Cable clamp",
            "Clamp bracket",
            "Frame clamp",
            "Other",
        )

    def test_picklist_preserves_etim_sort_order(self, contactor):
        """Order is ETIM's, not alphabetical: it is what a reviewer sees in the drawer."""
        f = contactor.feature("EF006819")
        assert [v.sort_nr for v in f.allowed_values] == sorted(v.sort_nr for v in f.allowed_values)
        assert f.allowed_texts()[0] == "Flat plug-in connection"

    def test_picklist_lookup_is_case_and_space_insensitive(self, contactor):
        f = contactor.feature("EF008242")
        assert f.find_allowed("ac") is not None
        assert f.find_allowed("  AC/DC ") is not None
        assert f.find_allowed("240V") is None

    def test_dimensions_are_millimetres(self, contactor):
        for fid in ("EF000008", "EF000040", "EF000049"):
            assert contactor.feature(fid).unit == "mm"

    def test_features_are_sorted_by_etim_sort_order(self, contactor):
        sorts = [f.sort_nr for f in contactor.features]
        assert sorts == sorted(sorts)


class TestFeatureTypeCoverage:
    def test_all_four_etim_types_are_represented(self, etim):
        seen = {f.feature_type for cls in etim.classes.values() for f in cls.features}
        assert seen == set(EtimFeatureType)

    def test_picklist_features_carry_allowed_values(self, etim):
        """An `A` feature with no allowed values could not constrain anything."""
        cls = etim.require("EC000066")
        for f in cls.features:
            if f.is_picklist:
                assert f.allowed_values, f"{f.feature_id} is a picklist with no values"


class TestClassLookup:
    def test_exact_name_lookup(self, etim):
        hits = etim.lookup_exact("Power contactor, AC switching")
        assert "EC000066" in {c.class_id for c in hits}

    def test_synonym_lookup_finds_the_class(self, etim):
        """Synonyms let us generate candidates with no model call."""
        cls = etim.require("EC000001")
        assert cls.synonyms
        hits = etim.lookup_exact(cls.synonyms[0])
        assert "EC000001" in {c.class_id for c in hits}

    def test_search_ranks_power_contactor_for_contactor(self, etim):
        results = etim.search("contactor")
        assert results
        assert "EC000066" in {c.class_id for c in results[:8]}

    def test_search_respects_limit(self, etim):
        assert len(etim.search("cable", limit=5)) <= 5

    def test_search_on_noise_returns_nothing(self, etim):
        assert etim.search("zzzzqqqq") == []

    def test_unknown_class_raises(self, etim):
        assert etim.get("EC999999") is None
        with pytest.raises(KeyError, match="EC999999"):
            etim.require("EC999999")
