"""What discovery is asked, what it finds, and what it decides.

## A search result is a locator, never evidence

This is the rule the whole package is arranged around. A search engine returning
`officialmanufacturer.com/LC1D18P7 — "18 A contactor, 440 V"` has told us **where to
look**. It has not told us that the product is rated 18 A, and the snippet must never
reach a `ProductAttribute`, an `Evidence`, or an `ArtifactStore`. Only bytes we fetched
and hashed ourselves can do that, and even then they must still pass identity resolution
and mechanical verification exactly as before.

Rank is not authority either. Being first on a results page is a statement about a search
engine, not about who publishes a product's specification.

## No confidence anywhere

Every decision here is a categorical state with a typed reason. There is no probability
field on any model in this package, and a test enforces it.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import RunMode, SourceType

#: Bumped when a change could alter which candidates are accepted or how they rank.
DISCOVERY_VERSION = "source-discovery@v1"


class SourceAuthority(StrEnum):
    """The publisher relationship between a host and the product's manufacturer.

    Decided from a reviewed registry, never from the page's own claims and never from a
    manufacturer's name appearing in a hostname. `philips-superstore-example.com` says
    "Philips" and is not Philips.
    """

    #: A host the registry approves for *this* product's manufacturer, under a binding
    #: strong enough to license evidence.
    APPROVED_MANUFACTURER = "APPROVED_MANUFACTURER"
    #: The registry connects this host to the manufacturer, but not with enough standing
    #: to license a fact: the name matched only as a search locator, or the registry is
    #: marked DEMO. A useful candidate; not a publisher we can cite.
    UNVERIFIED_MANUFACTURER = "UNVERIFIED_MANUFACTURER"
    #: A host approved for a *different* manufacturer. Not authoritative here — a
    #: Schneider domain says nothing authoritative about a Philips part.
    OTHER_MANUFACTURER = "OTHER_MANUFACTURER"
    KNOWN_DISTRIBUTOR = "KNOWN_DISTRIBUTOR"
    KNOWN_MARKETPLACE = "KNOWN_MARKETPLACE"
    #: Explicitly refused: scrapers, mirrors, aggregators.
    BLOCKED = "BLOCKED"
    #: Not in any list. Unknown is not permission.
    UNKNOWN = "UNKNOWN"

    @property
    def may_license_evidence(self) -> bool:
        """Only a manufacturer-approved host may become licensing evidence."""
        return self is SourceAuthority.APPROVED_MANUFACTURER


class MpnRelevance(StrEnum):
    """How a candidate's URL and title relate to the target reference.

    Deterministic and deliberately blunt. These states exist to **demote** candidates:
    only `EXACT` lets one be acquired, and even an `EXACT` candidate has proved nothing
    about the product until the fetched document passes identity resolution. A heuristic
    that can only reduce trust is safe; one that grants it is not.
    """

    #: The target reference occurs as a whole token, canonically identical.
    EXACT = "EXACT"
    #: A shorter reference the target extends — `LC1D18` for `LC1D18P7`. A family stem
    #: is not its own child, which is the leap the identity stage exists to prevent.
    FAMILY_ONLY = "FAMILY_ONLY"
    #: A reference sharing a stem but diverging — `LC1D18B7` against `LC1D18P7`.
    SIBLING = "SIBLING"
    #: Several diverging siblings and no exact match: the page does not identify one.
    AMBIGUOUS = "AMBIGUOUS"
    ABSENT = "ABSENT"

    @property
    def is_exact(self) -> bool:
        return self is MpnRelevance.EXACT


class CandidateStatus(StrEnum):
    """What discovery decided about one candidate."""

    #: Manufacturer-approved, exact reference, and a content type we can ingest.
    ACQUIRED = "ACQUIRED"
    #: Eligible, but acquisition failed or was not attempted (budget, or HTML).
    ACCEPTED_NOT_ACQUIRED = "ACCEPTED_NOT_ACQUIRED"
    REJECTED = "REJECTED"


class SourceKind(StrEnum):
    """What a candidate looks like. A hint for ranking, never an authority claim."""

    DATASHEET = "DATASHEET"
    PRODUCT_PAGE = "PRODUCT_PAGE"
    CATALOG = "CATALOG"
    MANUAL = "MANUAL"
    UNKNOWN = "UNKNOWN"


class DiscoveryRequest(BaseModel):
    """Identity hints for one product. Only what the input actually supplies.

    `manufacturer_hint` is exactly what the source row said — `Phillips Lighting`
    misspelling and all. It is a *hint*: the approved manufacturer master is not in the
    organizer pack, so nothing here is canonical, and a hint that matches no registry
    entry yields no approved domain rather than a guess.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    mpn: str = Field(min_length=1, description="Cleaned manufacturer part number")
    raw_mpn: str | None = Field(default=None, description="Exactly what the row said")
    manufacturer_hint: str | None = Field(
        default=None, description="Manufacturer name as written. Never canonical."
    )
    manufacturer_code: str | None = Field(
        default=None, description="Supplier code parsed from `Name (CODE)`, if any"
    )
    brand_signals: tuple[str, ...] = Field(
        default=(), description="Non-placeholder brand values, in file order"
    )
    description: str | None = None
    row_number: int | None = Field(default=None, description="Source row, for traceability")


