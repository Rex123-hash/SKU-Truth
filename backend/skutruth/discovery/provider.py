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
            )
        )
    return tuple(results)


def search_request(query: str, *, provider: str, max_results: int) -> InteractionRequest:
    """The replay descriptor for one search.

    The query and result cap are part of the key: asking for more results is a different
    interaction, and reusing a 5-result recording for a 20-result request would silently
    change ranking input.
    """
    return InteractionRequest(
        provider=provider,
        model=provider,
        endpoint=ENDPOINT,
        payload={"query": query, "max_results": max_results},
        prompt_version=QUERY_VERSION,
    )


def execute_search(
    call: SearchCall,
    *,
    provider: SearchProvider,
    store: CassetteStore,
    mode: RunMode = RunMode.REPLAY,
) -> tuple[SearchResult, ...]:
    """Run or replay one query. In `REPLAY` the provider is never touched."""
    request = search_request(call.query, provider=provider.name, max_results=call.max_results)

    live: Callable[[], object] | None = None
    if mode is RunMode.LIVE:

        def live() -> object:
            return provider.search(call)

    outcome = run_interaction(mode=mode, request=request, store=store, live_callable=live)
    return _to_results(outcome.cassette.response, query=call.query, provider=provider.name)


__all__ = [
    "ENDPOINT",
    "SearchCall",
    "SearchProvider",
    "declared_discovery_method",
    "execute_search",
    "search_request",
]
