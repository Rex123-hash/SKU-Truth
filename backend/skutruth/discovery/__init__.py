"""Manufacturer source discovery and artifact acquisition.

A search result locates a candidate. It is never evidence. See ./README.md.
"""

from .acquire import (
    AcquiredArtifact,
    acquire_pdf,
    discovered_artifacts,
    source_metadata_for,
)
from .domains import (
    DEFAULT_REGISTRY_DIR,
    DomainRegistry,
    ManufacturerEntry,
    RegistryAuthority,
    host_covered_by,
    load_registry,
    normalize_host,
    normalize_manufacturer,
    parse_registry,
)
from .errors import (
    BudgetExceededError,
    DiscoveryError,
    FetchError,
    MalformedRegistryError,
    RejectionReason,
    UnsafeUrlError,
)
from .fetch import (
    ACQUISITION_VERSION,
    HTML_CONTENT_TYPES,
    PDF_CONTENT_TYPES,
    USER_AGENT,
    FetchedResource,
    FetchPolicy,
    fetch_url,
    validate_url,
)
from .models import (
    DISCOVERY_VERSION,
    CandidateStatus,
    DiscoveryRequest,
    DiscoveryResult,
    DiscoverySummary,
    MpnRelevance,
    SearchResult,
    SourceAuthority,
    SourceCandidate,
    SourceKind,
)
from .policy import classify_authority, classify_kind, classify_relevance, host_of
from .provider import SearchCall, SearchProvider, execute_search
from .query import QueryBudget, build_queries
from .ranking import rank_candidates, ranking_key, ranking_reasons
from .service import DiscoveryBudget, classify_candidate, discover_sources

__all__ = [
    "ACQUISITION_VERSION",
    "DEFAULT_REGISTRY_DIR",
    "DISCOVERY_VERSION",
    "HTML_CONTENT_TYPES",
    "PDF_CONTENT_TYPES",
    "USER_AGENT",
    "AcquiredArtifact",
    "BudgetExceededError",
    "CandidateStatus",
    "DiscoveryBudget",
    "DiscoveryError",
    "DiscoveryRequest",
    "DiscoveryResult",
    "DiscoverySummary",
    "DomainRegistry",
    "FetchError",
    "FetchPolicy",
    "FetchedResource",
    "MalformedRegistryError",
    "ManufacturerEntry",
    "MpnRelevance",
    "QueryBudget",
    "RegistryAuthority",
    "RejectionReason",
    "SearchCall",
    "SearchProvider",
    "SearchResult",
    "SourceAuthority",
    "SourceCandidate",
    "SourceKind",
    "UnsafeUrlError",
    "acquire_pdf",
    "build_queries",
    "classify_authority",
    "classify_candidate",
    "classify_kind",
    "classify_relevance",
    "discover_sources",
    "discovered_artifacts",
    "execute_search",
    "fetch_url",
    "host_covered_by",
    "host_of",
    "load_registry",
    "normalize_host",
    "normalize_manufacturer",
    "parse_registry",
    "rank_candidates",
    "ranking_key",
    "ranking_reasons",
    "source_metadata_for",
    "validate_url",
]
