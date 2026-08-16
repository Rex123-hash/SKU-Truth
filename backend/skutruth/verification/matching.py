"""Boundary-safe phrase matching for text and categorical values.

Bare substring containment is not evidence. `"AC" in "VACUUM"` is true, and so is
`"NO" in "NORMAL"` — both would license a controlled value the document never states.
Short values are exactly where this bites, and short values are what a Unilog LOV is
full of (`NO`, `NC`, `SS`, `Brass`), so the rule has to be structural rather than a
list of special cases.

## The rule

A phrase is present only if it occurs with a **boundary at both ends**, where a
boundary is any character that is neither alphanumeric nor a *joiner*.

    joiners: -  /  _  +

Joiners are treated as non-boundaries deliberately. They are the characters that bind
two tokens into one compound designation, and a compound is a different value from its
parts:

| Source            | Claim   | Result | Why |
|-------------------|---------|--------|-----|
| `Voltage type AC` | `AC`    | match  | space on both sides |
| `AC-3`            | `AC-3`  | match  | whole designation |
| `AC-3`            | `AC`    | **no** | `AC-3` is a utilisation category, not a voltage type |
| `AC-30`           | `AC-3`  | **no** | truncation is not a match |
| `VACUUM`          | `AC`    | **no** | interior of a word |
| `BRASS`           | `Brass` | match  | case-insensitive |
| `Brass-plated`    | `Brass` | **no** | brass-plated is not brass |

The last row is the conservative call this module makes deliberately. A hyphenated
compound frequently *qualifies* the value into a different one, and mechanical text
matching cannot tell the qualifying case from the incidental case. Refusing costs a
little recall and cannot manufacture a wrong specification.

`.` is **not** a joiner: a trailing full stop is sentence punctuation, and refusing
`Stainless Steel` in `Housing: Stainless Steel.` would be strictness with no safety
argument behind it. Numbers never reach this module — they go through `quantities`,
where units and relations are checked properly.

## What this is not

It is not synonym matching. `screw clamp terminals` does not match `Screw connection`
here and must not: that mapping may well be correct, but it is a controlled-vocabulary
decision backed by a published synonym list, not something text can establish. Keeping
it out of this module is what stops span verification from quietly becoming semantic
interpretation.
"""

from __future__ import annotations

from .quantities import normalize_text

#: Characters that bind tokens into a single compound designation. A match may not sit
#: directly against one of these, because `AC` inside `AC-3` is part of another value.
JOINERS = frozenset("-/_+")


def _is_boundary(char: str) -> bool:
    return not (char.isalnum() or char in JOINERS)


def prepare(text: str) -> str:
    """Fold representation-only differences, for matching only.

    NFKC and exotic spaces via `normalize_text`, then case folding, then runs of
    whitespace collapsed to one space so a value split across a wrapped table cell
    still compares equal. No character is substituted and nothing semantic changes.
    """
    return " ".join(normalize_text(text).casefold().split())


def contains_phrase(haystack: str, phrase: str) -> bool:
    """Whether `phrase` occurs in `haystack` as a whole, boundary-delimited phrase."""
    hay = prepare(haystack)
    needle = prepare(phrase)
    if not needle or not hay:
        return False

    index = hay.find(needle)
    while index != -1:
        end = index + len(needle)
        before_ok = index == 0 or _is_boundary(hay[index - 1])
        after_ok = end == len(hay) or _is_boundary(hay[end])
        if before_ok and after_ok:
            return True
        index = hay.find(needle, index + 1)
    return False


__all__ = ["JOINERS", "contains_phrase", "prepare"]
