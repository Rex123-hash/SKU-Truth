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

from .domains import DomainRegistry, normalize_host
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
#:
#: This bounds the **data store corpus** — how many reviewed domains the app can search at
#: all. It is unrelated to `MAX_RESULTS_PER_QUERY`, which bounds one response.
MAX_INCLUDED_PATTERNS = 50

#: Documented `pageSize` ceiling for basic website search (default 10). Advanced indexing
#: allows 50; other data types 100. The API coerces larger values down silently, so this
#: is validated here — a run that asked for 100 and quietly received 25 would misreport
#: how much of the result set it actually considered.
MAX_RESULTS_PER_QUERY = 25


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

    #: Basic website search documents a default of 10 and a maximum of 25.
    max_results_per_query: int = 10
    timeout_seconds: float = 20.0
    #: Bounds the whole provider instance, not one product. A manufacturer with several
    #: reviewed domains costs one call per domain per query, so this is what stops a
    #: fan-out from multiplying quietly.
    max_calls: int = 40

    def __post_init__(self) -> None:
        if self.max_calls < 1 or self.timeout_seconds <= 0:
            raise ValueError("Agent Search limits must be positive")
        if not 1 <= self.max_results_per_query <= MAX_RESULTS_PER_QUERY:
            # Refused rather than clamped. The API coerces an over-large page size down
            # without saying so, and a run that believed it saw 100 results when it saw
            # 25 would draw conclusions from a truncated set it did not know was truncated.
            raise ValueError(
                f"max_results_per_query must be 1..{MAX_RESULTS_PER_QUERY} for basic "
                f"website search; got {self.max_results_per_query}"
            )


def site_pattern_for(domain: str) -> str:
    """The documented `siteSearch` pattern form for one domain.

    Google's examples are full URLs with a wildcard —
    `siteSearch:"https://example.com/subdomains/*"` — not bare hostnames, so the scheme
    is included. Built in one place so every caller agrees on the format.
    """
    host = normalize_host(domain)
    if not host:
        raise AgentSearchConfigError(f"cannot build a site pattern from {domain!r}")
    return f"https://{host}/*"


def included_patterns_for(registry: DomainRegistry) -> tuple[str, ...]:
    """Corpus patterns: every reviewed manufacturer domain, for the **data store**.

    This is what the Agent Search app is allowed to search at all. It is *not* the filter
    for any single query — see `reviewed_patterns_for_hint`, which narrows a request to
    the manufacturer it is actually about. Conflating the two would search every reviewed
    manufacturer's site for every part number.

    Reads `licensing_entries`, so a domain enters the corpus only once a human has
    recorded a `DomainReview`. No provider output can add one.

    Raises rather than truncating past the documented ceiling. Silently dropping the
    fifty-first pattern would mean a reviewed manufacturer was quietly unsearchable, and
    the run would report "no results" for a domain the operator believed was configured.
    """
    patterns = tuple(
        site_pattern_for(domain)
        for entry in registry.licensing_entries
        for domain in entry.domains
    )
    if len(patterns) > MAX_INCLUDED_PATTERNS:
        raise AgentSearchConfigError(
            f"{len(patterns)} URL patterns exceeds the {MAX_INCLUDED_PATTERNS}-pattern "
            f"limit of basic website search. Split the reviewed domains across more than "
            f"one data store; nothing here may silently drop one."
        )
    return patterns


def reviewed_patterns_for_hint(
    registry: DomainRegistry, manufacturer_hint: str | None
) -> tuple[str, ...]:
    """Query-time site patterns for *this row's* manufacturer. Empty when unreviewed.

    Two conditions, both required. The hint must identify the manufacturer under a
    reviewed **authority** hint — a locator-only spelling grants nothing — and that
    entry's binding must carry a `DomainReview`.

    Empty is the answer that matters: it means no Agent Search call should be made for
    this row at all. Searching the whole app and relying on the authority gate to sort it
    out afterwards would spend calls on other manufacturers' sites and invite a
    near-miss host to be considered in the first place.
    """
    entry = registry.entry_for_hint(manufacturer_hint)
    if entry is None or not registry.licenses(entry):
        return ()
    return tuple(site_pattern_for(domain) for domain in entry.domains)


