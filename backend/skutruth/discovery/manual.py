"""Human-supplied manufacturer locators through the existing discovery trust path.

A person supplies only a URL and an optional note. The URL is adapted into the same
candidate policy used for search results: reviewed-domain authority and URL/title MPN
relevance are re-derived, never asserted by the person. Eligible locators then converge
into the shared safe fetch, redirect reclassification, PDF ingestion, and ArtifactStore
path.

No search provider or search cassette participates. Stored artifacts use
``DiscoveryMethod.OPERATOR_SUPPLIED`` and retain unset identity scope: an exact reference
in a locator permits acquisition, but only document inspection can establish what the
artifact itself covers.
"""

from __future__ import annotations

import ipaddress
from enum import StrEnum

import httpx
from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import DiscoveryMethod
from skutruth.ingest.storage import ArtifactStore

from .domains import DomainRegistry
from .errors import FetchError
from .fetch import FetchPolicy, Resolver, system_resolver, validate_url_structure
from .models import CandidateStatus, DiscoveryRequest, SearchResult, SourceCandidate
from .service import acquire_candidate, classify_candidate

MANUAL_SOURCE_PROVIDER = "manual-operator-source"
MANUAL_SOURCE_QUERY = "operator-supplied locator"


class ManualLocatorKind(StrEnum):
    MANUAL = "MANUAL"


class ManualSourceMode(StrEnum):
    DRY_RUN = "DRY_RUN"
    LIVE = "LIVE"


class ManualSourceInput(BaseModel):
    """A locator tied to one real organizer row; no ownership or identity assertions."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    request: DiscoveryRequest
    url: str = Field(min_length=1)
    note: str = Field(
        default="",
        description="Operator context only; never consulted for MPN relevance or evidence",
    )

    @model_validator(mode="after")
    def _must_name_an_organizer_row(self) -> ManualSourceInput:
        if self.request.row_number is None or self.request.row_number < 1:
            raise ValueError("manual source input must identify its organizer row")
        return self


class ManualSourceResult(BaseModel):
    """The existing candidate decision plus manual-specific operational provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source: ManualSourceInput
    locator_kind: ManualLocatorKind = ManualLocatorKind.MANUAL
    mode: ManualSourceMode
    candidate: SourceCandidate

    manufacturer_key: str | None = None
    domain_review: str | None = None
    static_url_valid: bool
    dns_check_deferred: bool
    acquisition_would_be_attempted: bool
    network_attempted: bool = False
    bytes_downloaded: int = Field(default=0, ge=0)
    artifact_deduplicated: bool | None = None

    @model_validator(mode="after")
    def _dry_run_never_attempts_network(self) -> ManualSourceResult:
        if self.mode is ManualSourceMode.DRY_RUN and self.network_attempted:
            raise ValueError("manual dry-run cannot report a network attempt")
        if self.candidate.status is CandidateStatus.ACQUIRED and not self.candidate.artifact_sha256:
            raise ValueError("an acquired manual source must name its artifact")
        return self

    @property
    def input_host(self) -> str:
        return self.candidate.locator_host

    @property
    def reviewed_domain(self) -> bool:
        return self.candidate.authority.may_license_evidence

    @property
    def artifact_sha256(self) -> str | None:
        return self.candidate.artifact_sha256


def _manual_search_result(source: ManualSourceInput) -> SearchResult:
    """Adapt one operator locator without letting its note establish relevance."""
    return SearchResult(
        url=source.url,
        title="",
        snippet="",
        rank=1,
        query=MANUAL_SOURCE_QUERY,
        provider=MANUAL_SOURCE_PROVIDER,
    )


def _append_rejection(candidate: SourceCandidate, reason: str) -> SourceCandidate:
    rejections = tuple(dict.fromkeys((*candidate.rejections, reason)))
    return candidate.model_copy(
        update={"status": CandidateStatus.REJECTED, "rejections": rejections}
    )


def _dns_is_deferred(host: str) -> bool:
    if not host:
        return False
    try:
        ipaddress.ip_address(host)
    except ValueError:
        return True
    return False


def plan_manual_source(
    source: ManualSourceInput, *, registry: DomainRegistry
) -> ManualSourceResult:
    """Classify a manual locator with zero DNS, HTTP, provider, or store access."""
    candidate = classify_candidate(
        _manual_search_result(source), request=source.request, registry=registry
    )
    static_valid = True
    try:
        validated_host = validate_url_structure(source.url)
    except FetchError as exc:
        static_valid = False
        validated_host = ""
        candidate = _append_rejection(candidate, exc.reason.value)

    entry = registry.entry_for_hint(source.request.manufacturer_hint)
    would_attempt = static_valid and candidate.is_eligible
    return ManualSourceResult(
        source=source,
        mode=ManualSourceMode.DRY_RUN,
        candidate=candidate,
        manufacturer_key=entry.key if entry else None,
        domain_review=entry.review.describe() if entry and entry.review else None,
        static_url_valid=static_valid,
        dns_check_deferred=static_valid and _dns_is_deferred(validated_host),
        acquisition_would_be_attempted=would_attempt,
    )


def ingest_manual_source(
    source: ManualSourceInput,
    *,
    registry: DomainRegistry,
    store: ArtifactStore,
    policy: FetchPolicy | None = None,
    transport: httpx.BaseTransport | None = None,
    resolver: Resolver = system_resolver,
) -> ManualSourceResult:
    """Acquire an eligible manual locator through the shared live acquisition path."""
    plan = plan_manual_source(source, registry=registry)
    if not plan.acquisition_would_be_attempted:
        return plan.model_copy(
            update={"mode": ManualSourceMode.LIVE, "dns_check_deferred": False}
        )

    updated, acquired, byte_size = acquire_candidate(
        plan.candidate,
        store=store,
        registry=registry,
        manufacturer_hint=source.request.manufacturer_hint,
        publisher=source.request.manufacturer_hint,
        discovery_method=DiscoveryMethod.OPERATOR_SUPPLIED,
        policy=policy,
        transport=transport,
        resolver=resolver,
    )
    return plan.model_copy(
        update={
            "mode": ManualSourceMode.LIVE,
            "candidate": updated,
            "dns_check_deferred": False,
            "network_attempted": True,
            "bytes_downloaded": byte_size,
            "artifact_deduplicated": acquired.deduplicated if acquired else None,
        }
    )


__all__ = [
    "MANUAL_SOURCE_PROVIDER",
    "MANUAL_SOURCE_QUERY",
    "ManualLocatorKind",
    "ManualSourceInput",
    "ManualSourceMode",
    "ManualSourceResult",
    "ingest_manual_source",
    "plan_manual_source",
]
