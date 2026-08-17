"""Deciding what a candidate is: whose site, which product, what kind of document.

Three deterministic questions, none of which a language model is asked:

* **authority** — does the manufacturer publish from this host? Answered by the reviewed
  registry, never by the page's own claims.
* **relevance** — does this candidate name the exact reference? Answered by token
  comparison against the frozen `canonical_mpn`.
* **kind** — datasheet, product page, catalogue? A weak hint for ranking only.

## Relevance can only demote

`EXACT` is the only state that lets a candidate be acquired. `FAMILY_ONLY` and `SIBLING`
exist to *refuse* candidates that look right at a glance — a page about `LC1D18` is not
about `LC1D18P7`, and a page about `LC1D18B7` is about a different coil voltage. Reading
those as the target is precisely the family-to-exact leap the identity resolver was built
to prevent, and discovery must not smuggle it in one stage earlier.

Even `EXACT` proves nothing about the product. It means the reference appears in a URL or
a title, which is a reason to fetch the document — after which identity resolution and
mechanical verification apply unchanged.

## Why a prefix rule is safe here

Family and sibling detection compares token prefixes, which is exactly the kind of
"cleverer" MPN reasoning `contracts/mpn.py` warns belongs behind evaluation. It is
admissible here for one reason: it is only ever used to reject. A heuristic that can lose
a good source costs recall; one that grants authority costs correctness. Only the frozen
`canonical_mpn` can produce `EXACT`.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

from skutruth.contracts.mpn import canonical_mpn

from .domains import DomainRegistry, normalize_host
from .errors import RejectionReason
from .models import MpnRelevance, SearchResult, SourceAuthority, SourceKind

#: Shortest shared prefix that may be called a family relationship. Below this, two
#: references sharing a few characters are a coincidence, not a family.
MIN_STEM_LENGTH = 5

_TOKEN = re.compile(r"[A-Za-z0-9]+")

_DATASHEET_HINTS = ("datasheet", "data-sheet", "data_sheet", "specification", "spec-sheet")
_CATALOG_HINTS = ("catalog", "catalogue")
_MANUAL_HINTS = ("manual", "instruction", "installation", "user-guide")


def host_of(url: str) -> str:
    """The normalized host, or an empty string if the URL is unusable."""
    try:
        return normalize_host(urlsplit(url).hostname)
    except ValueError:
        return ""


def _tokens(*parts: str) -> set[str]:
    """Uppercase alphanumeric tokens from URL and title text."""
    found: set[str] = set()
    for part in parts:
        if not part:
            continue
        found.update(t.upper() for t in _TOKEN.findall(unquote(part)))
    return found


def classify_authority(
    host: str, *, registry: DomainRegistry, manufacturer_hint: str | None
) -> SourceAuthority:
    """Whose site this is, relative to the product's manufacturer.

    Blocked hosts are checked first: an explicit refusal outranks every other reading,
    including a host that also appears on a manufacturer's domain list.
    """
    normalized = normalize_host(host)
    if not normalized:
        return SourceAuthority.UNKNOWN
    if registry.is_blocked(normalized):
        return SourceAuthority.BLOCKED

    owner = registry.owner_of(normalized)
    if owner is not None:
        if owner.matches_hint(manufacturer_hint):
            return SourceAuthority.APPROVED_MANUFACTURER
        return SourceAuthority.OTHER_MANUFACTURER

    if registry.is_marketplace(normalized):
        return SourceAuthority.KNOWN_MARKETPLACE
    if registry.is_distributor(normalized):
        return SourceAuthority.KNOWN_DISTRIBUTOR
    return SourceAuthority.UNKNOWN


def classify_relevance(result: SearchResult, *, mpn: str) -> MpnRelevance:
    """How this candidate's URL and title relate to the target reference.

    The snippet is deliberately **not** consulted. A snippet is provider-generated text
    that may quote a page's cross-sell list; letting it establish that a page is about a
    product would make a search engine's summarisation into a product decision.
    """
    target = canonical_mpn(mpn)
    if not target:
        return MpnRelevance.ABSENT

    tokens = _tokens(result.url, result.title)
    if target in tokens:
        return MpnRelevance.EXACT

    families: set[str] = set()
    siblings: set[str] = set()
    for token in tokens:
        if len(token) < MIN_STEM_LENGTH or token == target:
            continue
        if target.startswith(token):
            families.add(token)
            continue
        shared = _common_prefix_length(token, target)
        if shared >= MIN_STEM_LENGTH:
            siblings.add(token)

    if len(siblings) > 1:
        return MpnRelevance.AMBIGUOUS
    if siblings:
        return MpnRelevance.SIBLING
    if families:
        return MpnRelevance.FAMILY_ONLY
    return MpnRelevance.ABSENT


def _common_prefix_length(a: str, b: str) -> int:
    length = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        length += 1
    return length


def classify_kind(result: SearchResult) -> SourceKind:
    """A weak structural hint. Never an authority or correctness claim."""
    haystack = f"{result.url} {result.title}".casefold()
    path = urlsplit(result.url).path.casefold()

    if any(h in haystack for h in _CATALOG_HINTS):
        return SourceKind.CATALOG
    if any(h in haystack for h in _MANUAL_HINTS):
        return SourceKind.MANUAL
    if any(h in haystack for h in _DATASHEET_HINTS) or path.endswith(".pdf"):
        return SourceKind.DATASHEET
    if "/product" in path or "/products" in path:
        return SourceKind.PRODUCT_PAGE
    return SourceKind.UNKNOWN


#: Why each non-approved authority may not license a product fact.
AUTHORITY_REJECTIONS: dict[SourceAuthority, RejectionReason] = {
    SourceAuthority.BLOCKED: RejectionReason.DOMAIN_NOT_APPROVED,
    SourceAuthority.KNOWN_MARKETPLACE: RejectionReason.MARKETPLACE_SOURCE,
    SourceAuthority.KNOWN_DISTRIBUTOR: RejectionReason.DISTRIBUTOR_SOURCE,
    SourceAuthority.OTHER_MANUFACTURER: RejectionReason.OTHER_MANUFACTURER_DOMAIN,
    SourceAuthority.UNKNOWN: RejectionReason.DOMAIN_NOT_APPROVED,
}

#: Why each non-exact relevance may not be treated as this product.
RELEVANCE_REJECTIONS: dict[MpnRelevance, RejectionReason] = {
    MpnRelevance.FAMILY_ONLY: RejectionReason.FAMILY_ONLY,
    MpnRelevance.SIBLING: RejectionReason.SIBLING_REFERENCE,
    MpnRelevance.AMBIGUOUS: RejectionReason.AMBIGUOUS_REFERENCE,
    MpnRelevance.ABSENT: RejectionReason.MPN_ABSENT,
}


def rejection_reasons(
    authority: SourceAuthority, relevance: MpnRelevance
) -> tuple[RejectionReason, ...]:
    """Every reason this candidate cannot license a fact. Empty means eligible.

    Both axes are reported rather than short-circuiting on the first: a reviewer looking
    at a rejected marketplace page for the wrong product should see both problems.
    """
    reasons: list[RejectionReason] = []
    if not authority.may_license_evidence:
        reasons.append(AUTHORITY_REJECTIONS[authority])
    if not relevance.is_exact:
        reasons.append(RELEVANCE_REJECTIONS[relevance])
    return tuple(reasons)


__all__ = [
    "AUTHORITY_REJECTIONS",
    "MIN_STEM_LENGTH",
    "RELEVANCE_REJECTIONS",
    "classify_authority",
    "classify_kind",
    "classify_relevance",
    "host_of",
    "rejection_reasons",
]
