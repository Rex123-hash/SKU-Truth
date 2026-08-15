"""Deterministic unit conversion, bounded to units we have actually reviewed.

This is the implementation layer the frozen contract deliberately deferred arithmetic
to. `EvidenceGroup.supports_value` guarantees a derived value is *traceable* to a real
observation; this module is what makes the derivation *correct*.

Three rules govern everything here:

* **Never guess.** An unrecognised unit is an error, not an assumption. A source that
  writes a unit we have not reviewed produces a validation failure and an abstention,
  which is the safe direction.
* **Never cross dimensions.** Amperes do not become volts. Attempting it is an error,
  never a silent pass-through.
* **Never fake an affine conversion.** Temperature scales differ by an offset as well
  as a factor, so a factor table cannot express them. Rather than encode a
  half-correct rule, conversion between two different temperature units is refused
  outright.

Conversion arithmetic runs in `Decimal` so that 18000 mA is exactly 18 A rather than
18.000000000000004. Product data is quoted to a few significant figures and a value
that drifts in the last bits would be a poor thing to put behind a citation.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from skutruth.contracts import Derivation, DerivationKind, NumericValue, RangeValue

#: Versioned identifier recorded on every derivation this module produces. Transform
#: ids are ours, never a model's: the contract accepts a derivation because the code
#: that produced it is auditable, not because a string was supplied.
UNIT_CONVERSION_TRANSFORM = "unit_conversion@v1"


class UnitError(ValueError):
    """Base class for every refusal in this module."""


class UnknownUnit(UnitError):
    """A unit symbol outside the reviewed registry."""


class IncompatibleUnits(UnitError):
    """Two units measuring different physical dimensions."""


class UnsupportedConversion(UnitError):
    """A conversion within a dimension that a factor table cannot express."""


@dataclass(frozen=True, slots=True)
class UnitDef:
    """One unit symbol, and how it relates to its dimension's base unit."""

    symbol: str
    dimension: str
    factor: Decimal  # multiply by this to reach the dimension's base unit
    affine: bool = False  # scale needs an offset too; factor alone is insufficient


def _u(symbol: str, dimension: str, factor: str, *, affine: bool = False) -> UnitDef:
    return UnitDef(symbol, dimension, Decimal(factor), affine=affine)


#: Reviewed unit registry. Scoped to the electrical demo classes plus the dimensions
#: their ETIM features actually use; new units are added here, and nothing else in the
#: system needs to change to support them.
#:
#: Base units are chosen to match ETIM's own preference (mm for length, g for mass)
#: so the common case is an identity conversion.
_REGISTRY: tuple[UnitDef, ...] = (
    # current
    _u("A", "current", "1"),
    _u("mA", "current", "0.001"),
    _u("kA", "current", "1000"),
    # voltage
    _u("V", "voltage", "1"),
    _u("mV", "voltage", "0.001"),
    _u("kV", "voltage", "1000"),
    # active power
    _u("W", "power", "1"),
    _u("mW", "power", "0.001"),
    _u("kW", "power", "1000"),
    _u("MW", "power", "1000000"),
    # apparent / reactive power are separate dimensions on purpose: VA, var and W are
    # numerically interchangeable only at unity power factor, which we cannot assume.
    _u("VA", "apparent_power", "1"),
    _u("kVA", "apparent_power", "1000"),
    _u("var", "reactive_power", "1"),
    _u("kvar", "reactive_power", "1000"),
    # length
    _u("mm", "length", "1"),
    _u("cm", "length", "10"),
    _u("m", "length", "1000"),
    _u("in", "length", "25.4"),
    # mass
    _u("g", "mass", "1"),
    _u("mg", "mass", "0.001"),
    _u("kg", "mass", "1000"),
    # frequency
    _u("Hz", "frequency", "1"),
    _u("kHz", "frequency", "1000"),
    _u("MHz", "frequency", "1000000"),
    # time
    _u("s", "time", "1"),
    _u("ms", "time", "0.001"),
    _u("min", "time", "60"),
    _u("h", "time", "3600"),
    # resistance
    _u("Ω", "resistance", "1"),
    _u("kΩ", "resistance", "1000"),
    _u("MΩ", "resistance", "1000000"),
    # temperature — affine, so cross-unit conversion is refused rather than faked
    _u("°C", "temperature", "1", affine=True),
    _u("K", "temperature", "1", affine=True),
)

