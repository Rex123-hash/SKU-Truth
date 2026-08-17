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

    # -- authority ------------------------------------------------------------
    DOMAIN_NOT_APPROVED = "DOMAIN_NOT_APPROVED"
    OTHER_MANUFACTURER_DOMAIN = "OTHER_MANUFACTURER_DOMAIN"
    DISTRIBUTOR_SOURCE = "DISTRIBUTOR_SOURCE"
    MARKETPLACE_SOURCE = "MARKETPLACE_SOURCE"

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
    "RejectionReason",
    "UnsafeUrlError",
]
