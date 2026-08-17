"""From fetched bytes to an ingested artifact, with discovery lineage attached.

`ingest/limits.py` already states the contract this module satisfies: *"Discovery hands
over bytes; ingestion never reaches the network."* That seam was designed before there
was a fetcher, and it is honoured exactly — nothing here re-implements PDF parsing,
hashing, or page mapping. Bytes go into the existing `ArtifactStore` and come out as the
same `IngestedArtifact` every later stage already consumes.

## What this milestone ingests

**PDFs only.** An official HTML product page is a legitimate discovery, and it is
recorded as an accepted candidate with its bytes hashed — but it is not forced into an
artifact store whose every invariant (page map, page hashes, per-page text) is defined in
terms of a paginated document. Writing an HTML page in there as a one-page PDF-shaped
record would be a small lie told in the place the whole system's provenance rests on.

So HTML candidates carry `NOT_INGESTABLE_YET`. That is a scope statement, not a quality
judgement, and it is the honest half of the narrower P0 described in the README.

## Lineage survives ingestion

`SourceMetadata` already carries exactly what discovery learns: the URL we asked for, the
URL we ended at, how it was found, the publisher, and when. Nothing new was invented for
it. What the frozen model has no field for — the redirect chain, the query that found the
document, the provider and its rank — stays on the `SourceCandidate`, so the lineage is
complete across the pair even though neither half holds all of it.

## Identical bytes are one artifact

Two URLs returning the same bytes produce one SHA-256 and therefore one stored artifact.
The second is not stored again and is not treated as independent corroboration: the same
document published at two addresses is one document, and counting it twice would let a
mirror manufacture agreement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from skutruth.contracts import DiscoveryMethod
from skutruth.ingest.errors import IngestionError
from skutruth.ingest.models import IngestedArtifact, SourceMetadata
from skutruth.ingest.pdf import ingest_pdf_bytes
from skutruth.ingest.storage import ArtifactStore

from .errors import FetchError, RejectionReason
from .fetch import FetchedResource
from .models import SourceCandidate

if TYPE_CHECKING:  # pragma: no cover - import cycle avoidance only
    from .models import DiscoveryResult


@dataclass(frozen=True, slots=True)
class AcquiredArtifact:
    """One stored artifact and the fetch that produced it."""

    artifact: IngestedArtifact
    resource: FetchedResource
    #: True when this content was already in the store under the same hash.
    deduplicated: bool

    @property
    def sha256(self) -> str:
        return self.artifact.sha256


#: Provider names that genuinely mean Google search grounding. The frozen
#: `DiscoveryMethod` enumerates specific mechanisms and has no generic "a search engine"
#: value, so anything else records `DIRECT_URL` — truthful, because we did fetch that URL
#: directly — and the actual provider name is preserved on the candidate and the
#: `DiscoveryResult` instead. Widening the frozen contract for this would be reopening it
#: for a labelling convenience, which is not a concrete bug.
GOOGLE_PROVIDERS = frozenset({"google", "google-search", "google_search", "programmable-search"})


def discovery_method_for(provider: str | None) -> DiscoveryMethod:
    """The narrowest truthful `DiscoveryMethod` for the provider that found a candidate.

    Never claims Google unless Google was actually used. A stored artifact asserting a
    discovery mechanism it did not go through is false provenance, and false provenance in
    the artifact store is the one thing this system cannot tolerate anywhere.
    """
    if provider and provider.strip().casefold() in GOOGLE_PROVIDERS:
        return DiscoveryMethod.GOOGLE_SEARCH_GROUNDING
    return DiscoveryMethod.DIRECT_URL


def source_metadata_for(
    candidate: SourceCandidate, resource: FetchedResource, *, publisher: str | None
) -> SourceMetadata:
    """Discovery lineage in the frozen ingestion contract's own terms.

    `source_type` comes from `candidate.source_type()`, which reads the **effective**
    authority — the host the bytes actually came from — and returns `None` when either the
    publisher or the document kind is not established. `None` is stored rather than a
    plausible-looking default: `SourceMetadata.source_type` is optional exactly so this
    can be left unsaid, and the repository's own ingested catalogue records `null` there.

    `identity_scope` and `covers_mpn` are likewise left unset. Discovery observed a
    reference in a URL and a title; whether the *document* covers that exact SKU is a
    question for identity resolution, and pre-filling it would let a search result decide
    what only the document's contents can.
    """
    manufacturer_owned = candidate.may_store_as_manufacturer_evidence
    return SourceMetadata(
        publisher=publisher if manufacturer_owned else None,
        final_artifact_url=resource.final_url,
        discovery_url=candidate.url,
        discovery_method=discovery_method_for(candidate.result.provider),
        source_type=candidate.source_type(),
        retrieved_at=resource.fetched_at,
        original_filename=resource.final_url.rsplit("/", 1)[-1] or None,
        license_note=(
            "Retrieved from the manufacturer's own site for local analysis. "
            "Redistribution rights not established; never commit."
        ),
    )


def acquire_pdf(
    candidate: SourceCandidate,
    resource: FetchedResource,
    *,
    store: ArtifactStore,
    publisher: str | None = None,
) -> AcquiredArtifact:
    """Ingest fetched PDF bytes into the existing artifact store.

    Raises `FetchError` with a typed reason if the bytes are not an ingestible PDF, so a
    caller never has to tell an ingestion failure from a policy refusal by reading prose.

    The authority check here is the last gate before bytes become evidence, and it reads
    the *effective* authority. A candidate that started at an approved manufacturer host
    and was redirected elsewhere fails here even though the fetch itself succeeded and was
    perfectly safe — being reachable and being the publisher are different properties.
    """
    if not candidate.may_store_as_manufacturer_evidence:
        raise FetchError(
            RejectionReason.REDIRECT_AUTHORITY_LOST,
            f"{resource.final_url} resolved to "
            f"{candidate.effective_authority.value}; only a host approved for this "
            f"manufacturer may be stored as its evidence",
        )
    if not resource.is_pdf:
        raise FetchError(
            RejectionReason.NOT_INGESTABLE_YET,
            f"{resource.final_url} is {resource.content_type}; this milestone ingests PDFs",
        )

    if store.exists(resource.sha256):
        return AcquiredArtifact(
            artifact=store.load(resource.sha256, verify_original=True),
            resource=resource,
            deduplicated=True,
        )

    try:
        artifact = ingest_pdf_bytes(
            resource.body, source=source_metadata_for(candidate, resource, publisher=publisher)
        )
    except IngestionError as exc:
        raise FetchError(
            RejectionReason.INVALID_PDF, f"{resource.final_url} could not be ingested: {exc}"
        ) from exc

    store.save(artifact, resource.body)
    return AcquiredArtifact(artifact=artifact, resource=resource, deduplicated=False)


def discovered_artifacts(
    result: DiscoveryResult, store: ArtifactStore
) -> tuple[IngestedArtifact, ...]:
    """Load every artifact a discovery run acquired, ready for the existing pipeline.

    The seam, in one function. What comes back is an ordinary `IngestedArtifact` — the
    same type identity resolution, extraction, and mechanical verification already
    consume — so a caller wires discovery to the rest of the system by passing these on,
    not by copying bytes or files anywhere.

    Integrity is re-validated on load, exactly as for a hand-ingested document. Nothing
    about having fetched a file ourselves makes it more trustworthy than one that arrived
    another way, and the store does not care which is which.
    """
    seen: set[str] = set()
    artifacts: list[IngestedArtifact] = []
    for candidate in result.acquired:
        sha = candidate.artifact_sha256
        if not sha or sha in seen:
            continue
        seen.add(sha)
        artifacts.append(store.load(sha, verify_original=True))
    return tuple(artifacts)


__all__ = [
    "AcquiredArtifact",
    "acquire_pdf",
    "discovered_artifacts",
    "source_metadata_for",
]
