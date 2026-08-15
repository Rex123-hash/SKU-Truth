"""Canonical manufacturer part number comparison, at the contract boundary only.

FROZEN CONTRACT — see contracts/README.md before changing anything here.

This exists for exactly one job: deciding whether an exact-SKU artifact is about the
product a record resolved to. It is **not** the identity resolver, and it must not
grow into one.

The normalisation is deliberately conservative — case and whitespace only. Real MPN
matching also has to reason about hyphenation, packaging suffixes, regional variants,
and manufacturer-specific formatting, and every one of those rules can conflate two
genuinely different parts if applied blindly. Getting that wrong here would silently
license the wrong evidence, which is the failure this comparison exists to prevent.
So the contract only recognises differences it can be certain are cosmetic, and
anything cleverer belongs in the identity stage, behind evaluation.
"""

from __future__ import annotations


def canonical_mpn(mpn: str | None) -> str | None:
    """Fold away case and whitespace. Returns `None` for anything empty.

    `None` never compares equal to anything, including another `None` — see
    `mpn_matches`. An artifact that does not say which reference it covers cannot be
    shown to cover *this* one.
    """
    if mpn is None:
        return None
    folded = "".join(mpn.split()).upper()
    return folded or None


def mpn_matches(a: str | None, b: str | None) -> bool:
    """True only when both references are present and canonically identical."""
    ca, cb = canonical_mpn(a), canonical_mpn(b)
    return ca is not None and ca == cb
