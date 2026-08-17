"""The search-provider boundary, and its record/replay wrapper.

Business logic never imports a search SDK. It calls a `SearchProvider`, satisfied by a
real engine in production and by a deterministic fake in tests — so the whole committed
suite runs offline, and swapping engines cannot change what a candidate *means*, only
which candidates turn up.

## Replay reuses the existing runner

Discovery does not get its own recording machinery. `skutruth.replay` already provides
versioned cassette keys, credential redaction before key derivation, and a `REPLAY` mode
that cannot reach the network — including on a miss, where it raises rather than falling
back. Search is just another external interaction, so it goes through the same door.

That gives one property worth stating plainly: **a `REPLAY` discovery run makes no
network call of any kind.** Not on a miss, not on a malformed cassette. A run that
quietly reached the internet would invalidate every measurement taken from it.

## Credentials

An API key belongs to the live callable and to nothing else. It is never part of the
interaction descriptor, so it cannot enter a cassette key or a stored recording, and
redaction runs over the payload anyway as a second line of defence.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

from skutruth.contracts import DiscoveryMethod, RunMode
from skutruth.replay.models import InteractionRequest
from skutruth.replay.runner import run_interaction
from skutruth.replay.store import CassetteStore

from .models import SearchResult
from .query import QUERY_VERSION

#: Recorded on the interaction descriptor so a recording made against one engine is
#: never replayed as though it came from another.
ENDPOINT = "search"


@dataclass(frozen=True, slots=True)
class SearchCall:
    """Everything a provider needs for one query."""

    query: str
    max_results: int = 10


class SearchProvider(Protocol):
    """One query in, results out. Deliberately almost the entire interface.

    The one addition is `discovery_method`, and it is not decoration. A stored artifact
    records *how it was found*, and only the provider knows that. Inferring it from the
    provider's name would mean a class calling itself `google-search` could mint
    `GOOGLE_SEARCH_GROUNDING` provenance for results that never went near Google —
    branding deciding what the audit trail says.

    `None` is a legitimate answer: it means the frozen `DiscoveryMethod` has no value that
    truthfully describes this provider. Acquisition then refuses rather than defaulting,
    because `SourceMetadata.discovery_method` is non-optional and every available default
    would assert something untrue.

    Two further attributes are read when present and are deliberately *not* declared
    here, so a minimal provider stays valid without them: `version`, a behaviour version
    folded into the replay key, and `request_options`, a mapping (or a callable
    returning one) of settings that change what a query returns. Both are read through
    the helpers below.
    """

    #: Stable identifier recorded in provenance, e.g. `"fake"`, `"programmable-search"`.
    name: str

    #: How this provider finds candidates, in the frozen contract's own vocabulary.
    discovery_method: DiscoveryMethod | None

    def search(self, call: SearchCall) -> list[dict]:  # pragma: no cover - protocol
        """Return raw result dicts with at least `url`; `title` and `snippet` optional."""
        ...


def declared_discovery_method(provider: SearchProvider) -> DiscoveryMethod | None:
    """What the provider says about its own discovery mechanism.

    Read through a helper so a provider written before this attribute existed reports
    `None` — unable to state its provenance — rather than silently inheriting whatever
    default happened to be nearby.
    """
    return getattr(provider, "discovery_method", None)


def declared_version(provider: SearchProvider) -> str | None:
    """The provider's own behaviour version, if it declares one.

    Part of the replay key. Two providers can answer the same query differently, and so
    can one provider before and after a change to how it builds requests or normalises
    results — replaying the older recording as though the newer code produced it would
    misreport what the run actually saw.

    `None` for a provider that declares nothing, which keeps every cassette recorded
    before this existed valid: an absent version is omitted from the descriptor rather
    than written as a null.
    """
    version = getattr(provider, "version", None)
    return str(version) if version else None


def declared_request_options(provider: SearchProvider) -> dict:
    """Provider options that change what a query returns, for the replay key.

    Anything affecting results but not already keyed — a language restriction, a file
    type filter — belongs here, so it cannot be changed without invalidating recordings
    made under the old setting. Empty is omitted from the descriptor entirely, so a
    provider with no options keys exactly as it did before this existed.
    """
    options = getattr(provider, "request_options", None)
    if callable(options):
        options = options()
    return dict(options) if options else {}


def _to_results(payload: object, *, query: str, provider: str) -> tuple[SearchResult, ...]:
    """Normalise a provider payload. Anything without a URL is dropped, not guessed at."""
    rows = payload if isinstance(payload, list) else []
    results: list[SearchResult] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            continue
        url = str(row.get("url") or "").strip()
        if not url:
            continue
        results.append(
            SearchResult(
                url=url,
                title=str(row.get("title") or "").strip(),
                snippet=str(row.get("snippet") or "").strip(),
                rank=int(row.get("rank") or index),
                query=query,
                provider=provider,
                # Only providers that return a redirect report this. Every unrecognised
                # key in `row` is ignored here, which is what keeps provider-specific
                # payload fields — including recorded provider queries — out of the
                # domain layer.
                publisher_host=(str(row.get("publisher_host") or "").strip() or None),
            )
        )
    return tuple(results)


def _provider_queries(payload: object) -> tuple[str, ...]:
    """Queries the provider reported executing, if it reported any.

    Carried inside the recorded payload rather than as a second interaction, so a replayed
    run reproduces the provider's own queries as exactly as it reproduces the results.
    """
    rows = payload if isinstance(payload, list) else []
    for row in rows:
        if not isinstance(row, dict):
            continue
        recorded = row.get("_provider_executed_queries")
        if recorded:
            return tuple(str(q).strip() for q in recorded if str(q).strip())
    return ()


def search_request(
    query: str,
    *,
    provider: str,
    max_results: int,
    version: str | None = None,
    options: dict | None = None,
) -> InteractionRequest:
    """The replay descriptor for one search.

    The query and result cap are part of the key: asking for more results is a different
    interaction, and reusing a 5-result recording for a 20-result request would silently
    change ranking input. `version` and `options` extend that to the provider's own
    behaviour, so a recording cannot outlive the code that produced it.

    An absent version and empty options are omitted rather than keyed as nulls, which
    keeps recordings made before those fields existed replayable.
    """
    payload: dict = {"query": query, "max_results": max_results}
    if options:
        payload["options"] = options
    return InteractionRequest(
        provider=provider,
        model=provider,
        endpoint=ENDPOINT,
        payload=payload,
        prompt_version=QUERY_VERSION,
        stage_version=version,
    )


def execute_search(
    call: SearchCall,
    *,
    provider: SearchProvider,
    store: CassetteStore,
    mode: RunMode = RunMode.REPLAY,
) -> tuple[SearchResult, ...]:
    """Run or replay one query. In `REPLAY` the provider is never touched."""
    request = search_request(
        call.query,
        provider=provider.name,
        max_results=call.max_results,
        version=declared_version(provider),
        options=declared_request_options(provider),
    )

    live: Callable[[], object] | None = None
    if mode is RunMode.LIVE:

        def live() -> object:
            return provider.search(call)

    outcome = run_interaction(mode=mode, request=request, store=store, live_callable=live)
    return _to_results(outcome.cassette.response, query=call.query, provider=provider.name)


@dataclass(frozen=True, slots=True)
class SearchExecution:
    """One query's results, plus what the provider says it actually searched.

    The two are separate because for a grounded provider they genuinely are: we supply a
    deterministic intent, and the provider generates its own queries from it. Reporting
    only one would either hide our intent or claim the provider ran it verbatim.
    """

    results: tuple[SearchResult, ...]
    #: From the provider's own metadata. Empty when it runs the query it was handed.
    provider_queries: tuple[str, ...] = ()


def execute_search_with_provenance(
    call: SearchCall,
    *,
    provider: SearchProvider,
    store: CassetteStore,
    mode: RunMode = RunMode.REPLAY,
) -> SearchExecution:
    """Run or replay one query, keeping the provider's own query metadata."""
    request = search_request(
        call.query,
        provider=provider.name,
        max_results=call.max_results,
        version=declared_version(provider),
        options=declared_request_options(provider),
    )

    live: Callable[[], object] | None = None
    if mode is RunMode.LIVE:

        def live() -> object:
            return provider.search(call)

    outcome = run_interaction(mode=mode, request=request, store=store, live_callable=live)
    payload = outcome.cassette.response
    return SearchExecution(
        results=_to_results(payload, query=call.query, provider=provider.name),
        provider_queries=_provider_queries(payload),
    )


__all__ = [
    "ENDPOINT",
    "SearchCall",
    "SearchExecution",
    "SearchProvider",
    "declared_discovery_method",
    "declared_request_options",
    "declared_version",
    "execute_search",
    "execute_search_with_provenance",
    "search_request",
]
