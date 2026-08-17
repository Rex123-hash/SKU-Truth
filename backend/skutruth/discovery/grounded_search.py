"""A live `SearchProvider` backed by Vertex AI Gemini with Google Search grounding.

## Why grounding, and what it costs

The Custom Search JSON API is closed to new customers, so it is not a dependency SKUTruth
can take. Google Search grounding is, it reaches the open web, and it is the one option
whose provenance the frozen contract can state truthfully: `GOOGLE_SEARCH_GROUNDING` means
exactly this mechanism.

It costs something real, and this module does not hide it. **The model chooses the search
queries.** Google's documentation is explicit: the model "analyzes the prompt and
determines if a Google Search can improve the answer" and "automatically generates one or
multiple search queries". SKUTruth's `build_queries` therefore stops being the executed
query and becomes a *query intent* placed in a prompt.

    QUERY INTENT IS DETERMINISTIC
    SEARCH EXECUTION IS PROVIDER-GENERATED AND RECORDED

Both are kept: the intent on `DiscoveryResult.executed_queries`, and whatever Google
actually searched on `DiscoveryResult.provider_executed_queries`, read from
`groundingMetadata.webSearchQueries`. Nothing here calls the second set deterministic, and
two LIVE runs of one product may differ. `REPLAY` reproduces both exactly.

This is acceptable *only because discovery is a locator stage*. Nothing the model does can
reach a fact: it cannot decide manufacturer ownership, product identity, or any attribute
value, and every one of those gates runs unchanged downstream.

## The generated answer is discarded

A grounded call returns prose. That prose is the most dangerous thing in the response — it
is fluent, it is about the product, and it is exactly what a careless integration would
store. It is never read. This module extracts `groundingMetadata` and nothing else;
`response.text`, `groundingSupports` spans, and any summary never enter the domain layer,
and tests assert they cannot reach a `SearchResult` or an artifact.

## Redirect URIs, and the host that actually matters

`groundingChunks[].web.uri` is a `vertexaisearch.cloud.google.com/grounding-api-redirect/…`
link, not the publisher's URL. The publisher appears separately as `web.domain`, which
Google documents as usable "to filter out low-quality sources".

So `url` keeps the redirect exactly as returned, and `domain` becomes
`SearchResult.publisher_host`. Authority is looked up against the publisher host, because
looking it up against the Google host would classify every result identically.

That is a decision about **what to fetch**, never about what may be stored. The fetch
follows the redirect, and `service._acquire_one` re-decides authority on the host the
bytes actually arrived from. If Google reports `kichler.com` and the redirect lands
somewhere else, the final-host check refuses it — Google's reported domain cannot override
it, and a test proves that.

## Credentials

Application Default Credentials through the existing Vertex setup, the same as
`skutruth.extraction.vertex`. No second key ecosystem, and nothing here reads, stores, or
logs a secret.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from skutruth.contracts import DiscoveryMethod
from skutruth.extraction.config import DEFAULT_LOCATION, VertexConfig

from .errors import (
    MalformedSearchResponseError,
    SearchBudgetExceededError,
    SearchProviderError,
    SearchProviderTimeout,
    SearchProviderTransportError,
)
from .provider import SearchCall

#: Bumped when a change here could alter which candidates a query yields or how they are
#: normalised. Part of the replay key.
PROVIDER_VERSION = "vertex-search-grounding@v1"

#: Recorded in provenance and in every cassette key.
PROVIDER_NAME = "vertex-search-grounding"

#: Environment variable naming the discovery model, kept **separate from extraction**.
#: Sharing `SKUTRUTH_VERTEX_MODEL` would mean tuning discovery silently changed which
#: model reads datasheets, and those are different jobs with different requirements.
ENV_MODEL = "SKUTRUTH_DISCOVERY_MODEL"

#: A current Vertex Gemini model that supports Google Search grounding. A default, not a
#: constant to depend on: it participates in the replay key, so changing it invalidates
#: recordings rather than silently altering results.
DEFAULT_MODEL = "gemini-2.5-flash"


@dataclass(frozen=True, slots=True)
class GroundingLimits:
    """Ceilings on live grounding. There is no unbounded configuration."""

    #: Chunks kept per call. Grounding returns as many sources as it used; this caps how
    #: many become candidates so one verbose answer cannot flood the ranking.
    max_results_per_query: int = 10
    timeout_seconds: float = 30.0
    #: Bounds the whole provider instance. Per-product query budgets bound one row; a loop
    #: over organizer rows would otherwise multiply them into an unbounded billable run.
    max_calls: int = 40

    def __post_init__(self) -> None:
        if self.max_results_per_query < 1 or self.max_calls < 1 or self.timeout_seconds <= 0:
            raise ValueError("grounding limits must be positive")


@dataclass(frozen=True, slots=True)
class GroundingConfig:
    """Where to call, and with which model. Credentials are never configuration."""

    project: str
    location: str = DEFAULT_LOCATION
    model: str = DEFAULT_MODEL

    @classmethod
    def from_env(cls) -> GroundingConfig:
        """Reuse the project and location the extraction stage already requires.

        The model is read from `SKUTRUTH_DISCOVERY_MODEL` so discovery and extraction can
        be configured independently; falling back to the extraction model would make one
        setting quietly control two unrelated stages.
        """
        import os

        vertex = VertexConfig.from_env()
        return cls(
            project=vertex.project,
            location=vertex.location,
            model=os.environ.get(ENV_MODEL, "").strip() or DEFAULT_MODEL,
        )


def build_grounding_prompt(query: str) -> str:
    """The smallest prompt that turns one deterministic query intent into a search.

    Deliberately narrow. The model is asked to *locate pages*, and is told in as many
    words that it is not being asked to answer anything about the product — because every
    judgement it could offer (whose site this is, whether the reference matches, what the
    specification says) is made downstream by code, and a model opinion arriving early
    would be an unfalsifiable input to all of it.

    The query intent is passed through verbatim so what SKUTruth asked for stays visible
    in the prompt, the cassette, and the report.
    """
    return (
        "Use Google Search to find official manufacturer web pages and PDF documents "
        f"matching this search query exactly: {query}\n\n"
        "Return only a list of the sources you found. Do not describe the product, do "
        "not state any specification, and do not judge which source is authoritative. "
        "Locating the pages is the entire task; everything else is decided elsewhere."
    )


def _text_of(value: object) -> str:
    return str(value).strip() if value is not None else ""


def extract_locators(grounding_metadata: object, *, limit: int) -> tuple[list[dict], list[str]]:
    """Pull locators and executed queries out of grounding metadata. Nothing else.

    Returns `(rows, executed_queries)`. A chunk with no `uri` is skipped rather than
    repaired: a locator we invented is worse than one we did not return.

    Deduplication is on the **full URI**, not the domain. Two different documents on one
    manufacturer's site are two candidates, and collapsing them by host would silently
    discard the datasheet because the product page came first.
    """
    if grounding_metadata is None:
        return [], []

    executed = [
        text
        for raw in (getattr(grounding_metadata, "web_search_queries", None) or [])
        if (text := _text_of(raw))
    ]

    rows: list[dict] = []
    seen: set[str] = set()
    for index, chunk in enumerate(getattr(grounding_metadata, "grounding_chunks", None) or [], 1):
        web = getattr(chunk, "web", None)
        if web is None:
            continue
        uri = _text_of(getattr(web, "uri", None))
        if not uri or uri in seen:
            continue
        seen.add(uri)
        rows.append(
            {
                "url": uri,
                "title": _text_of(getattr(web, "title", None)),
                # `domain` is absent on some chunks. Left as None rather than guessed
                # from the redirect URI, which would name Google as the publisher.
                "publisher_host": _text_of(getattr(web, "domain", None)) or None,
                "rank": index,
                # No snippet: grounding returns prose about the product, and a snippet
                # field is exactly where that prose would leak into the domain layer.
                "snippet": "",
            }
        )
        if len(rows) >= limit:
            break

    return rows, executed


def search_entry_point_of(grounding_metadata: object) -> str:
    """The Search Suggestions HTML Google requires a UI to display, if present.

    Captured because using grounding obliges any eventual interface to render it. It is
    returned separately and never attached to a candidate: it is provider chrome, not a
    locator, and certainly not evidence. Nothing renders it today.
    """
    entry = getattr(grounding_metadata, "search_entry_point", None)
    return _text_of(getattr(entry, "rendered_content", None)) if entry is not None else ""


class VertexGroundedSearchProvider:
    """Live open-web discovery through Vertex Gemini with Google Search grounding.

    Satisfies the `SearchProvider` protocol. The generated answer is never read.
    """

    name = PROVIDER_NAME
    version = PROVIDER_VERSION

    #: Declared by this implementation because this is genuinely what it does — a Google
    #: Search grounding call. Never inferred from the class or provider name; a class
    #: called `google-anything` gets no say in what the audit trail records.
    discovery_method = DiscoveryMethod.GOOGLE_SEARCH_GROUNDING

    def __init__(
        self,
        config: GroundingConfig,
        *,
        limits: GroundingLimits | None = None,
        client=None,
    ) -> None:
        self.config = config
        self._limits = limits or GroundingLimits()
        self._client = client
        self._calls = 0
        #: Search Suggestions HTML from the most recent call, for a future UI obligation.
        self._last_search_entry_point = ""

    @classmethod
    def from_env(
        cls, *, limits: GroundingLimits | None = None, client=None
    ) -> VertexGroundedSearchProvider:
        return cls(GroundingConfig.from_env(), limits=limits, client=client)

    @property
    def calls_made(self) -> int:
        return self._calls

    @property
    def limits(self) -> GroundingLimits:
        return self._limits

    @property
    def last_search_entry_point(self) -> str:
        return self._last_search_entry_point

    def request_options(self) -> dict:
        """Options that change what a call returns, folded into the replay key.

        The model and result cap belong here: grounding is model-mediated, so replaying a
        recording made by one model as though another produced it would misreport the run.
        """
        return {"model": self.config.model, "max_results": self._limits.max_results_per_query}

    def _ensure_client(self):
        if self._client is None:
            from google import genai  # imported lazily; absent in offline test runs

            self._client = genai.Client(
                vertexai=True, project=self.config.project, location=self.config.location
            )
        return self._client

    def search(self, call: SearchCall) -> list[dict]:
        """Run one grounded search. Returns locator rows; the answer text is dropped."""
        if self._calls >= self._limits.max_calls:
            raise SearchBudgetExceededError(
                f"live grounding budget of {self._limits.max_calls} provider calls is spent"
            )
        query = call.query.strip()
        if not query:
            raise MalformedSearchResponseError("refusing to search for an empty query")

        from google.genai import types

        client = self._ensure_client()
        limit = min(call.max_results, self._limits.max_results_per_query)

        self._calls += 1
        try:
            response = client.models.generate_content(
                model=self.config.model,
                contents=build_grounding_prompt(query),
                config=types.GenerateContentConfig(
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                    # The answer is discarded, so sampling it differently changes nothing
                    # we keep. Pinned anyway so a recording is as reproducible as the
                    # provider permits.
                    temperature=0.0,
                    http_options=types.HttpOptions(
                        timeout=int(self._limits.timeout_seconds * 1000)
                    ),
                ),
            )
        except TimeoutError:
            raise SearchProviderTimeout(
                f"grounded search did not respond within {self._limits.timeout_seconds:g}s"
            ) from None
        except Exception as exc:  # noqa: BLE001 - mapped to a typed provider failure
            raise _as_provider_error(exc) from None

        metadata = _grounding_metadata_of(response)
        rows, executed = extract_locators(metadata, limit=limit)
        self._last_search_entry_point = search_entry_point_of(metadata)

        # `executed` rides on the first row so it survives the cassette without a second
        # interaction. `provider.execute_search` lifts it back out; `_to_results` ignores
        # unknown keys, so it can never reach a `SearchResult`.
        if rows:
            rows[0] = {**rows[0], "_provider_executed_queries": executed}
        elif executed:
            rows = [{"_provider_executed_queries": executed}]
        return rows


def _grounding_metadata_of(response: object):
    """The first candidate's grounding metadata, or `None`.

    Only this branch of the response is ever read. `response.text` is deliberately not
    touched — not logged, not stored, not inspected — because it is model prose about the
    product and this package's whole premise is that such prose is not evidence.
    """
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        metadata = getattr(candidate, "grounding_metadata", None)
        if metadata is not None:
            return metadata
    return None


def _as_provider_error(exc: Exception) -> SearchProviderError:
    """Map an SDK exception onto a typed failure without echoing its text.

    SDK errors can carry request URLs and headers. The class name and any HTTP status are
    enough to act on, and are all that is propagated.
    """
    name = type(exc).__name__
    if "Timeout" in name or "DeadlineExceeded" in name:
        return SearchProviderTimeout(f"grounded search timed out ({name})")
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(status, int):
        from .errors import SearchProviderHTTPError

        return SearchProviderHTTPError(status, f"grounded search failed ({name})")
    return SearchProviderTransportError(f"could not reach Vertex for grounded search ({name})")


def with_limits(
    provider: VertexGroundedSearchProvider, **changes: object
) -> VertexGroundedSearchProvider:  # pragma: no cover - convenience for scripts
    """A copy with adjusted limits and a fresh call budget."""
    return VertexGroundedSearchProvider(
        provider.config,
        limits=replace(provider.limits, **changes),  # type: ignore[arg-type]
    )


def provider_executed_queries(rows: Sequence[dict]) -> tuple[str, ...]:
    """Lift the recorded provider queries back out of a normalised payload."""
    for row in rows:
        if isinstance(row, dict) and row.get("_provider_executed_queries"):
            return tuple(str(q) for q in row["_provider_executed_queries"])
    return ()


__all__ = [
    "DEFAULT_MODEL",
    "ENV_MODEL",
    "PROVIDER_NAME",
    "PROVIDER_VERSION",
    "GroundingConfig",
    "GroundingLimits",
    "VertexGroundedSearchProvider",
    "build_grounding_prompt",
    "extract_locators",
    "provider_executed_queries",
    "search_entry_point_of",
]
