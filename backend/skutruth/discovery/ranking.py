"""Deterministic candidate ordering.

Lexicographic over named tiers, not a learned score. Every candidate can therefore say
*why* it ranked where it did, in words a reviewer can check, and two runs over the same
results always produce the same order.

    1. authority   — approved manufacturer first; marketplace and blocked last
    2. relevance   — exact reference, then family, then sibling, then absent
    3. kind        — datasheet, catalogue, product page, manual, unknown
    4. provider rank — a weak tiebreak, and the only place it is consulted at all

The first tier is the one that matters: **an approved manufacturer page for the exact
product always outranks a third-party page for the exact product**, however the search
engine ordered them. Popularity is not authority, and a first-place result from a
reseller is still a reseller.

Provider rank appears last on purpose. It is the only signal here that a search engine
controls, so anything it could outrank would be a decision the engine had made for us.
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import MpnRelevance, SourceAuthority, SourceCandidate, SourceKind

#: Lower sorts first.
AUTHORITY_ORDER: dict[SourceAuthority, int] = {
    SourceAuthority.APPROVED_MANUFACTURER: 0,
    # Above an unknown host — the registry does connect it to the manufacturer — and
    # below an approved one, because ranking must never let it be mistaken for licensed.
    SourceAuthority.UNVERIFIED_MANUFACTURER: 1,
    SourceAuthority.OTHER_MANUFACTURER: 2,
    SourceAuthority.UNKNOWN: 3,
    SourceAuthority.KNOWN_DISTRIBUTOR: 4,
    SourceAuthority.KNOWN_MARKETPLACE: 5,
    SourceAuthority.BLOCKED: 6,
}

RELEVANCE_ORDER: dict[MpnRelevance, int] = {
    MpnRelevance.EXACT: 0,
    MpnRelevance.FAMILY_ONLY: 1,
    MpnRelevance.SIBLING: 2,
    MpnRelevance.AMBIGUOUS: 3,
    MpnRelevance.ABSENT: 4,
}

#: Documents that state specifications outrank pages that mostly link to them. This is a
#: mild preference, and it never crosses an authority or relevance boundary.
KIND_ORDER: dict[SourceKind, int] = {
    SourceKind.DATASHEET: 0,
    SourceKind.CATALOG: 1,
    SourceKind.PRODUCT_PAGE: 2,
    SourceKind.MANUAL: 3,
    SourceKind.UNKNOWN: 4,
}


def ranking_key(candidate: SourceCandidate) -> tuple[int, int, int, int, str]:
    """The sort key. The trailing URL makes ties total rather than input-order dependent."""
    return (
        AUTHORITY_ORDER[candidate.authority],
        RELEVANCE_ORDER[candidate.relevance],
        KIND_ORDER[candidate.kind],
        candidate.result.rank,
        candidate.url,
    )


def ranking_reasons(candidate: SourceCandidate) -> tuple[str, ...]:
    """The key in words, so an ordering can be audited rather than trusted."""
    return (
        f"authority={candidate.authority.value}",
        f"relevance={candidate.relevance.value}",
        f"kind={candidate.kind.value}",
        f"provider_rank={candidate.result.rank}",
    )


def rank_candidates(candidates: Sequence[SourceCandidate]) -> tuple[SourceCandidate, ...]:
    """Best first. Stable, total, and independent of the order results arrived in."""
    return tuple(sorted(candidates, key=ranking_key))


__all__ = [
    "AUTHORITY_ORDER",
    "KIND_ORDER",
    "RELEVANCE_ORDER",
    "rank_candidates",
    "ranking_key",
    "ranking_reasons",
]
