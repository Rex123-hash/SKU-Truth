"""Exact text location within an ingested artifact.

Infrastructure for the future span verifier, and **not itself verification.** Finding
a string on a page establishes that the string is on the page. It says nothing about
whether that text supports a proposed product attribute, which is a question about
meaning, conditions, and identity scope that this module does not touch.

Only exact matching, on both representations:

* against `raw_text`, which yields a character offset a reviewer can be pointed at;
* against `search_text`, which tolerates the whitespace and ligature differences that
  make a copied quote fail a byte-for-byte match.

A `search_text` hit is deliberately marked as such, because that representation is
lossy: NFKC folds `m²` into `m2`, so a match there is a candidate to confirm, never a
confirmation. Nothing fuzzy, semantic, or model-driven belongs here.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import IngestedArtifact
from .text import normalize_quote


@dataclass(frozen=True, slots=True)
class TextMatch:
    """One exact occurrence of a quote on one page."""

    page_number: int
    start: int
    end: int
    matched_representation: str  # "raw" | "search"
    excerpt: str

    @property
    def is_exact_raw_match(self) -> bool:
        """Whether this was found in the unmodified page text.

        A `search` match is a candidate located in a lossy index; only a `raw` match
        points at characters the document actually contains.
        """
        return self.matched_representation == "raw"


def find_text(
    artifact: IngestedArtifact,
    quote: str,
    *,
    page_number: int | None = None,
    max_matches: int = 20,
) -> tuple[TextMatch, ...]:
    """Locate `quote` in the artifact. Exact matching only.

    Tries `raw_text` first, since a hit there is directly citable. Falls back to the
    normalised `search_text` for pages where the raw form did not match, and labels
    those results accordingly.

    Returns an empty tuple when nothing matches. That is not evidence of absence in
    any strong sense — the parser may have ordered a table differently from how a
    reader sees it — which is another reason this is not verification.
    """
    if not quote.strip():
        return ()

    pages = (
        [p for p in artifact.pages if p.page_number == page_number]
        if page_number is not None
        else list(artifact.pages)
    )
    normalized = normalize_quote(quote)
    matches: list[TextMatch] = []

    for page in pages:
        found_raw = False
        for start in _find_all(page.raw_text, quote):
            found_raw = True
            matches.append(
                TextMatch(
                    page_number=page.page_number,
                    start=start,
                    end=start + len(quote),
                    matched_representation="raw",
                    excerpt=_excerpt(page.raw_text, start, len(quote)),
                )
            )
            if len(matches) >= max_matches:
                return tuple(matches)
        if found_raw or not normalized:
            continue
        for start in _find_all(page.search_text, normalized):
            matches.append(
                TextMatch(
                    page_number=page.page_number,
                    start=start,
                    end=start + len(normalized),
                    matched_representation="search",
                    excerpt=_excerpt(page.search_text, start, len(normalized)),
                )
            )
            if len(matches) >= max_matches:
                return tuple(matches)

    return tuple(matches)


def page_contains(artifact: IngestedArtifact, page_number: int, quote: str) -> bool:
    """Whether the quote occurs on that page, in either representation."""
    return bool(find_text(artifact, quote, page_number=page_number, max_matches=1))


def _find_all(haystack: str, needle: str):
    if not needle:
        return
    start = haystack.find(needle)
    while start != -1:
        yield start
        start = haystack.find(needle, start + 1)


def _excerpt(text: str, start: int, length: int, context: int = 60) -> str:
    lo = max(0, start - context)
    hi = min(len(text), start + length + context)
    return text[lo:hi]