class SearchResult(BaseModel):
    """One result as a provider returned it. Locator metadata only."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: str = Field(min_length=1)
    title: str = ""
    #: Retained so a reviewer can see what the provider showed. **Never evidence** — a
    #: test asserts no snippet reaches an artifact or a verified span.
    snippet: str = ""
    rank: int = Field(ge=1, description="Provider's own ordering. Not authority.")
    query: str = Field(min_length=1, description="The query that returned it")
    provider: str = Field(min_length=1)

    #: The publisher host a provider reported *separately from the URL*, for the class of
    #: provider whose `url` is a redirect rather than the publisher's own address. A
    #: Google Search grounding adapter needed this — its links were
    #: `vertexaisearch.cloud.google.com/grounding-api-redirect/…` with the real publisher
    #: in a separate field — and without it every result classified as one Google host,
    #: making a manufacturer datasheet indistinguishable from a marketplace listing.
    #:
    #: **No current provider populates it.** Agent Search returns the publisher's own URL,
    #: so `host_of(url)` applies and this stays `None`. The field is kept because the
    #: hazard it addresses is a real property of redirect-returning providers, and because
    #: `candidate_host` handling it in one place is what stops a future adapter
    #: special-casing itself through the policy layer.
    #:
    #: **It is locator metadata, exactly like `url`.** It may decide whether a candidate is
    #: worth fetching. It may not establish manufacturer ownership, evidence authority,
    #: product identity, or artifact scope — it is a provider's claim, and the authority
    #: that governs storage is re-decided on the host the bytes actually arrived from
    #: (`SourceCandidate.final_authority`). It never replaces `url`.
    publisher_host: str | None = Field(
        default=None, description="Provider-reported publisher host. A locator hint."
    )


class SourceCandidate(BaseModel):
    """A search result after policy has been applied to it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    result: SearchResult
    #: The host authority was decided against: the provider-reported publisher host when
    #: there is one, otherwise the URL's own host.
    host: str = Field(description="Normalized lowercase host")
    #: The host the fetch will actually start at, from `result.url`. Differs from `host`
    #: only for a provider that returns a redirect, and it is kept because the two answer
    #: different questions — who is said to publish this, and where we are about to
    #: connect. Collapsing them would hide a redirect behind a manufacturer's name.
    locator_host: str = ""
    #: Authority of the host the search engine named. This is what decides whether the
    #: candidate is worth fetching — it is **not** what decides what may be stored.
    authority: SourceAuthority
    #: Authority of the host the download actually came from, set once a fetch has
    #: happened. A redirect can move the bytes to a host with no standing to publish
    #: this manufacturer's data, and only this field can see that.
    final_authority: SourceAuthority | None = None
    relevance: MpnRelevance
    kind: SourceKind
    status: CandidateStatus
    #: Typed reasons, in the order the checks ran. Empty for an accepted candidate.
    rejections: tuple[str, ...] = ()
    #: The ranking key, exposed so a reviewer can see why one candidate beat another.
    rank_reasons: tuple[str, ...] = ()

    artifact_sha256: str | None = None
    final_url: str | None = None
    fetched_at: datetime | None = None
    http_status: int | None = None
    content_type: str | None = None
    byte_size: int | None = None
    redirect_chain: tuple[str, ...] = ()

    @property
    def url(self) -> str:
        return self.result.url

    @property
    def is_eligible(self) -> bool:
        """Worth fetching: manufacturer-approved host, and about this exact reference.

        Eligibility is a decision about the *search result*. Whether the bytes that come
        back may be stored as manufacturer evidence is decided again afterwards, against
        `effective_authority`.
        """
        return self.authority.may_license_evidence and self.relevance.is_exact

    @property
    def effective_authority(self) -> SourceAuthority:
        """The authority that governs what may be stored.

        The final host once one is known, the originally named host otherwise. Everything
        that writes provenance reads this rather than `authority`, so a redirect cannot
        leave a stored artifact claiming a publisher it never came from.
        """
        return self.final_authority or self.authority

    @property
    def may_store_as_manufacturer_evidence(self) -> bool:
        return self.effective_authority.may_license_evidence

    @model_validator(mode="after")
    def _rejected_candidates_explain_themselves(self) -> SourceCandidate:
        if self.status is CandidateStatus.REJECTED and not self.rejections:
            raise ValueError(f"{self.url} was rejected without a reason")
        if self.status is CandidateStatus.ACQUIRED and not self.artifact_sha256:
            raise ValueError(f"{self.url} is ACQUIRED but names no artifact")
        return self

    def source_type(self) -> SourceType | None:
        """The frozen contract's publisher class, when it can be truthfully stated.

        Two ways to return `None`, both deliberate:

        * the host has no standing — returning `GENERAL_WEB` would be this package
          claiming to classify a stranger's site, which it cannot do;
        * the document kind is not established. `MANUFACTURER_DATASHEET` asserts the
          document *is a datasheet*, and a PDF from a manufacturer may equally be a
          manual, a warranty, a brochure, or a catalogue. Labelling all of them
          `DATASHEET` would fabricate a document type from a file extension.

        `SourceMetadata.source_type` is optional precisely so this can be left unsaid,
        and the repository's own ingested Schneider catalogue records `null` here. A
        later stage that needs the value must establish it from the document.
        """
        if not self.may_store_as_manufacturer_evidence:
            return None
        if self.kind is SourceKind.PRODUCT_PAGE:
            return SourceType.MANUFACTURER_PAGE
        if self.kind is SourceKind.DATASHEET:
            return SourceType.MANUFACTURER_DATASHEET
        return None