def build_filter(*, site_pattern: str | None = None, pdf_only: bool = False) -> str:
    """A **basic** website-search filter expression.

    Basic search's documented grammar is `filter = expression, { "AND", expression }`.
    There is no `OR`: using one returns *"Unsupported expression type in filter. Supported
    expression types are: (1) expression without logical joiner. (2) expressions joint by
    AND"*, because `OR` belongs to the advanced-indexing grammar and advanced indexing is
    deliberately off here.

    So this takes **one** site pattern, not a list. A manufacturer with several reviewed
    domains is searched with one bounded request per domain and the results merged — see
    `AgentSearchProvider.search`. Accepting a list here would make an invalid filter
    expressible, and the failure would surface as a backend parse error at run time
    rather than as a type error while writing the call.
    """
    clauses: list[str] = []
    if site_pattern:
        clauses.append(f'siteSearch:"{site_pattern}"')
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

    def replace(self, **changes) -> AgentSearchProvider:
        """A sibling provider with some settings changed and the rest carried over.

        One place where copies are made, so a new search-semantic setting cannot be
        forgotten by one helper and preserved by another — which is exactly the bug an
        earlier `with_limits` had, silently dropping the PDF filter.
        """
        fields = {
            "config": self.config,
            "limits": self._limits,
            "site_patterns": self._site_patterns,
            "pdf_only": self._pdf_only,
            "client": self._client,
        }
        fields.update(changes)
        config = fields.pop("config")
        return AgentSearchProvider(config, **fields)

    def for_pdfs(self, *, pdf_only: bool = True) -> AgentSearchProvider:
        """A sibling provider differing only in the file-type filter.

        A separate instance rather than a mutable flag, because the filter is part of the
        replay key: flipping it mid-run would silently reuse a recording made under the
        other setting.
        """
        return self.replace(pdf_only=pdf_only)

    def for_manufacturer(self, site_patterns: tuple[str, ...]) -> AgentSearchProvider:
        """A sibling restricted to one manufacturer's reviewed domains."""
        return self.replace(site_patterns=site_patterns)

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

        The engine and every filter belong here: the same query against a different
        corpus, a different manufacturer's domains, or with the PDF filter flipped is a
        different interaction, and replaying one as the other would misreport the run.
        """
        return {
            "engine": self.config.engine_id,
            "location": self.config.location,
            "serving_config": self.config.serving_config,
            "filters": list(self.filter_expressions()),
        }

    def filter_expressions(self) -> tuple[str, ...]:
        """One filter per reviewed domain — never one filter joining them with `OR`.

        Basic website search cannot parse `OR`, so several domains mean several requests.
        """
        if not self._site_patterns:
            return (build_filter(pdf_only=self._pdf_only),)
        return tuple(
            build_filter(site_pattern=pattern, pdf_only=self._pdf_only)
            for pattern in self._site_patterns
        )

    def filter_expression(self) -> str:
        """The single filter, for the ordinary one-domain case.

        Raises for a multi-domain provider rather than joining with `OR`: there is no
        single valid expression to return, and inventing one would produce a filter the
        backend refuses.
        """
        expressions = self.filter_expressions()
        if len(expressions) > 1:
            raise AgentSearchConfigError(
                f"{len(expressions)} reviewed domains cannot share one basic-search "
                f"filter; use filter_expressions() and issue one request each"
            )
        return expressions[0]

    def _ensure_client(self):
        if self._client is None:
            # Imported lazily so the offline suite runs without the SDK installed.
            from google.cloud import discoveryengine_v1 as discoveryengine

            self._client = discoveryengine.SearchServiceClient()
        return self._client

    def search(self, call: SearchCall) -> list[dict]:
        """Run this query against each reviewed domain, and merge the results.

        One request per domain, because basic website search cannot express
        `siteSearch:A OR siteSearch:B`. The fan-out is bounded by `max_calls`, and every
        request counts — a manufacturer with two reviewed domains costs two calls.

        Merging is deterministic: domains in configured order, results in the provider's
        order within each, first sighting of a URL wins. Rank stays the position *within
        its own query*, which is what the provider actually reported; there is no
        synthetic global score, and `ranking.py` orders candidates by its own tiers
        afterwards regardless.

        `call.max_results` is a **logical total**, so the merged list is capped at it —
        two domains do not silently return twice what the caller asked for. The cap is
        applied *after* deduplication, so a document both domains return does not consume
        two of the caller's slots.

        Every configured domain is queried before the cap is applied, rather than
        stopping once the quota is full. Stopping early would mean the second domain was
        never searched, so whether a document was found would depend on how many results
        the first domain happened to return — and `makita.com` would be invisible
        whenever `makitatools.com` was talkative. Every physical request counts against
        `max_calls`, which is what bounds the cost of that choice.
        """
        query = call.query.strip()
        if not query:
            raise MalformedSearchResponseError("refusing to search for an empty query")

        limit = min(call.max_results, self._limits.max_results_per_query)
        merged: list[dict] = []
        seen: set[str] = set()

        for expression in self.filter_expressions():
            for row in self._search_once(query, expression, limit):
                if row["url"] in seen:
                    continue
                seen.add(row["url"])
                merged.append(row)
        return merged[:limit]

    def _search_once(self, query: str, filter_expression: str, limit: int) -> list[dict]:
        """One request, against one site restriction."""
        if self._calls >= self._limits.max_calls:
            raise SearchBudgetExceededError(
                f"Agent Search budget of {self._limits.max_calls} provider calls is spent"
            )

        from google.cloud import discoveryengine_v1 as discoveryengine

        client = self._ensure_client()
        request = discoveryengine.SearchRequest(
            serving_config=self.config.serving_config_path,
            # Verbatim. Nothing rewrites, expands, or normalises the reference.
            query=query,
            page_size=limit,
            filter=filter_expression,
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


def with_limits(provider: AgentSearchProvider, **changes: object) -> AgentSearchProvider:
    """A copy with adjusted limits and a fresh call budget.

    Goes through `replace`, so every other search-semantic setting is carried over. An
    earlier version rebuilt the provider field by field and dropped `pdf_only`, which
    meant `provider.for_pdfs()` followed by `with_limits(...)` silently searched without
    the PDF filter — a regression test now covers exactly that sequence.
    """
    return provider.replace(limits=replace(provider.limits, **changes))  # type: ignore[arg-type]


__all__ = [
    "DEFAULT_LOCATION",
    "DEFAULT_SERVING_CONFIG",
    "ENV_ENGINE_ID",
    "ENV_LOCATION",
    "ENV_SERVING_CONFIG",
    "MAX_INCLUDED_PATTERNS",
    "MAX_RESULTS_PER_QUERY",
    "PROVIDER_NAME",
    "PROVIDER_VERSION",
    "AgentSearchConfig",
    "AgentSearchConfigError",
    "AgentSearchLimits",
    "AgentSearchProvider",
    "build_filter",
    "included_patterns_for",
    "normalize_results",
    "reviewed_patterns_for_hint",
    "site_pattern_for",
    "with_limits",
]
