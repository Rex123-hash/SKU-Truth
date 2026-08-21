"""Parsing the `Part_Manuf` field into a name and a supplier code.

The organizer input carries the supplier as one string with a code appended in
parentheses — `Kichler Lighting (KICLI)`. Splitting that is pure structure, so it is
done deterministically here and produces a code that needs no matching at all.

**No canonicalisation happens in this parser.** `Phillips Lighting` stays
`Phillips Lighting`; `Black & Decker/dewlt` stays as written. Both look like misspellings
of real manufacturers, but the approved manufacturer master is not available, and a
correction we cannot check against the approved list is a guess wearing a rule's clothing.
The separate normalization layer may select only explicitly authorized canonical rules;
unknown values remain review candidates rather than being corrected here.

The code is preserved verbatim for the same reason — this sample happens to use 4- and
5-character uppercase codes, but that is an observation about 1,000 rows, not a contract.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .placeholders import is_placeholder

FIELD = "Part_Manuf"

#: A trailing parenthesised group, with no nested parentheses inside it. Anchored to the
#: end so a name that merely *contains* parentheses is not mistaken for a code. The code
#: is allowed to be empty here so that `Acme ()` is caught and refused rather than
#: quietly falling through to "name only".
_TRAILING_CODE = re.compile(r"^(?P<name>.*?)\s*\((?P<code>[^()]*)\)$", re.DOTALL)


def _parentheses_are_well_formed(text: str) -> bool:
    """Balanced *and* correctly ordered.

    Counting alone would accept `Acme )AC(`, which is malformed rather than merely
    code-less, so depth is tracked and a close-before-open fails immediately.
    """
    depth = 0
    for char in text:
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


class ManufacturerParse(StrEnum):
    """What the raw supplier string turned out to be."""

    NAME_WITH_CODE = "NAME_WITH_CODE"
    #: A usable name with no parenthesised code. Not a failure.
    NAME_ONLY = "NAME_ONLY"
    #: The field was blank.
    MISSING = "MISSING"
    #: A documented placeholder, e.g. a bare `-`.
    PLACEHOLDER = "PLACEHOLDER"
    #: Present but not confidently splittable — unbalanced parentheses, an empty code,
    #: or a code with no name in front of it. Left unresolved rather than salvaged.
    UNRESOLVED = "UNRESOLVED"


@dataclass(frozen=True, slots=True)
class ParsedManufacturer:
    """The structural reading of one `Part_Manuf` value."""

    raw: str
    status: ManufacturerParse
    display_name: str | None = None
    supplier_code: str | None = None

    @property
    def is_resolved(self) -> bool:
        """Whether a usable manufacturer name was recovered."""
        return self.status in {
            ManufacturerParse.NAME_WITH_CODE,
            ManufacturerParse.NAME_ONLY,
        }

    @property
    def has_code(self) -> bool:
        return self.supplier_code is not None


def parse_part_manuf(value: str | None) -> ParsedManufacturer:
    """Split `Name (CODE)` conservatively. Never corrects spelling."""
    raw = value or ""
    stripped = raw.strip()

    if not stripped:
        return ParsedManufacturer(raw=raw, status=ManufacturerParse.MISSING)
    if is_placeholder(FIELD, stripped):
        return ParsedManufacturer(raw=raw, status=ManufacturerParse.PLACEHOLDER)

    # Malformed parentheses mean we cannot tell where a code would start or end.
    if not _parentheses_are_well_formed(stripped):
        return ParsedManufacturer(raw=raw, status=ManufacturerParse.UNRESOLVED)

    match = _TRAILING_CODE.match(stripped)
    if match is None:
        # Either no parentheses at all, or they are present but not in trailing-code
        # position (`Acme (US) Tools`). Both leave a usable name and no identifiable code.
        return ParsedManufacturer(
            raw=raw, status=ManufacturerParse.NAME_ONLY, display_name=stripped
        )

    name = match.group("name").strip()
    code = match.group("code").strip()
    if not name or not code:
        # `(KICLI)` with no name, or `Acme ()` with no code. Both ambiguous; neither is
        # salvaged, because guessing which half was intended is exactly the failure mode.
        return ParsedManufacturer(raw=raw, status=ManufacturerParse.UNRESOLVED)

    return ParsedManufacturer(
        raw=raw,
        status=ManufacturerParse.NAME_WITH_CODE,
        display_name=name,
        supplier_code=code,
    )


__all__ = ["FIELD", "ManufacturerParse", "ParsedManufacturer", "parse_part_manuf"]
