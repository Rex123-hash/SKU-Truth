"""A live `SearchProvider` backed by Agent Search basic website search.

## Why this and not Google Search grounding

Grounding was implemented first and removed. Its terms state that Grounded Results,
Search Suggestions, and Links "are intended to be used in combination to respond to a
given End User prompt", and prohibit "using programmatic or automated means to collect
Links, using Links to build an index, or using Links to identify destination pages for
crawling or scraping". SKUTruth does exactly those three things: it collects links
programmatically, records them as candidates, and fetches the pages they name. Grounding
is therefore not available to this pipeline — a terms question, not a technical one.

Agent Search basic website search is Google's documented migration path from the
site-restricted Custom Search API, and it fits this package far better anyway:

* **the caller's query is executed verbatim** — no model rewrites it, so `build_queries`
  is once again the query, not an intent handed to something that might reinterpret it;
* **results carry the publisher's real URL** in `derivedStructData.link`, so exact-MPN
  relevance has a URL to match against and the authority gate needs no redirect
  workaround;
* **no generative feature is involved.** No summaries, no `answer`, no follow-ups, no
  extractive generation. Conventional search results only, which is the whole point:
  discovery is deterministic again, and no module in this package imports a model client.

## Basic website search, deliberately

Advanced website indexing is **off**, and the provisioning helper refuses to turn it on.
Advanced indexing requires domain verification, which we cannot perform for manufacturers'
sites — Google's own guidance is to disable it when "you don't own the domains that you
specify". Basic search reads Google's existing index instead, and needs no such claim.

## The corpus is the reviewed set, and only the reviewed set

A domain enters the search corpus *after* a human has reviewed it, never before. That
ordering is the point: Agent Search cannot be used to decide that a domain is
trustworthy, because a domain only becomes searchable once someone already decided that.
`included_patterns_for` builds the pattern list exclusively from registry entries that
carry a `DomainReview`, and refuses to exceed the documented 50-pattern ceiling.

## Credentials

Application Default Credentials against the existing GCP project, the same as the
extraction stage. No API keys; resource ids come from the environment.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace

from skutruth.contracts import DiscoveryMethod

from .domains import DomainRegistry
from .errors import (
    DiscoveryError,
    MalformedSearchResponseError,
    SearchBudgetExceededError,
    SearchProviderError,
    SearchProviderHTTPError,
    SearchProviderTimeout,
    SearchProviderTransportError,
)
from .provider import SearchCall

#: Bumped when a change here could alter which results a query yields or how they are
#: normalised. Part of the replay key.
PROVIDER_VERSION = "agent-search-basic@v1"

#: Recorded in provenance and in every cassette key.
PROVIDER_NAME = "agent-search"

ENV_ENGINE_ID = "SKUTRUTH_AGENT_SEARCH_ENGINE_ID"
ENV_LOCATION = "SKUTRUTH_AGENT_SEARCH_LOCATION"
ENV_SERVING_CONFIG = "SKUTRUTH_AGENT_SEARCH_SERVING_CONFIG"

#: Website data stores are global unless deliberately regionalised.
DEFAULT_LOCATION = "global"
DEFAULT_SERVING_CONFIG = "default_search"

#: Documented ceiling for **basic** website search. Advanced indexing allows 500, and is
#: not available to us: it requires verifying domains we do not own.
MAX_INCLUDED_PATTERNS = 50


#: Distinguishes "attribute absent" from "attribute present but empty".
_MISSING = object()


class AgentSearchConfigError(DiscoveryError):
    """Agent Search resources are not configured, or are configured impossibly."""


@dataclass(frozen=True, slots=True)
class AgentSearchConfig:
    """Which provisioned Agent Search app to query. Never creates anything.

    SKUTruth expects the app and data store to exist already. A runtime that silently
    provisioned cloud resources would create billable infrastructure as a side effect of
    a search, and would make the corpus depend on whichever run happened to go first.
    `scripts/setup_agent_search.py` is the explicit, separate path for that.
    """

    project: str
    engine_id: str
    location: str = DEFAULT_LOCATION
    serving_config: str = DEFAULT_SERVING_CONFIG

    @classmethod
    def from_env(cls) -> AgentSearchConfig:
        """Read resource ids, refusing rather than guessing.

        The project comes from the same variable the extraction stage already requires,
        so one GCP project serves the whole system.
        """
        from skutruth.extraction.config import ENV_PROJECT

        project = os.environ.get(ENV_PROJECT, "").strip()
        engine = os.environ.get(ENV_ENGINE_ID, "").strip()
        missing = [n for n, v in ((ENV_PROJECT, project), (ENV_ENGINE_ID, engine)) if not v]
        if missing:
            raise AgentSearchConfigError(
                f"Agent Search needs {' and '.join(missing)} in the environment. "
                f"Create a website data store with advanced indexing OFF and a search "
                f"app over it, then set the app id; see scripts/setup_agent_search.py."
            )
        return cls(
            project=project,
            engine_id=engine,
            location=os.environ.get(ENV_LOCATION, "").strip() or DEFAULT_LOCATION,
            serving_config=(
                os.environ.get(ENV_SERVING_CONFIG, "").strip() or DEFAULT_SERVING_CONFIG
            ),
        )

    @property
    def serving_config_path(self) -> str:
        """The fully-qualified serving config the search method addresses."""
        return (
            f"projects/{self.project}/locations/{self.location}"
            f"/collections/default_collection/engines/{self.engine_id}"
            f"/servingConfigs/{self.serving_config}"
        )


@dataclass(frozen=True, slots=True)
class AgentSearchLimits:
    """Bounded work. There is no unlimited configuration."""

    max_results_per_query: int = 10
    timeout_seconds: float = 20.0
    #: Bounds the whole provider instance, not one product.
    max_calls: int = 40

    def __post_init__(self) -> None:
        if self.max_results_per_query < 1 or self.max_calls < 1 or self.timeout_seconds <= 0:
            raise ValueError("Agent Search limits must be positive")


def included_patterns_for(registry: DomainRegistry) -> tuple[str, ...]:
    """URL patterns for the reviewed manufacturer domains, and nothing else.

    Reads `licensing_entries`, so a domain enters the search corpus only once a human has
    recorded a `DomainReview` for its entry. An unreviewed domain stays out — it can still
    be *located* by other means, but it is not part of the corpus SKUTruth searches for
    evidence, and no provider output can add one.

    Raises rather than truncating past the documented ceiling. Silently dropping the
    fifty-first pattern would mean a reviewed manufacturer was quietly unsearchable, and
    the run would report "no results" for a domain the operator believed was configured.
    """
    patterns = tuple(
        f"{domain}/*" for entry in registry.licensing_entries for domain in entry.domains
    )
    if len(patterns) > MAX_INCLUDED_PATTERNS:
        raise AgentSearchConfigError(
            f"{len(patterns)} URL patterns exceeds the {MAX_INCLUDED_PATTERNS}-pattern "
            f"limit of basic website search. Split the reviewed domains across more than "
            f"one data store; nothing here may silently drop one."
        )
    return patterns


def build_filter(*, site_patterns: tuple[str, ...] = (), pdf_only: bool = False) -> str:
    """A basic-website-search filter expression.

    Basic search supports `siteSearch` and `fileType` (among others); advanced indexing
    does not offer `fileType`, which is one more reason basic suits this use. Expressed
    as a filter rather than smuggled into the query string, so the query stays exactly
    the reference we are looking for.
    """
    clauses: list[str] = []
    if site_patterns:
        sites = " OR ".join(f'siteSearch:"{p}"' for p in site_patterns)
        clauses.append(f"({sites})" if len(site_patterns) > 1 else sites)
    if pdf_only:
        clauses.append('fileType:".pdf"')
    return " AND ".join(clauses)


def _struct_get(struct: object, key: str) -> object:
    """Read a key from a protobuf Struct or a plain dict, whichever the SDK returns."""
    if struct is None:
        return None
    if isinstance(struct, dict):
        return struct.get(key)
    try:
        return struct[key]  # type: ignore[index]
    except (KeyError, TypeError, IndexError):
        return getattr(struct, key, None)


def _text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _first_snippet(derived: object) -> str:
    """The first snippet, as locator metadata only.

    Retained so a reviewer can see what the index matched. It never reaches the
    exact-MPN gate — `classify_relevance` reads the URL and title and deliberately not
    this — and it can never become evidence.
    """
    snippets = _struct_get(derived, "snippets")
    if not snippets:
        return ""
    try:
        first = snippets[0]  # type: ignore[index]
    except (IndexError, TypeError, KeyError):
        return ""
    return _text(_struct_get(first, "snippet"))


def normalize_results(results: object, *, limit: int) -> list[dict]:
    """Map Agent Search results onto the shape `execute_search` expects.

    A result with no `link` is skipped rather than repaired: the URL is the one thing a
    locator must report faithfully, and there is nothing to reconstruct it from.
    """
    rows: list[dict] = []
    for index, result in enumerate(results or [], start=1):
        document = getattr(result, "document", None)
        if document is None and isinstance(result, dict):
            document = result.get("document")
        derived = getattr(document, "derived_struct_data", None)
        if derived is None:
            derived = _struct_get(document, "derivedStructData")

        url = _text(_struct_get(derived, "link"))
        if not url:
            continue
        rows.append(
            {
                "url": url,
                "title": _text(_struct_get(derived, "title")),
                "snippet": _first_snippet(derived),
                "rank": index,
                # publisher_host stays absent: `link` is already the publisher's own URL,
                # so the ordinary `host_of(url)` path applies and nothing is special-cased.
            }
        )
        if len(rows) >= limit:
            break
    return rows


class AgentSearchProvider:
    """Site-restricted keyword search over reviewed manufacturer domains.

    No model, no prompt, no generated text. The query it is handed is the query it runs.
    """

    name = PROVIDER_NAME
    version = PROVIDER_VERSION

    #: Truthful for this mechanism: a keyword search restricted to configured sites,
    #: returning publishers' own URLs. Declared by the implementation, never inferred
    #: from the class or provider name.
    discovery_method = DiscoveryMethod.SITE_RESTRICTED_SEARCH

    def __init__(
        self,
        config: AgentSearchConfig,
        *,
        limits: AgentSearchLimits | None = None,
        site_patterns: tuple[str, ...] = (),
        pdf_only: bool = False,
        client=None,
    ) -> None:
        self.config = config
        self._limits = limits or AgentSearchLimits()
        self._site_patterns = site_patterns
        self._pdf_only = pdf_only
        self._client = client
        self._calls = 0

    @classmethod
    def from_env(
        cls,
        *,
        limits: AgentSearchLimits | None = None,
        site_patterns: tuple[str, ...] = (),
        pdf_only: bool = False,
        client=None,
    ) -> AgentSearchProvider:
        return cls(
            AgentSearchConfig.from_env(),
            limits=limits,
            site_patterns=site_patterns,
            pdf_only=pdf_only,
            client=client,
        )

    def for_pdfs(self, *, pdf_only: bool = True) -> AgentSearchProvider:
        """A sibling provider differing only in the file-type filter.

        A separate instance rather than a mutable flag, because the filter is part of the
        replay key: flipping it mid-run would silently reuse a recording made under the
        other setting.
        """
        return AgentSearchProvider(
            self.config,
            limits=self._limits,
            site_patterns=self._site_patterns,
            pdf_only=pdf_only,
            client=self._client,
        )

    @property
    def calls_made(self) -> int:
        return self._calls

    @property
    def limits(self) -> AgentSearchLimits:
        return self._limits

    @property
    def site_patterns(self) -> tuple[str, ...]:
        return self._site_patterns

    def request_options(self) -> dict:
        """Everything that changes what a query returns, folded into the replay key.

        The engine and the filters belong here: the same query against a different corpus
        or with the PDF filter flipped is a different interaction, and replaying one as
        the other would misreport what the run saw.
        """
        return {
            "engine": self.config.engine_id,
            "location": self.config.location,
            "serving_config": self.config.serving_config,
            "filter": self.filter_expression(),
        }

    def filter_expression(self) -> str:
        return build_filter(site_patterns=self._site_patterns, pdf_only=self._pdf_only)

    def _ensure_client(self):
        if self._client is None:
            # Imported lazily so the offline suite runs without the SDK installed.
            from google.cloud import discoveryengine_v1 as discoveryengine

            self._client = discoveryengine.SearchServiceClient()
        return self._client

    def search(self, call: SearchCall) -> list[dict]:
        """Run one query, exactly as given. Returns locator rows."""
        if self._calls >= self._limits.max_calls:
            raise SearchBudgetExceededError(
                f"Agent Search budget of {self._limits.max_calls} provider calls is spent"
            )
        query = call.query.strip()
        if not query:
            raise MalformedSearchResponseError("refusing to search for an empty query")

        from google.cloud import discoveryengine_v1 as discoveryengine

        client = self._ensure_client()
        limit = min(call.max_results, self._limits.max_results_per_query)

        request = discoveryengine.SearchRequest(
            serving_config=self.config.serving_config_path,
            # Verbatim. Nothing rewrites, expands, or normalises the reference.
            query=query,
            page_size=limit,
            filter=self.filter_expression(),
        )

        self._calls += 1
        try:
            response = client.search(request=request, timeout=self._limits.timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - mapped to a typed provider failure
            raise _as_provider_error(exc) from None

        # `or response` would be wrong here: an empty `results` is falsy, and falling
        # through to the response object turns "no matches" into a TypeError. A search
        # that legitimately found nothing must return nothing.
        results = getattr(response, "results", _MISSING)
        return normalize_results(response if results is _MISSING else results, limit=limit)


def _as_provider_error(exc: Exception) -> SearchProviderError:
    """Map an SDK exception onto a typed failure without echoing its text.

    Client exceptions can carry request URLs and resource paths. The class name and any
    status code are enough to act on, and are all that is propagated.
    """
    name = type(exc).__name__
    if "Timeout" in name or "DeadlineExceeded" in name:
        return SearchProviderTimeout(f"Agent Search timed out ({name})")
    status = getattr(exc, "code", None)
    status = status() if callable(status) else status
    if isinstance(status, int):
        return SearchProviderHTTPError(status, f"Agent Search failed ({name})")
    return SearchProviderTransportError(f"could not reach Agent Search ({name})")


def with_limits(
    provider: AgentSearchProvider, **changes: object
) -> AgentSearchProvider:  # pragma: no cover - convenience for scripts
    """A copy with adjusted limits and a fresh call budget."""
    return AgentSearchProvider(
        provider.config,
        limits=replace(provider.limits, **changes),  # type: ignore[arg-type]
        site_patterns=provider.site_patterns,
    )


__all__ = [
    "DEFAULT_LOCATION",
    "DEFAULT_SERVING_CONFIG",
    "ENV_ENGINE_ID",
    "ENV_LOCATION",
    "ENV_SERVING_CONFIG",
    "MAX_INCLUDED_PATTERNS",
    "PROVIDER_NAME",
    "PROVIDER_VERSION",
    "AgentSearchConfig",
    "AgentSearchConfigError",
    "AgentSearchLimits",
    "AgentSearchProvider",
    "build_filter",
    "included_patterns_for",
    "normalize_results",
]
