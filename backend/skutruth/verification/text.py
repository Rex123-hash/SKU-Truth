"""Locating coherent text evidence units in an ingested page.

The model's quote is a **locator hint**, never the evidence. This module finds where that
hint occurs in the artifact and then hands back the *artifact's own* surrounding line. The
claim is checked against that line, so a paraphrased or subtly altered quote cannot verify
itself.

## Why a line is the evidence unit

A datasheet states a rating and its operating point together on one row:

    18 A (at <60 °C) at <= 440 V AC AC-3 for power circuit

That line is one coherent assertion. Bounding the evidence unit to it is what makes the
one-evidence-unit rule mechanical rather than aspirational — a number from this line
cannot be married to a qualifier three paragraphs away, because the qualifier is simply
not inside the unit being examined.
"""

from __future__ import annotations

from dataclasses import dataclass

from skutruth.ingest.models import IngestedPage

from .models import TextMatchMode
from .quantities import normalize_text


@dataclass(frozen=True, slots=True)
class LocatedUnit:
    """One occurrence of the hint, with the artifact line that contains it."""

    text: str
    start: int
    end: int
    match_mode: TextMatchMode
    matched_text: str


def _line_bounds(text: str, position: int) -> tuple[int, int]:
    start = text.rfind("\n", 0, position) + 1
    end = text.find("\n", position)
    return start, (len(text) if end == -1 else end)


def _find_all(haystack: str, needle: str) -> list[int]:
    found: list[int] = []
    index = haystack.find(needle)
    while index != -1:
        found.append(index)
        index = haystack.find(needle, index + 1)
    return found


def locate_units(page: IngestedPage, fragment: str) -> tuple[LocatedUnit, ...]:
    """Every artifact line containing `fragment`, literally or after normalisation.

    Literal matching is tried first and, if it succeeds, normalisation is not attempted:
    a literal hit is already exact, and mixing the two would report the same occurrence
    twice under different modes.
    """
    hint = fragment.strip()
    if not hint:
        return ()

    raw = page.raw_text
    units: list[LocatedUnit] = []

    for position in _find_all(raw, hint):
        start, end = _line_bounds(raw, position)
        units.append(
            LocatedUnit(
                text=raw[start:end],
                start=start,
                end=end,
                match_mode=TextMatchMode.LITERAL,
                matched_text=raw[position : position + len(hint)],
            )
        )
    if units:
        return tuple(units)

    # Representation-only fallback. Normalisation is applied to the page and the hint
    # identically, so offsets stay meaningful within the normalised text.
    normalized_page = normalize_text(raw)
    normalized_hint = normalize_text(hint)
    for position in _find_all(normalized_page, normalized_hint):
        start, end = _line_bounds(normalized_page, position)
        units.append(
            LocatedUnit(
                text=normalized_page[start:end],
                start=start,
                end=end,
                match_mode=TextMatchMode.NORMALIZED,
                matched_text=normalized_page[position : position + len(normalized_hint)],
            )
        )
    return tuple(units)


__all__ = ["LocatedUnit", "locate_units"]
