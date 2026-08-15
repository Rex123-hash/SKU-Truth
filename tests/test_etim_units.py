"""The unit boundary. Every refusal here is deliberate."""

from __future__ import annotations

import pytest
from skutruth.contracts import DerivationKind, NumericValue, RangeValue
from skutruth.etim import units


class TestConversion:
    def test_the_hero_case(self):
        """18000 mA -> 18 A, exactly, with no floating-point drift."""
        assert units.convert(18000.0, "mA", "A") == 18.0

    @pytest.mark.parametrize(
        "number,src,dst,expected",
        [
            (18000.0, "mA", "A", 18.0),
            (18.0, "A", "mA", 18000.0),
            (7.5, "kW", "W", 7500.0),
            (400.0, "V", "kV", 0.4),
            (2.5, "cm", "mm", 25.0),
            (1.0, "in", "mm", 25.4),
            (0.5, "kg", "g", 500.0),
            (50.0, "Hz", "kHz", 0.05),
        ],
    )
    def test_known_conversions(self, number, src, dst, expected):
        assert units.convert(number, src, dst) == pytest.approx(expected, rel=1e-12)

    def test_identity_conversion_is_exact(self):
        assert units.convert(18.0, "A", "A") == 18.0

    def test_decimal_arithmetic_avoids_float_drift(self):
        """The naive float route gives 18.000000000000004 for this one."""
        assert units.convert(18000.0, "mA", "A") == 18.0
        assert repr(units.convert(18000.0, "mA", "A")) == "18.0"


class TestRefusals:
    def test_incompatible_dimensions_are_rejected(self):
        with pytest.raises(units.IncompatibleUnits, match="different physical dimensions"):
            units.convert(18.0, "A", "V")

    def test_power_and_apparent_power_are_different_dimensions(self):
        """W and VA coincide only at unity power factor, which we cannot assume."""
        with pytest.raises(units.IncompatibleUnits):
            units.convert(1.0, "kW", "kVA")

    def test_reactive_power_is_its_own_dimension(self):
        with pytest.raises(units.IncompatibleUnits):
            units.convert(1.0, "kvar", "kW")

    def test_unknown_units_are_never_guessed(self):
        with pytest.raises(units.UnknownUnit, match="not in the reviewed registry"):
            units.convert(1.0, "furlongs", "mm")

    def test_unit_symbols_are_case_sensitive(self):
        """mA and MA are not the same thing; folding case would be a guess."""
        with pytest.raises(units.UnknownUnit):
            units.convert(18000.0, "MA", "A")

    def test_affine_scales_are_refused_rather_than_faked(self):
        """Celsius to Kelvin needs an offset; a factor table cannot express it."""
        with pytest.raises(units.UnsupportedConversion, match="needs an offset"):
            units.convert(20.0, "°C", "K")

    def test_identity_on_an_affine_unit_is_still_fine(self):
        assert units.convert(20.0, "°C", "°C") == 20.0


class TestRegistryIntrospection:
    def test_compatible_units_share_a_dimension(self):
        assert set(units.compatible_units("A")) == {"A", "mA", "kA"}

    def test_dimension_lookup(self):
        assert units.dimension_of("kW") == "power"
        assert units.dimension_of("mm") == "length"

    def test_is_known(self):
        assert units.is_known("A")
        assert not units.is_known("furlongs")
        assert not units.is_known(None)


class TestNormalisation:
    def test_normalising_records_derivation_lineage(self):
        source = NumericValue(raw="18000 mA", number=18000.0, unit="mA")
        out = units.normalize_numeric(source, "A")
        assert out.number == 18.0
        assert out.unit == "A"
        assert out.derivation.kind is DerivationKind.UNIT_CONVERSION
        assert out.derivation.transform_id == units.UNIT_CONVERSION_TRANSFORM
        assert out.derivation.detail == "18000 mA -> 18 A"

    def test_normalising_preserves_the_source_raw_text(self):
        """The raw text is the link the contract uses to tie the value to its span."""
        source = NumericValue(raw="18000 mA", number=18000.0, unit="mA")
        assert units.normalize_numeric(source, "A").raw == "18000 mA"

    def test_a_value_already_in_the_target_unit_is_returned_untouched(self):
        source = NumericValue(raw="18 A", number=18.0, unit="A")
        out = units.normalize_numeric(source, "A")
        assert out is source
        assert out.derivation.is_verbatim

    def test_normalising_a_range_converts_both_bounds(self):
        source = RangeValue(raw="24000-230000 mV", minimum=24000.0, maximum=230000.0, unit="mV")
        out = units.normalize_range(source, "V")
        assert (out.minimum, out.maximum) == (24.0, 230.0)
        assert out.derivation.kind is DerivationKind.UNIT_CONVERSION

    def test_a_unitless_value_cannot_be_normalised(self):
        source = NumericValue(raw="18", number=18.0)
        with pytest.raises(units.UnknownUnit, match="never assumed"):
            units.normalize_numeric(source, "A")
