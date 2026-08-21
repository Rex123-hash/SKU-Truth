"""From safely fetched bytes to an explicit PDF or HTML artifact.

Discovery hands over bytes; ingestion never reaches the network. PDF keeps its frozen
page-addressable representation. HTML is stored as original response bytes plus a
deterministic read model and is never assigned a synthetic page.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skutruth.contracts import DiscoveryMethod
from skutruth.ingest.errors import DocumentTooLargeError, IngestionError
from skutruth.ingest.html import HtmlArtifact, ingest_html_bytes
from skutruth.ingest.models import IngestedArtifact, SourceMetadata
from skutruth.ingest.pdf import ingest_pdf_bytes
from skutruth.ingest.storage import ArtifactStore, StoredArtifact

from .errors import FetchError, RejectionReason
from .fetch import FetchedResource
from .models import SourceCandidate

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance only
    from .models import DiscoveryResult


@dataclass(frozen=True, slots=True)
class AcquiredArtifact:
    """One stored artifact and the fetch that produced it."""

    artifact: StoredArtifact
    resource: FetchedResource
    #: True when this content was already in the store under the same hash and kind.
    deduplicated: bool

    @property
    def sha256(self) -> str:
        return self.artifact.sha256


def source_metadata_for(
    candidate: SourceCandidate,
    resource: FetchedResource,
    *,
    publisher: str | None,
    discovery_method: DiscoveryMethod,
) -> SourceMetadata:
    """Record only lineage discovery actually established.

    Exact locator relevance does not establish artifact identity, so ``identity_scope``
    and ``covers_mpn`` remain unset for both representations.
    """
    manufacturer_owned = candidate.may_store_as_manufacturer_evidence
    return SourceMetadata(
        publisher=publisher if manufacturer_owned else None,
        final_artifact_url=resource.final_url,
        discovery_url=candidate.url,
        discovery_method=discovery_method,
        source_type=candidate.source_type(),
        retrieved_at=resource.fetched_at,
        original_filename=resource.final_url.rsplit("/", 1)[-1] or None,
        license_note=(
            "Retrieved from the manufacturer's own site for local analysis. "
            "Redistribution rights not established; never commit."
        ),
    )


def _validate_authority_and_provenance(
    candidate: SourceCandidate,
    resource: FetchedResource,
    discovery_method: DiscoveryMethod | None,
) -> DiscoveryMethod:
    """The shared final gate before either representation can be stored."""
    if not candidate.may_store_as_manufacturer_evidence:
        raise FetchError(
            RejectionReason.REDIRECT_AUTHORITY_LOST,
            f"{resource.final_url} resolved to "
            f"{candidate.effective_authority.value}; only a host approved for this "
            f"manufacturer may be stored as its evidence",
        )
    if discovery_method is None:
        raise FetchError(
            RejectionReason.DISCOVERY_PROVENANCE_UNDECLARED,
            f"{candidate.result.provider!r} declares no DiscoveryMethod; an artifact "
            f"cannot be stored without recording how it was found",
        )
    return discovery_method


def acquire_pdf(
    candidate: SourceCandidate,
    resource: FetchedResource,
    *,
    store: ArtifactStore,
    discovery_method: DiscoveryMethod | None,
    publisher: str | None = None,
) -> AcquiredArtifact:
    """Ingest fetched PDF bytes with the existing page and signature semantics."""
    discovery_method = _validate_authority_and_provenance(
        candidate, resource, discovery_method
    )
    if not resource.is_pdf:
        raise FetchError(
            RejectionReason.NOT_INGESTABLE_YET,
            f"{resource.final_url} is {resource.content_type}; PDF ingestion refused it",
        )

    if store.exists(resource.sha256):
        stored = store.load(resource.sha256, verify_original=True)
        if not isinstance(stored, IngestedArtifact):
            raise FetchError(
                RejectionReason.INVALID_PDF,
                "content hash already exists with a non-PDF artifact kind",
            )
        return AcquiredArtifact(artifact=stored, resource=resource, deduplicated=True)

    try:
        artifact = ingest_pdf_bytes(
            resource.body,
            source=source_metadata_for(
                candidate,
                resource,
                publisher=publisher,
                discovery_method=discovery_method,
            ),
        )
    except IngestionError as exc:
        raise FetchError(
            RejectionReason.INVALID_PDF,
            f"{resource.final_url} could not be ingested: {exc}",
        ) from exc

    store.save(artifact, resource.body)
    return AcquiredArtifact(artifact=artifact, resource=resource, deduplicated=False)


def acquire_html(
    candidate: SourceCandidate,
    resource: FetchedResource,
    *,
    store: ArtifactStore,
    discovery_method: DiscoveryMethod | None,
    publisher: str | None = None,
) -> AcquiredArtifact:
    """Ingest fetched HTML without scripts, pages, or secondary network access."""
    discovery_method = _validate_authority_and_provenance(
        candidate, resource, discovery_method
    )
    if not resource.is_html:
        raise FetchError(
            RejectionReason.UNSUPPORTED_CONTENT_TYPE,
            f"{resource.final_url} is {resource.content_type}; HTML ingestion refused it",
        )

    if store.exists(resource.sha256):
        stored = store.load(resource.sha256, verify_original=True)
        if not isinstance(stored, HtmlArtifact):
            raise FetchError(
                RejectionReason.CONTENT_INTEGRITY_ERROR,
                "content hash already exists with a non-HTML artifact kind",
            )
        return AcquiredArtifact(artifact=stored, resource=resource, deduplicated=True)

    try:
        artifact = ingest_html_bytes(
            resource.body,
            media_type=resource.content_type,
            source=source_metadata_for(
                candidate,
                resource,
                publisher=publisher,
                discovery_method=discovery_method,
            ),
            final_authority=candidate.effective_authority.value,
        )
    except DocumentTooLargeError as exc:
        raise FetchError(
            RejectionReason.RESPONSE_TOO_LARGE,
            f"{resource.final_url} could not be ingested: {exc}",
        ) from exc
    except IngestionError as exc:
        raise FetchError(
            RejectionReason.CONTENT_INTEGRITY_ERROR,
            f"{resource.final_url} could not be ingested: {exc}",
        ) from exc

    store.save(artifact, resource.body)
    return AcquiredArtifact(artifact=artifact, resource=resource, deduplicated=False)


def acquire_resource(
    candidate: SourceCandidate,
    resource: FetchedResource,
    *,
    store: ArtifactStore,
    discovery_method: DiscoveryMethod | None,
    publisher: str | None = None,
) -> AcquiredArtifact:
    """Dispatch on trusted post-fetch MIME while keeping representations distinct."""
    if resource.is_pdf:
        return acquire_pdf(
            candidate,
            resource,
            store=store,
            discovery_method=discovery_method,
            publisher=publisher,
        )
    if resource.is_html:
        return acquire_html(
            candidate,
            resource,
            store=store,
            discovery_method=discovery_method,
            publisher=publisher,
        )
    raise FetchError(
        RejectionReason.UNSUPPORTED_CONTENT_TYPE,
        f"{resource.final_url} served unsupported {resource.content_type!r}",
    )


def discovered_artifacts(
    result: DiscoveryResult, store: ArtifactStore
) -> tuple[StoredArtifact, ...]:
    """Load acquired PDF and HTML artifacts with integrity rechecked.

    Consumers dispatch on ``artifact_kind``. PDF-only extraction and verification must
    continue to require ``IngestedArtifact`` rather than treating HTML as one page.
    """
    seen: set[str] = set()
    artifacts: list[StoredArtifact] = []
    for candidate in result.acquired:
        sha = candidate.artifact_sha256
        if not sha or sha in seen:
            continue
        seen.add(sha)
        artifacts.append(store.load(sha, verify_original=True))
    return tuple(artifacts)


__all__ = [
    "AcquiredArtifact",
    "acquire_html",
    "acquire_pdf",
    "acquire_resource",
    "discovered_artifacts",
    "source_metadata_for",
]
