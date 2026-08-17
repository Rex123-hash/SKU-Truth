"""Discovery failures, and the typed reasons a candidate was refused.

Two different things live here, deliberately separated:

* **exceptions** — the caller did something impossible, or infrastructure failed;
* **`RejectionReason`** — a normal, expected outcome about one candidate. Most
  candidates are rejected, and rejection is the system working, not an error.

Nothing downstream classifies a rejection by reading prose. The reason is a typed value
decided where the check happened.
"""

from __future__ import annotations

from enum import StrEnum


class DiscoveryError(Exception):
    """Base class for every refusal in this package."""


class MalformedRegistryError(DiscoveryError):
    """A domain registry file cannot mean what it says."""


class UnsafeUrlError(DiscoveryError):
    """A URL was refused before any connection was attempted."""


class FetchError(DiscoveryError):
    """An acquisition attempt failed. Always carries a typed reason."""

    def __init__(self, reason: RejectionReason, detail: str) -> None:
        super().__init__(f"{reason.value}: {detail}")
        self.reason = reason
        self.detail = detail


class BudgetExceededError(DiscoveryError):
    """Discovery hit a configured limit. Bounded work is a feature, not a failure."""


class SearchProviderError(DiscoveryError):
    """A live search provider could not answer.

    Distinct from `FetchError`, which is about retrieving a *document*. This is about
    the search call itself, and it is never a statement about the product: a provider
    timing out tells us nothing about whether a manufacturer publishes a datasheet.

    ## These messages are constructed, never inherited

    An HTTP client's own exception text contains the request URL, and for an API keyed
    by query parameter that URL contains the credential. Every subclass here is raised
    with a message this package built, and `SearchCredentials.scrub` is applied to it,
    so a secret cannot reach a log, a traceback, or a report by riding along inside a
    third-party error string.
    """


class MissingSearchCredentialsError(SearchProviderError):
    """A live search was requested and the environment supplies no credential.

    Raised at construction rather than at call time, so a misconfigured run fails
    before it starts instead of halfway through a pilot.
    """


class SearchProviderTimeout(SearchProviderError):
    """The provider did not respond inside the configured timeout."""


class SearchProviderHTTPError(SearchProviderError):
    """The provider answered with an error status.

    Carries `status_code` so a caller can tell a quota refusal (429) from a bad
    credential (403) without parsing prose.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(f"search provider returned HTTP {status_code}: {detail}")
        self.status_code = status_code
        self.detail = detail


class SearchProviderTransportError(SearchProviderError):
    """The provider could not be reached at all — DNS, TLS, connection reset."""


class MalformedSearchResponseError(SearchProviderError):
    """The provider answered, and the body is not the shape its API documents.

    Refused rather than best-effort parsed. A partially understood response would
    silently drop results, and a run would report "no candidates" for a query that
    actually returned some.
    """


class SearchBudgetExceededError(BudgetExceededError):
    """The provider's total call budget for this process is spent.

    A separate ceiling from per-product query budgets: those bound one product, this
    bounds a whole run, so a loop over many rows cannot quietly become thousands of
    billable calls.
    """


class RejectionReason(StrEnum):
    """Why a candidate did not become an acquired manufacturer source."""

    # -- URL and transport safety ------------------------------------------
    MALFORMED_URL = "MALFORMED_URL"
    UNSUPPORTED_SCHEME = "UNSUPPORTED_SCHEME"
    BLOCKED_HOST = "BLOCKED_HOST"
    PRIVATE_ADDRESS = "PRIVATE_ADDRESS"
    DNS_FAILURE = "DNS_FAILURE"
    REDIRECT_BLOCKED = "REDIRECT_BLOCKED"
    TOO_MANY_REDIRECTS = "TOO_MANY_REDIRECTS"
    TIMEOUT = "TIMEOUT"
    HTTP_ERROR = "HTTP_ERROR"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    RESPONSE_TOO_LARGE = "RESPONSE_TOO_LARGE"

    # -- content --------------------------------------------------------------
    UNSUPPORTED_CONTENT_TYPE = "UNSUPPORTED_CONTENT_TYPE"
    INVALID_PDF = "INVALID_PDF"
    CONTENT_INTEGRITY_ERROR = "CONTENT_INTEGRITY_ERROR"
    #: An official HTML page. A legitimate candidate; this milestone does not ingest it.
    NOT_INGESTABLE_YET = "NOT_INGESTABLE_YET"
    #: The provider cannot state how it found the candidate, and `discovery_method` is
    #: non-optional on stored metadata. Refused rather than defaulted to a false value.
    DISCOVERY_PROVENANCE_UNDECLARED = "DISCOVERY_PROVENANCE_UNDECLARED"

    # -- authority ------------------------------------------------------------
    DOMAIN_NOT_APPROVED = "DOMAIN_NOT_APPROVED"
    OTHER_MANUFACTURER_DOMAIN = "OTHER_MANUFACTURER_DOMAIN"
    DISTRIBUTOR_SOURCE = "DISTRIBUTOR_SOURCE"
    MARKETPLACE_SOURCE = "MARKETPLACE_SOURCE"
    #: The registry associates this host with the manufacturer, but the association is
    #: not strong enough to license evidence — a locator-only spelling, or a registry
    #: marked DEMO. Distinct from DOMAIN_NOT_APPROVED, where nothing is known at all.
    AUTHORITY_NOT_ESTABLISHED = "AUTHORITY_NOT_ESTABLISHED"
    #: The request started at an approved manufacturer host and ended somewhere else.
    #: Deliberately **not** an SSRF reason: the destination may be entirely safe to
    #: connect to and still have no standing to publish this manufacturer's data.
    REDIRECT_AUTHORITY_LOST = "REDIRECT_AUTHORITY_LOST"

    # -- product relevance ----------------------------------------------------
    MPN_ABSENT = "MPN_ABSENT"
    FAMILY_ONLY = "FAMILY_ONLY"
    SIBLING_REFERENCE = "SIBLING_REFERENCE"
    AMBIGUOUS_REFERENCE = "AMBIGUOUS_REFERENCE"

    # -- budgets --------------------------------------------------------------
    FETCH_BUDGET_EXHAUSTED = "FETCH_BUDGET_EXHAUSTED"


__all__ = [
    "BudgetExceededError",
    "DiscoveryError",
    "FetchError",
    "MalformedRegistryError",
    "MalformedSearchResponseError",
    "MissingSearchCredentialsError",
    "RejectionReason",
    "SearchBudgetExceededError",
    "SearchProviderError",
    "SearchProviderHTTPError",
    "SearchProviderTimeout",
    "SearchProviderTransportError",
    "UnsafeUrlError",
]
