"""Reading quantities — with their operators — out of real source text.

This is the machinery the verifier's honesty rests on. Three failures from the first
real Gemini run all reduce to a relation being dropped:

    source `< 60 °C`      proposed `60 °C`     — a bound read as a point
    source `<= 440 V`     proposed `400 V`     — a bound read as a different point
    source `50/60 Hz`     proposed `50 Hz`     — an enumeration read as a single value

So a quantity here is never just a number and a unit. It carries a `Relation`, and
`< 60 °C` is not equal to `60 °C` at any point in this module.

## Enumerations are not ranges

`50/60 Hz` states two discrete alternatives, both of which the document asserts. It is
parsed into two quantities marked `enumerated`, so a condition binding either one can be
supported by set membership. `100-250 V` is a *range* and is deliberately **not** treated
that way: a value inside a range is not a value the document states.

## What is deliberately not parsed

Mixed-inch fractions (`24-1/4 in`) are left alone. They appear in Unilog delivery output
rather than in the manufacturer text this verifier reads, and a `W-N/D` pattern is
ambiguous with a hyphenated range. Adding it speculatively would risk reading `50-1/4` as
a subtraction or a span.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from enum import StrEnum

from skutruth.etim import units


class Relation(StrEnum):
    """How a stated number relates to the property it describes."""

    EQ = "EQ"
    LT = "LT"
    LE = "LE"
    GT = "GT"
    GE = "GE"

    @property
    def is_point(self) -> bool:
        """Whether the source asserts a value rather than a bound on one."""
        return self is Relation.EQ


#: Longest first, so `<=` is never read as `<`.
_OPERATORS: tuple[tuple[str, Relation], ...] = (
    ("<=", Relation.LE),
    (">=", Relation.GE),
    ("≤", Relation.LE),
    ("≥", Relation.GE),
    ("<", Relation.LT),
    (">", Relation.GT),
    ("=", Relation.EQ),
)

_NUMBER = r"\d+(?:[.,]\d+)?"

#: A number, or a slash-separated enumeration of them, optionally preceded by an operator
#: and optionally followed by a unit symbol.
_QUANTITY = re.compile(
    r"(?P<op><=|>=|≤|≥|<|>|=)?\s*"
    rf"(?P<numbers>{_NUMBER}(?:\s*/\s*{_NUMBER})*)"
    r"\s*(?P<unit>°[CF]|[A-Za-zµΩ%][A-Za-z0-9µΩ°/%-]*)?"
)


@dataclass(frozen=True, slots=True)
class Quantity:
    """One number the source states, with its relation and unit."""

    number: float
    unit: str | None
    relation: Relation
    text: str
    start: int
    end: int
    #: True when this came from a `50/60 Hz` style enumeration of alternatives.
    enumerated: bool = False

    @property
    def resolved_unit(self) -> str | None:
        """The registry symbol this source unit denotes, if unambiguous."""
        return resolve_source_unit(self.unit)

    @property
    def has_known_unit(self) -> bool:
        return self.resolved_unit is not None

    def dimension(self) -> str | None:
        resolved = self.resolved_unit
        return units.dimension_of(resolved) if resolved else None

    def as_unit(self, target: str) -> float | None:
        """This magnitude expressed in `target`, or None if not convertible."""
        resolved = self.resolved_unit
        if resolved is None or not units.is_known(target):
            return None
        if units.dimension_of(resolved) != units.dimension_of(target):
            return None
        try:
            return units.convert(self.number, resolved, target)
        except units.UnitError:  # pragma: no cover - guarded by the dimension check
            return None


#: Symbols longer than this are not case-resolved. Real unit symbols are short, and an
#: exhaustive case search must stay bounded.
_MAX_RESOLVABLE_SYMBOL = 4


def resolve_source_unit(symbol: str | None) -> str | None:
    """Resolve a publisher's unit typography to a registry symbol, or `None`.

    Manufacturers write `KW` for kilowatt and `Mm` for millimetre. Those are typographic
    slips, not different quantities, and refusing them costs real evidence.

    `units.lookup` deliberately refuses to fold case, and it is right to: it is the
    conversion authority, where `mA` and `MA` must never be conflated. Reading a
    document's typography is a different job, so the resolution lives here — and it is
    guarded rather than permissive.

    Every case variant is tried exhaustively. The symbol resolves **only if exactly one
    registry symbol matches**; if two do, the casing is load-bearing and the value is
    left unresolved. In the current registry that guard fires on exactly one pair —
    `mW` (milliwatt) against `MW` (megawatt) — which is precisely the case where
    guessing would be a thousand-fold error. The guard is structural, so it keeps
    holding if the registry grows.
    """
    if symbol is None:
        return None
    candidate = symbol.strip()
    if not candidate:
        return None
    if units.is_known(candidate):
        return candidate
    letters = [i for i, ch in enumerate(candidate) if ch.isalpha()]
    if not letters or len(letters) > _MAX_RESOLVABLE_SYMBOL:
        return None

    matches: set[str] = set()
    for mask in range(1 << len(letters)):
        chars = list(candidate)
        for bit, index in enumerate(letters):
            chars[index] = chars[index].upper() if mask >> bit & 1 else chars[index].lower()
        variant = "".join(chars)
        if units.is_known(variant):
            matches.add(variant)
    return matches.pop() if len(matches) == 1 else None


def normalize_text(text: str) -> str:
    """Fold representation-only differences: NBSP, exotic spaces, Unicode form.

    NFKC only, so `m²` folding to `m2` is accepted, but nothing semantic changes. This
    is *not* OCR tolerance and never turns one number into another.
    """
    folded = unicodedata.normalize("NFKC", text)
    return folded.replace(" ", " ").replace(" ", " ").replace(" ", " ")


def _clean_number(raw: str) -> float | None:
    try:
        return float(raw.replace(",", "."))
    except ValueError:  # pragma: no cover - the pattern already constrains this
        return None


def _is_identifier_digit(source: str, position: int) -> bool:
    """Whether this number is part of a code rather than a measurement.

    `AC-3`, `IP-65` and similar attach a digit to a token with a hyphen. Reading the `3`
    out of `AC-3` as a quantity would let a utilisation category weakly support an
    unrelated unitless claim of 3, so hyphen-joined digits are skipped.
    """
    if position == 0 or source[position - 1] != "-":
        return False
    return position >= 2 and source[position - 2].isalnum()


def parse_quantities(text: str) -> tuple[Quantity, ...]:
    """Every quantity stated in `text`, in order, with relations preserved."""
    source = normalize_text(text)
    found: list[Quantity] = []

    for match in _QUANTITY.finditer(source):
        if _is_identifier_digit(source, match.start("numbers")):
            continue
        numbers_raw = match.group("numbers")
        unit = match.group("unit")
        if unit is not None:
            unit = unit.strip().rstrip(".,;:")
            if not unit:
                unit = None

        relation = Relation.EQ
        if match.group("op"):
            relation = next(r for token, r in _OPERATORS if token == match.group("op"))

        parts = [p.strip() for p in numbers_raw.split("/")]
        enumerated = len(parts) > 1
        for part in parts:
            number = _clean_number(part)
            if number is None:
                continue
            found.append(
                Quantity(
                    number=number,
                    unit=unit,
                    relation=relation,
                    text=match.group(0).strip(),
                    start=match.start(),
                    end=match.end(),
                    enumerated=enumerated,
                )
            )
    return tuple(found)


def magnitudes_agree(left: float, right: float, *, tolerance: float = 1e-9) -> bool:
    """Numeric equality with a floating-point epsilon, never a fuzzy tolerance."""
    return abs(left - right) <= tolerance * max(1.0, abs(left), abs(right))


def quantity_supports(
    stated: Quantity, *, number: float, unit: str | None, relation: Relation = Relation.EQ
) -> bool:
    """Whether a stated quantity supports a claimed one.

    Relations must agree. A source bound (`<= 440 V`) does **not** support a claimed point
    (`440 V`): "rated up to 440 V" and "measured at 440 V" are different assertions, and
    conflating them is how a plausible-looking wrong operating point gets licensed.
    """
    if stated.relation is not relation:
        return False

    if unit is None:
        # A bare number claim, e.g. a contact count. The source may write `3 NO`, where
        # `NO` is a qualifier rather than a unit — an unrecognised symbol means the source
        # is not asserting a dimensioned quantity, so it can still support the count. A
        # source stating a *known* unit is making a more specific claim and does not.
        if stated.has_known_unit:
            return False
        return magnitudes_agree(stated.number, number)

    if stated.unit is None:
        return False
    if not units.is_known(unit) or not stated.has_known_unit:
        # Either symbol unresolvable: fall back to exact identity rather than guessing.
        return stated.unit == unit and magnitudes_agree(stated.number, number)

    converted = stated.as_unit(unit)
    if converted is None:
        return False
    return magnitudes_agree(converted, number)


__all__ = [
    "Quantity",
    "Relation",
    "magnitudes_agree",
    "normalize_text",
    "parse_quantities",
    "quantity_supports",
]