class DiscoverySummary(BaseModel):
    """Operational counts. Not accuracy — no labelled source set exists."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    queries: int = 0
    search_results: int = 0
    candidates: int = 0
    official_candidates: int = 0
    exact_mpn_candidates: int = 0
    family_candidates: int = 0
    rejected_third_party: int = 0
    fetch_attempts: int = 0
    fetch_successes: int = 0
    artifacts_ingested: int = 0
    bytes_downloaded: int = 0

    def render(self) -> str:
        return (
            f"{self.queries} queries · {self.search_results} results · "
            f"{self.official_candidates} official · {self.exact_mpn_candidates} exact · "
            f"{self.fetch_successes}/{self.fetch_attempts} fetched · "
            f"{self.artifacts_ingested} ingested"
        )


class DiscoveryResult(BaseModel):
    """Everything discovery did for one product, and why.

    Candidates are returned ranked *with their reasons*, not reduced to one winner.
    `preferred` is a convenience over the same ordering; it never hides the rest, and a
    reviewer can always see what else was found and why it lost.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    request: DiscoveryRequest
    #: What SKUTruth asked for, from `build_queries`. **Deterministic**: the same row
    #: produces the same intents on every run, and they are what the code controls.
    #:
    #: Named `executed_queries` for the providers where the two coincide — a plain search
    #: API runs the string it is given. It keeps that name for compatibility; read it as
    #: "the queries we issued".
    executed_queries: tuple[str, ...] = ()
    #: What the provider actually searched, when it reports that and it can differ.
    #: Google Search grounding generates its own queries from a prompt and returns them in
    #: `groundingMetadata.webSearchQueries`; those are recorded here verbatim.
    #:
    #: **Not deterministic, and never presented as such.** Two LIVE runs of one product may
    #: search differently. Empty means the provider reported nothing separate, which is the
    #: normal case for a provider that runs the query it was handed — it does *not* mean
    #: nothing was searched.
    #:
    #: QUERY INTENT IS DETERMINISTIC · SEARCH EXECUTION IS PROVIDER-GENERATED AND RECORDED.
    provider_executed_queries: tuple[str, ...] = ()
    candidates: tuple[SourceCandidate, ...] = ()
    summary: DiscoverySummary = Field(default_factory=DiscoverySummary)
    mode: RunMode
    provider: str = ""
    discovery_version: str = DISCOVERY_VERSION

    @property
    def requested_queries(self) -> tuple[str, ...]:
        """The deterministic intents SKUTruth issued. An alias that says what it means."""
        return self.executed_queries

    @property
    def search_execution_was_provider_generated(self) -> bool:
        """Whether the provider chose its own queries rather than running ours."""
        return bool(self.provider_executed_queries)

    @property
    def accepted(self) -> tuple[SourceCandidate, ...]:
        return tuple(c for c in self.candidates if c.status is not CandidateStatus.REJECTED)

    @property
    def rejected(self) -> tuple[SourceCandidate, ...]:
        return tuple(c for c in self.candidates if c.status is CandidateStatus.REJECTED)

    @property
    def acquired(self) -> tuple[SourceCandidate, ...]:
        return tuple(c for c in self.candidates if c.status is CandidateStatus.ACQUIRED)

    @property
    def preferred(self) -> SourceCandidate | None:
        """The best acquired source, or the best accepted one. `None` is a real answer."""
        return next(iter(self.acquired), None) or next(iter(self.accepted), None)

    @property
    def found_authoritative_source(self) -> bool:
        return bool(self.acquired)

    def rejection_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for candidate in self.rejected:
            for reason in candidate.rejections:
                counts[reason] = counts.get(reason, 0) + 1
        return dict(sorted(counts.items()))


__all__ = [
    "DISCOVERY_VERSION",
    "CandidateStatus",
    "DiscoveryRequest",
    "DiscoveryResult",
    "DiscoverySummary",
    "MpnRelevance",
    "SearchResult",
    "SourceAuthority",
    "SourceCandidate",
    "SourceKind",
]
