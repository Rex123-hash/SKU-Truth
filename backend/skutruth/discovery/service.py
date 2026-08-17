"""Discovery, end to end: hints in, ranked candidates and acquired artifacts out.

    DiscoveryRequest
          ↓  deterministic templates
    queries  ─→ search provider (through record/replay)
          ↓
    SearchResult[]  ─→ authority · relevance · kind
          ↓
    SourceCandidate[]  ranked, every one carrying its reasons
          ↓  eligible only: approved manufacturer host, exact reference
    safe fetch  ─→ ArtifactStore
          ↓
    DiscoveryResult

## Failure is a result

`NO_AUTHORITATIVE_SOURCE_FOUND` is the honest outcome for most long-tail products, and it
is better than every alternative. Returning a marketplace listing because it was the only
result would hand the rest of the pipeline a page that cannot license a single fact, and
the trust architecture would then spend its effort discovering that. `found_authoritative_source`
is a plain boolean, and callers are expected to see `False` often.

## Everything is bounded

Queries per product, results per query, fetch attempts, and bytes are all capped. There
is no crawling, no link following, and no spidering — discovery retrieves documents a
search provider named, and stops.

## Nothing here asks a model anything

Not for queries, not for domain authority, not for MPN equivalence. A test asserts this
package imports no model client.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import httpx

from skutruth.contracts import RunMode
from skutruth.ingest.storage import ArtifactStore
from skutruth.replay.errors import ReplayError
from skutruth.replay.store import CassetteStore

from .acquire import AcquiredArtifact, acquire_pdf
from .domains import DomainRegistry
from .errors import FetchError, RejectionReason
from .fetch import FetchedResource, FetchPolicy, Resolver, fetch_url, system_resolver
from .models import (
    DISCOVERY_VERSION,
    CandidateStatus,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoverySummary,
    SearchResult,
    SourceCandidate,
)
from .policy import (
    classify_authority,
    classify_kind,
    classify_relevance,
    host_of,
    rejection_reasons,
)
from .provider import SearchCall, SearchProvider, execute_search
from .query import QueryBudget, build_queries
from .ranking import rank_candidates, ranking_reasons


@dataclass(frozen=True, slots=True)
class DiscoveryBudget:
    """Bounded work for one product. Discovery must never become a crawl."""

    queries: QueryBudget = QueryBudget()
    max_results_per_query: int = 10
    max_fetch_attempts: int = 3
    fetch: FetchPolicy = FetchPolicy()


def classify_candidate(
    result: SearchResult, *, request: DiscoveryRequest, registry: DomainRegistry
) -> SourceCandidate:
    """Apply every deterministic policy to one search result."""
    host = host_of(result.url)
    authority = classify_authority(
        host, registry=registry, manufacturer_hint=request.manufacturer_hint
    )
    relevance = classify_relevance(result, mpn=request.mpn)
    reasons = rejection_reasons(authority, relevance)

    candidate = SourceCandidate(
        result=result,
        host=host,
        authority=authority,
        relevance=relevance,
        kind=classify_kind(result),
        status=CandidateStatus.REJECTED if reasons else CandidateStatus.ACCEPTED_NOT_ACQUIRED,
        rejections=tuple(r.value for r in reasons),
    )
    return candidate.model_copy(update={"rank_reasons": ranking_reasons(candidate)})


def _search_all(
    queries: Sequence[str],
    *,
    provider: SearchProvider,
    cassettes: CassetteStore,
    mode: RunMode,
    max_results: int,
) -> tuple[tuple[SearchResult, ...], tuple[str, ...]]:
    """Run every query, keeping the first sighting of each URL.

    A URL found by two queries is one candidate, credited to the query that found it
    first — recording it twice would double its weight in the counts for no reason.
    """
    seen: set[str] = set()
    results: list[SearchResult] = []
    executed: list[str] = []

    for query in queries:
        executed.append(query)
        found = execute_search(
            SearchCall(query=query, max_results=max_results),
            provider=provider,
            store=cassettes,
            mode=mode,
        )
        for result in found:
            if result.url in seen:
                continue
            seen.add(result.url)
            results.append(result)
    return tuple(results), tuple(executed)


def _acquire_one(
    candidate: SourceCandidate,
    *,
    store: ArtifactStore,
    registry: DomainRegistry,
    manufacturer_hint: str | None,
    publisher: str | None,
    policy: FetchPolicy,
    transport: httpx.BaseTransport | None,
    resolver: Resolver,
) -> tuple[SourceCandidate, AcquiredArtifact | None, int]:
    """Fetch and ingest one eligible candidate. Returns the updated candidate.

    Eligibility was decided from the URL a search engine named. The bytes may arrive from
    somewhere else entirely, so publisher authority is decided again here — against the
    host the download actually came from.
    """
    try:
        resource: FetchedResource = fetch_url(
            candidate.url, policy=policy, transport=transport, resolver=resolver
        )
    except FetchError as exc:
        return (
            candidate.model_copy(
                update={
                    "status": CandidateStatus.REJECTED,
                    "rejections": (*candidate.rejections, exc.reason.value),
                }
            ),
            None,
            0,
        )

    # `fetch_url` already re-applied network policy at every hop. That answers "is this
    # safe to connect to", which is a different question from "may this host publish this
    # manufacturer's data" — a redirect to an ordinary public third-party site passes the
    # first and must fail the second.
    final_authority = classify_authority(
        host_of(resource.final_url), registry=registry, manufacturer_hint=manufacturer_hint
    )
    fetched = candidate.model_copy(
        update={
            "final_authority": final_authority,
            "final_url": resource.final_url,
            "redirect_chain": resource.redirect_chain,
            "http_status": resource.status_code,
            "content_type": resource.content_type,
            "byte_size": resource.byte_size,
            "fetched_at": resource.fetched_at,
        }
    )

    try:
        acquired = acquire_pdf(fetched, resource, store=store, publisher=publisher)
    except FetchError as exc:
        # An official HTML page lands here as NOT_INGESTABLE_YET. It stays accepted:
        # the source is real and eligible, and only this milestone's scope stops short.
        status = (
            CandidateStatus.ACCEPTED_NOT_ACQUIRED
            if exc.reason is RejectionReason.NOT_INGESTABLE_YET
            else CandidateStatus.REJECTED
        )
        return (
            fetched.model_copy(
                update={"status": status, "rejections": (*fetched.rejections, exc.reason.value)}
            ),
            None,
            resource.byte_size,
        )

    return (
        fetched.model_copy(
            update={
                "status": CandidateStatus.ACQUIRED,
                "artifact_sha256": acquired.sha256,
            }
        ),
        acquired,
        resource.byte_size,
    )


def discover_sources(
    request: DiscoveryRequest,
    *,
    provider: SearchProvider,
    registry: DomainRegistry,
    cassettes: CassetteStore,
    artifacts: ArtifactStore | None = None,
    mode: RunMode = RunMode.REPLAY,
    budget: DiscoveryBudget | None = None,
    transport: httpx.BaseTransport | None = None,
    resolver: Resolver = system_resolver,
) -> DiscoveryResult:
    """Find and, where permitted, acquire manufacturer sources for one product.

    With no `artifacts` store, discovery runs to ranked candidates and stops — useful for
    surveying what is findable without downloading anything.
    """
    limits = budget or DiscoveryBudget()
    approved = registry.domains_for_hint(request.manufacturer_hint)
    queries = build_queries(request, approved_domains=approved, budget=limits.queries)

    results, executed = _search_all(
        queries,
        provider=provider,
        cassettes=cassettes,
        mode=mode,
        max_results=limits.max_results_per_query,
    )
    ranked = rank_candidates(
        [classify_candidate(r, request=request, registry=registry) for r in results]
    )

    final: list[SourceCandidate] = []
    attempts = successes = ingested = downloaded = 0

    for candidate in ranked:
        if artifacts is None or not candidate.is_eligible:
            final.append(candidate)
            continue
        if attempts >= limits.max_fetch_attempts:
            final.append(
                candidate.model_copy(
                    update={
                        "rejections": (
                            *candidate.rejections,
                            RejectionReason.FETCH_BUDGET_EXHAUSTED.value,
                        )
                    }
                )
            )
            continue

        attempts += 1
        updated, acquired, byte_size = _acquire_one(
            candidate,
            store=artifacts,
            registry=registry,
            manufacturer_hint=request.manufacturer_hint,
            publisher=request.manufacturer_hint,
            policy=limits.fetch,
            transport=transport,
            resolver=resolver,
        )
        downloaded += byte_size
        if acquired is not None:
            successes += 1
            ingested += 0 if acquired.deduplicated else 1
        final.append(updated)

    summary = DiscoverySummary(
        queries=len(executed),
        search_results=len(results),
        candidates=len(final),
        official_candidates=sum(1 for c in final if c.authority.may_license_evidence),
        exact_mpn_candidates=sum(1 for c in final if c.relevance.is_exact),
        family_candidates=sum(1 for c in final if c.relevance.value == "FAMILY_ONLY"),
        rejected_third_party=sum(
            1 for c in final if not c.authority.may_license_evidence
        ),
        fetch_attempts=attempts,
        fetch_successes=successes,
        artifacts_ingested=ingested,
        bytes_downloaded=downloaded,
    )
    return DiscoveryResult(
        request=request,
        executed_queries=executed,
        candidates=tuple(final),
        summary=summary,
        mode=mode,
        provider=provider.name,
        discovery_version=DISCOVERY_VERSION,
    )


__all__ = ["DiscoveryBudget", "ReplayError", "classify_candidate", "discover_sources"]
