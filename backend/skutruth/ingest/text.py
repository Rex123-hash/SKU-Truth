"""Page text: what is preserved, and what may be normalised.

Two representations, kept side by side, because they answer different questions.

**`raw_text`** is what the parser produced, altered only by converting CRLF and CR to
LF. Nothing else is touched. This is the representation a reviewer sees and the one a
future span locator must be able to point into, so it keeps its punctuation, its
minus signs, its superscripts, its degree symbols, its non-breaking spaces, and its
line ordering — all of which can be evidence. `18 A` and `18 Ω` differ by a character
that a keen normaliser would happily mangle.

**`search_text`** is a derived index for finding candidate matches: NFKC-normalised,
whitespace collapsed, casefolded. It exists because a quote copied out of a datasheet
rarely matches the extracted stream byte-for-byte — a ligature here, a soft hyphen
there, a line break in the middle of a table row.

The rule that matters: **quote verification must never depend solely on
`search_text`.** Finding a candidate in the normalised form is a hint about where to
look; confirming it against `raw_text` is what makes it evidence. Normalisation is
lossy by design, and a system that only ever compared lossy forms would happily
verify a quote that says something slightly different from the document.

NFKC is chosen deliberately and named in `TEXT_NORMALIZATION_FORM`. It folds
compatibility characters — ligatures, superscript digits, full-width forms — which is
what makes it useful for search and exactly why it is unsafe for evidence: NFKC turns
`m²` into `m2`, and a square metre is not a metre.
"""

from __future__ import annotations

import re
import unicodedata

#: Recorded on every artifact so a later parser or policy change is observable.
TEXT_NORMALIZATION_FORM = "NFKC"

_WHITESPACE = re.compile(r"\s+")

#: Zero-width and formatting characters that survive extraction and break naive
#: matching without carrying meaning. Removed from `search_text` only.
_INVISIBLE = str.maketrans(
    {
        "­": "",  # soft hyphen
        "​": "",  # zero-width space
        "‌": "",  # zero-width non-joiner
        "‍": "",  # zero-width joiner
        "﻿": "",  # byte-order mark
    }
)


def normalize_line_endings(text: str) -> str:
    """CRLF and lone CR to LF. The only change made to `raw_text`.

    Safe because a line ending is a transport artefact, not content: no datasheet
    means something different by CRLF than by LF. Everything else is left alone.
    """
    return text.replace("\r\n", "\n").replace("\r", "\n")


def build_search_text(raw: str) -> str:
    """Derive the lossy search representation from raw page text.

    NFKC, invisible characters dropped, whitespace collapsed to single spaces,
    casefolded. Suitable for locating a candidate; never sufficient to confirm one.
    """
    folded = unicodedata.normalize(TEXT_NORMALIZATION_FORM, raw)
    folded = folded.translate(_INVISIBLE)
    return _WHITESPACE.sub(" ", folded).strip().casefold()


def normalize_quote(quote: str) -> str:
    """Put a proposed quote into the same space as `search_text`.

    Both sides of a comparison must be normalised the same way, so this is the only
    supported route for turning a quote into something comparable.
    """
    return build_search_text(quote)
