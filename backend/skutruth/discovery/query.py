"""Deterministic search-query construction.

Queries are built from templates, in a fixed order, from fields the input actually
supplies. **No language model participates.** Asking a model to invent search queries
would make the set of documents we consider depend on a sampled generation, so two runs
of the same product could consult different sources and neither could be reproduced. It
would also put the model upstream of every trust decision that follows it.

Every query string is recorded on the result, so what was asked is auditable rather than
inferred from what came back.

## Quoting

The reference is quoted so a provider matches it as a phrase rather than splitting it
into tokens. Quotes inside the input are stripped rather than escaped — a part number
containing a double quote is far more likely to be dirty data than a real reference, and
passing it through would corrupt the query for every provider differently.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import DiscoveryRequest

#: Bumped when a change here could alter which documents a run considers.
QUERY_VERSION = "discovery-query@v1"


@dataclass(frozen=True, slots=True)
class QueryBudget:
    """Bounded work. Discovery must never become a crawl."""

    max_queries: int = 4
    max_site_queries: int = 2


def _clean(value: str | None) -> str:
    """Collapse whitespace and drop quoting characters."""
    if not value:
        return ""
    return " ".join(value.replace('"', " ").replace("'", " ").split())


def build_queries(
    request: DiscoveryRequest,
    *,
    approved_domains: tuple[str, ...] = (),
    budget: QueryBudget | None = None,
) -> tuple[str, ...]:
    """The queries to run for one product, in priority order, de-duplicated.

    Site-restricted queries come first when the manufacturer's domains are known: they
    are the only queries that can *only* return manufacturer-owned pages, so they spend
    the budget where an authoritative answer is possible at all.
    """
    limits = budget or QueryBudget()
    mpn = _clean(request.mpn)
    if not mpn:
        return ()

    manufacturer = _clean(request.manufacturer_hint)
    quoted = f'"{mpn}"'

    ordered: list[str] = []
    for domain in approved_domains[: limits.max_site_queries]:
        ordered.append(f"{quoted} site:{domain}")
    if manufacturer:
        ordered.append(f"{quoted} {manufacturer}")
    ordered.append(f"{quoted} datasheet")
    if not manufacturer and request.brand_signals:
        ordered.append(f"{quoted} {_clean(request.brand_signals[0])}")

    seen: set[str] = set()
    unique = [q for q in ordered if q and not (q in seen or seen.add(q))]
    return tuple(unique[: limits.max_queries])


__all__ = ["QUERY_VERSION", "QueryBudget", "build_queries"]
