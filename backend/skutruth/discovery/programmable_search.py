"""A live `SearchProvider` backed by the Google Custom Search JSON API.

## Why this API and not Google Search grounding

`DiscoveryMethod.GOOGLE_SEARCH_GROUNDING` already exists in the frozen contract, so
grounding through Gemini looks like the obvious choice. It was investigated first and
rejected on two counts, both of which are documented behaviour of that API rather than
opinions about it:

* **The model chooses the queries.** Google's own documentation states that "the model
  analyzes the prompt and determines if a Google Search can improve the answer" and then
  "automatically generates one or multiple search queries and executes them". Discovery's
  query set is deterministic by design (`query.py`), because two runs of the same product
  must consult the same documents. A provider that substitutes sampled queries for the
  ones it was handed would make that guarantee unenforceable.
* **The URLs are not the publisher's.** Grounding returns `groundingChunks[].web.uri` as
  a `vertexaisearch.cloud.google.com/grounding-api-redirect/...` link, with `web.title`
  carrying only a domain. Every authority decision in this package is made from the host
  of the URL *before* anything is fetched. Redirect URIs collapse every result onto one
  Google host, so `classify_authority` would see `UNKNOWN` for a manufacturer datasheet
  and an eBay listing alike. Recovering the real host would mean fetching first and
  classifying afterwards — inverting the gate that makes the fetch safe.

The Custom Search JSON API has neither problem: the caller supplies `q` verbatim, and
`items[].link` is the publisher's own URL. No model is in the loop at any point.

## This provider cannot state its provenance, and says so

`discovery_method = None`, deliberately. The frozen `DiscoveryMethod` enumerates specific
mechanisms — `CURATED_CORPUS`, `GOOGLE_SEARCH_GROUNDING`, `URL_CONTEXT`, `DIRECT_URL`,
`OPERATOR_SUPPLIED` — and none of them describes a programmable web-search API. Declaring
`GOOGLE_SEARCH_GROUNDING` because Google runs the service would be exactly the branding-
decides-the-audit-trail failure `provider.py` warns about: these results never went near
the grounding pipeline.

The consequence is deliberate and load-bearing: acquisition refuses candidates found this
way with `DISCOVERY_PROVENANCE_UNDECLARED` rather than storing an artifact that misstates
how it was found. Search, ranking, and human review all work; storage waits for the
contract to gain a truthful value. See the README's contract-gap note.

## Credentials

The key is read from the environment, held only on the credentials object, and sent as an
`X-Goog-Api-Key` header rather than in the query string, so it stays out of URLs, request
logs, and proxy access logs. It is never part of the replay interaction descriptor, so it
cannot reach a cassette key or a stored recording.

Third-party exception text is never propagated. An HTTP client's own error message embeds
the request URL and sometimes the headers; every failure below is re-raised as a typed
error carrying a message this module built, with `scrub` applied so the secret cannot ride
along inside a string we did not write.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field

import httpx

from .errors import (
    MalformedSearchResponseError,
    MissingSearchCredentialsError,
    SearchBudgetExceededError,
    SearchProviderHTTPError,
    SearchProviderTimeout,
    SearchProviderTransportError,
)
from .provider import SearchCall

#: Bumped when a change here could alter which results a query returns or how they are
#: normalised. Recorded in the replay key, so a recording made under older behaviour is
#: never silently replayed as though this version produced it.
PROVIDER_VERSION = "google-programmable-search@v1"

#: Stable identifier recorded in provenance and in every cassette key.
PROVIDER_NAME = "google-programmable-search"

ENDPOINT_URL = "https://www.googleapis.com/customsearch/v1"

#: Environment variables, and the only place a credential is read from.
API_KEY_ENV = "SKUTRUTH_SEARCH_API_KEY"
ENGINE_ID_ENV = "SKUTRUTH_SEARCH_ENGINE_ID"

#: The API's own hard ceiling: "Valid values are integers between 1 and 10, inclusive."
MAX_RESULTS_PER_QUERY = 10

#: The API documents a 2048-character limit on the request.
MAX_QUERY_CHARS = 2048


@dataclass(frozen=True, slots=True)
class SearchCredentials:
    """A search API key and engine id, read from the environment and nowhere else.

    `api_key` is excluded from `repr` so a credential cannot reach a log line, a
    debugger dump, or a pytest assertion diff through ordinary object printing.
    """

    api_key: str = field(repr=False)
    engine_id: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> SearchCredentials:
        """Read credentials, or refuse. Never falls back to an unauthenticated call.

        `env` is injectable so tests can exercise both branches without touching the
        real process environment.
        """
        source = os.environ if env is None else env
        api_key = (source.get(API_KEY_ENV) or "").strip()
        engine_id = (source.get(ENGINE_ID_ENV) or "").strip()
        missing = [
            name
            for name, value in ((API_KEY_ENV, api_key), (ENGINE_ID_ENV, engine_id))
            if not value
        ]
        if missing:
            raise MissingSearchCredentialsError(
                f"live search needs {' and '.join(missing)} in the environment; "
                f"set them in your shell or a local .env that is never committed"
            )
        return cls(api_key=api_key, engine_id=engine_id)

    def scrub(self, text: str) -> str:
        """Remove the key from a string before it is raised, logged, or reported.

        Applied to every message this module produces. The engine id is not a secret —
        it identifies a search configuration, not an authorisation — so it is left
        readable, which keeps misconfiguration diagnosable.
        """
        return text.replace(self.api_key, "[REDACTED]") if self.api_key else text


@dataclass(frozen=True, slots=True)
class SearchLimits:
    """Ceilings on live search. There is no unbounded configuration.

    `max_calls` bounds the whole provider instance rather than one product: per-product
    query budgets already exist in `QueryBudget`, and a loop over organizer rows would
    otherwise multiply them into an unbounded, billable crawl.
    """

    max_results_per_query: int = MAX_RESULTS_PER_QUERY
    timeout_seconds: float = 10.0
    max_calls: int = 40
    #: Refused before parsing. A search response is small; a large one is a signal that
    #: something other than the documented API is answering.
    max_response_bytes: int = 2_000_000

    def __post_init__(self) -> None:
        if not 1 <= self.max_results_per_query <= MAX_RESULTS_PER_QUERY:
            raise ValueError(
                f"max_results_per_query must be 1..{MAX_RESULTS_PER_QUERY}; "
                f"got {self.max_results_per_query}"
            )
        if self.timeout_seconds <= 0 or self.max_calls < 1 or self.max_response_bytes < 1:
            raise ValueError("search limits must be positive")


def _result_rows(payload: object) -> list[dict]:
    """Pull `items` out of a documented response, refusing anything else.

    An absent `items` is a normal empty result — the API omits the key when a query
    matches nothing — but a body that is not an object, or an `items` that is not a
    list, means we are not talking to the API we think we are.
    """
    if not isinstance(payload, dict):
        raise MalformedSearchResponseError(
            f"expected a JSON object from the search API, got {type(payload).__name__}"
        )
    if "items" not in payload:
        return []
    items = payload["items"]
    if not isinstance(items, list):
        raise MalformedSearchResponseError(
            f"`items` must be a list, got {type(items).__name__}"
        )
    return items


def normalize_items(items: list[dict]) -> list[dict]:
    """Map documented API fields onto the shape `provider.execute_search` expects.

    Rank is the provider's own ordering, taken from a row's position in `items` — the
    API returns results in relevance order and states no rank field of its own. It is
    recorded because a reviewer should be able to see where a result sat, and it is
    never treated as authority.

    A skipped row leaves a gap in the ranks rather than closing it. If the third item
    is unusable, the fourth really was fourth in what the provider returned, and
    renumbering it to third would misreport the provider's ordering.

    A row without a usable `link` is skipped rather than repaired. Guessing a URL from
    `displayLink` would invent a locator the provider never returned, and locators are
    the one thing this class exists to report faithfully.
    """
    rows: list[dict] = []
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            continue
        url = str(item.get("link") or "").strip()
        if not url:
            continue
        rows.append(
            {
                "url": url,
                "title": str(item.get("title") or "").strip(),
                # Retained as locator metadata for human review. `models.SearchResult`
                # documents why this can never become evidence, and a test enforces it.
                "snippet": str(item.get("snippet") or "").strip(),
                "rank": index,
            }
        )
    return rows


class ProgrammableSearchProvider:
    """Live web search through the Custom Search JSON API. Locators only.

    Satisfies the `SearchProvider` protocol, so `discover_sources` cannot tell it apart
    from the offline fake beyond which candidates turn up — the point of the seam.
    """

    name = PROVIDER_NAME
    version = PROVIDER_VERSION

    #: No frozen `DiscoveryMethod` truthfully describes a programmable web-search API.
    #: See the module docstring; acquisition refuses rather than defaulting.
    discovery_method = None

    def __init__(
        self,
        credentials: SearchCredentials,
        *,
        limits: SearchLimits | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._credentials = credentials
        self._limits = limits or SearchLimits()
        self._client = client
        self._calls = 0

    @classmethod
    def from_env(
        cls,
        *,
        env: Mapping[str, str] | None = None,
        limits: SearchLimits | None = None,
        client: httpx.Client | None = None,
    ) -> ProgrammableSearchProvider:
        return cls(SearchCredentials.from_env(env), limits=limits, client=client)

    @property
    def calls_made(self) -> int:
        """How many live requests this instance has issued. Reported by the pilot."""
        return self._calls

    @property
    def limits(self) -> SearchLimits:
        return self._limits

    def request_options(self) -> dict:
        """Options that change what a query returns, for the replay key.

        Only the result cap varies today, and `search_request` already keys on it, so
        this stays empty rather than padding every cassette key with constants. It
        exists so a future option cannot be added without the key noticing.
        """
        return {}

    def _params(self, call: SearchCall) -> dict[str, str | int]:
        """The documented query parameters. The credential is not among them."""
        query = call.query.strip()
        if not query:
            raise MalformedSearchResponseError("refusing to search for an empty query")
        if len(query) > MAX_QUERY_CHARS:
            raise MalformedSearchResponseError(
                f"query is {len(query)} characters; the API limit is {MAX_QUERY_CHARS}"
            )
        requested = max(1, min(call.max_results, self._limits.max_results_per_query))
        return {"q": query, "cx": self._credentials.engine_id, "num": requested}

    def _read(self, response: httpx.Response) -> object:
        """Decode a response body, refusing one that is too large or not JSON."""
        body = response.content
        if len(body) > self._limits.max_response_bytes:
            raise MalformedSearchResponseError(
                f"search response is {len(body)} bytes, over the "
                f"{self._limits.max_response_bytes} byte cap"
            )
        try:
            return json.loads(body)
        except (ValueError, UnicodeDecodeError) as exc:
            raise MalformedSearchResponseError(
                self._credentials.scrub(f"search response is not JSON: {exc}")
            ) from None

    def search(self, call: SearchCall) -> list[dict]:
        """Execute one query. Returns raw result dicts; never raises a bare client error.

        `from None` on the re-raises is deliberate: chaining would attach the original
        client exception, whose `str()` contains the request URL, to the traceback — and
        the traceback is exactly what ends up in a log.
        """
        if self._calls >= self._limits.max_calls:
            raise SearchBudgetExceededError(
                f"live search budget of {self._limits.max_calls} provider calls is spent"
            )

        params = self._params(call)
        headers = {
            # Header rather than a `key=` query parameter, so the credential never
            # appears in a URL, a redirect, or an access log.
            "X-Goog-Api-Key": self._credentials.api_key,
            "Accept": "application/json",
        }

        self._calls += 1
        try:
            if self._client is not None:
                response = self._client.get(
                    ENDPOINT_URL,
                    params=params,
                    headers=headers,
                    timeout=self._limits.timeout_seconds,
                )
            else:
                with httpx.Client(timeout=self._limits.timeout_seconds) as client:
                    response = client.get(ENDPOINT_URL, params=params, headers=headers)
        except httpx.TimeoutException:
            raise SearchProviderTimeout(
                f"search provider did not respond within "
                f"{self._limits.timeout_seconds:g}s"
            ) from None
        except httpx.HTTPError as exc:
            raise SearchProviderTransportError(
                self._credentials.scrub(
                    f"could not reach the search provider: {type(exc).__name__}"
                )
            ) from None

        if response.status_code != httpx.codes.OK:
            raise SearchProviderHTTPError(
                response.status_code,
                self._credentials.scrub(_error_detail(response)),
            )

        return normalize_items(_result_rows(self._read(response)))


def _error_detail(response: httpx.Response) -> str:
    """A short, useful reason from an error body — never the whole body, never the URL.

    Google's error envelope carries `error.message`, which distinguishes an invalid key
    from an exhausted quota. Anything else collapses to the status text, because echoing
    an unrecognised body would risk reflecting back whatever it contains.
    """
    try:
        payload = response.json()
    except ValueError:
        return response.reason_phrase or "no error detail"
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            if message:
                return message[:300]
    return response.reason_phrase or "no error detail"


__all__ = [
    "API_KEY_ENV",
    "ENDPOINT_URL",
    "ENGINE_ID_ENV",
    "MAX_QUERY_CHARS",
    "MAX_RESULTS_PER_QUERY",
    "PROVIDER_NAME",
    "PROVIDER_VERSION",
    "ProgrammableSearchProvider",
    "SearchCredentials",
    "SearchLimits",
    "normalize_items",
]