_BY_SYMBOL: dict[str, UnitDef] = {u.symbol: u for u in _REGISTRY}


def lookup(symbol: str) -> UnitDef:
    """Resolve a unit symbol, or raise `UnknownUnit`.

    Matching is exact apart from surrounding whitespace. Case is significant, because
    unit symbols are case-bearing: `mA` and `MA` are not the same thing, and folding
    them would be exactly the kind of guess this module refuses to make.
    """
    key = symbol.strip()
    unit = _BY_SYMBOL.get(key)
    if unit is None:
        raise UnknownUnit(
            f"unit {symbol!r} is not in the reviewed registry; add it to units.py "
            "rather than inferring a conversion"
        )
    return unit


def is_known(symbol: str | None) -> bool:
    return symbol is not None and symbol.strip() in _BY_SYMBOL


def dimension_of(symbol: str) -> str:
    return lookup(symbol).dimension


def compatible_units(symbol: str) -> tuple[str, ...]:
    """Every reviewed unit sharing this one's dimension, in registry order.

    Used by schema generation to tell an extraction model which units it may report
    for a feature: the ETIM-mandated unit plus anything we can convert from.
    """
    dim = lookup(symbol).dimension
    return tuple(u.symbol for u in _REGISTRY if u.dimension == dim)


def convert(number: float, from_unit: str, to_unit: str) -> float:
    """Convert `number` between two reviewed units of the same dimension.

    Raises `UnknownUnit`, `IncompatibleUnits`, or `UnsupportedConversion`. Never
    returns an unconverted number as a fallback — a failure here must reach the
    caller, because the alternative is a wrong value behind a citation.
    """
    src, dst = lookup(from_unit), lookup(to_unit)
    if src.dimension != dst.dimension:
        raise IncompatibleUnits(
            f"cannot convert {from_unit!r} ({src.dimension}) to {to_unit!r} "
            f"({dst.dimension}): different physical dimensions"
        )
    if src.symbol == dst.symbol:
        return number
    if src.affine or dst.affine:
        raise UnsupportedConversion(
            f"conversion from {from_unit!r} to {to_unit!r} needs an offset as well as a "
            "factor; affine scales are not converted here"
        )
    result = Decimal(str(number)) * src.factor / dst.factor
    return float(result)


def conversion_detail(number: float, from_unit: str, to_unit: str, result: float) -> str:
    """The human-readable trace recorded on the `Derivation`."""
    return f"{number:g} {from_unit} -> {result:g} {to_unit}"


def normalize_numeric(value: NumericValue, expected_unit: str) -> NumericValue:
    """Return `value` expressed in `expected_unit`, carrying derivation lineage.

    The returned value keeps the source's own `raw` text. That is not cosmetic: it is
    the link the contract uses to tie a derived value back to the span that observed
    it, so rewriting it here would sever the lineage.
    """
    if value.unit is None:
        raise UnknownUnit(
            "cannot normalize a numeric value that carries no unit; the source unit "
            "must be read from the document, never assumed"
        )
    if value.unit == expected_unit:
        return value
    converted = convert(value.number, value.unit, expected_unit)
    return NumericValue(
        raw=value.raw,
        number=converted,
        unit=expected_unit,
        derivation=Derivation(
            kind=DerivationKind.UNIT_CONVERSION,
            transform_id=UNIT_CONVERSION_TRANSFORM,
            detail=conversion_detail(value.number, value.unit, expected_unit, converted),
        ),
    )


def normalize_range(value: RangeValue, expected_unit: str) -> RangeValue:
    """Range equivalent of `normalize_numeric`; both bounds convert together."""
    if value.unit is None:
        raise UnknownUnit(
            "cannot normalize a range that carries no unit; the source unit must be "
            "read from the document, never assumed"
        )
    if value.unit == expected_unit:
        return value
    lo = convert(value.minimum, value.unit, expected_unit)
    hi = convert(value.maximum, value.unit, expected_unit)
    return RangeValue(
        raw=value.raw,
        minimum=lo,
        maximum=hi,
        unit=expected_unit,
        derivation=Derivation(
            kind=DerivationKind.UNIT_CONVERSION,
            transform_id=UNIT_CONVERSION_TRANSFORM,
            detail=(
                f"{value.minimum:g}–{value.maximum:g} {value.unit} -> "
                f"{lo:g}–{hi:g} {expected_unit}"
            ),
        ),
    )
