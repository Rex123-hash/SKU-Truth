"""Placeholder recognition — field-aware on purpose.

The organizer states that `-- Unbranded --`, `-- No Unilog Brand --` and
`-- No DIB Brand --` mean *the field is empty*, not that the product is unbranded. A
placeholder that reaches matching, prompting, or scoring would be treated as a real
manufacturer or brand, so it is turned into `None` at the boundary.

Two rules, deliberately different in scope:

* **The `-- … --` sentinel form is recognised in any field.** The double-hyphen wrapper
  is a distinctive marker, not something a real catalogue value looks like.
* **A bare `-` is recognised only where it has been observed to mean "absent"** —
  currently `Part_Manuf`, where the audit found it on 41 of 1,000 rows. A lone hyphen is
  perfectly legitimate elsewhere (a part number, a size range, a hyphenated description),
  so treating it as a global null would silently destroy real data.

The raw value is never overwritten. `RawProductRow` keeps the original string alongside
the cleaned one, because "the source said `-- Unbranded --`" and "the source said
nothing" are different facts and a reviewer may need to tell them apart.
"""

from __future__ import annotations

import re

#: The organizer's documented sentinel form, e.g. `-- No Unilog Brand --`.
SENTINEL = re.compile(r"^--\s*.*?\s*--$")

#: Fields where a bare `-` has been observed to mean "no value". Extend only from
#: evidence in a real file, never by assumption.
BARE_HYPHEN_FIELDS = frozenset({"Part_Manuf"})

#: Documented literals, kept for reporting and so a reader can see what is recognised.
DOCUMENTED_PLACEHOLDERS = (
    "-- Unbranded --",
    "-- No Unilog Brand --",
    "-- No DIB Brand --",
)


def is_placeholder(field_name: str, value: str | None) -> bool:
    """Whether `value` in `field_name` means "the field is empty".

    Blank and whitespace-only values are *not* placeholders — they are simply empty, and
    the distinction is preserved so callers can report on it.
    """
    if value is None:
        return False
    stripped = value.strip()
    if not stripped:
        return False
    if SENTINEL.match(stripped):
        return True
    return stripped == "-" and field_name in BARE_HYPHEN_FIELDS


def clean(field_name: str, value: str | None) -> str | None:
    """The usable value, or `None` for a placeholder or an empty string.

    Whitespace is trimmed. Nothing else is altered: casing, punctuation, and symbols
    are the publisher's, and normalising them here would pre-empt a canonicalisation
    step that needs the master list we do not have.
    """
    if value is None:
        return None
    stripped = value.strip()
    if not stripped or is_placeholder(field_name, stripped):
        return None
    return stripped


__all__ = [
    "BARE_HYPHEN_FIELDS",
    "DOCUMENTED_PLACEHOLDERS",
    "SENTINEL",
    "clean",
    "is_placeholder",
]
