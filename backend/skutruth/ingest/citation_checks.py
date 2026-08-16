"""Artifact-level checks an evaluation citation can now actually perform.

Before this milestone, citation scoring could only compare a prediction's claimed
hash and page against fixture metadata — two pieces of paperwork agreeing with each
other. With ingestion, three of those claims become checkable against a stored
document:

* does an artifact with this hash exist in the store?
* do its stored bytes still hash to it?
* does the claimed page exist within it?

What remains uncheckable here is the one that matters most: **does the quoted span
support the proposed attribute value?** That needs span verification and condition
binding, neither of which exists, and this module goes out of its way not to imply
otherwise. `CitationArtifactCheck.quote_located` records whether the text was found on
the page — a necessary condition for support, and nowhere near a sufficient one.

The evaluation framework is not rewritten. This is a narrow helper it can call.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .errors import ArtifactNotFoundError, CorruptArtifactError
from .locate import find_text
from .storage import ArtifactStore


class ArtifactCheckOutcome(StrEnum):
    """Result of the artifact-level portion of a citation check."""

    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    ARTIFACT_CORRUPT = "ARTIFACT_CORRUPT"
    PAGE_OUT_OF_RANGE = "PAGE_OUT_OF_RANGE"
    PAGE_EXISTS = "PAGE_EXISTS"


@dataclass(frozen=True, slots=True)
class CitationArtifactCheck:
    """What could be established about a citation from the stored artifact alone."""

    sha256: str
    page: int | None
    outcome: ArtifactCheckOutcome
    page_count: int | None = None
    quote_located: bool | None = None
    detail: str = ""

    @property
    def artifact_verified(self) -> bool:
        """The artifact exists, hashes correctly, and contains the cited page."""
        return self.outcome is ArtifactCheckOutcome.PAGE_EXISTS

    @property
    def supports_value(self) -> None:
        """Deliberately always `None`.

        Whether a span supports a product attribute is a question about meaning,
        operating conditions, and identity scope. Ingestion cannot answer it, and a
        property that returned a boolean here would invite exactly the over-reading
        this whole design refuses.
        """
        return None


def check_citation_artifact(
    store: ArtifactStore,
    sha256: str,
    page: int | None = None,
    quote: str | None = None,
) -> CitationArtifactCheck:
    """Check a citation's artifact, hash, page, and optionally locate its quote.

    Never raises for a missing or corrupt artifact — those are results, and an
    evaluation run must record them rather than crash on them.
    """
    try:
        artifact = store.load(sha256)
    except ArtifactNotFoundError:
        return CitationArtifactCheck(
            sha256=sha256,
            page=page,
            outcome=ArtifactCheckOutcome.ARTIFACT_MISSING,
            detail=f"no artifact {sha256[:12]}… in {store.root}",
        )
    except CorruptArtifactError as exc:
        return CitationArtifactCheck(
            sha256=sha256,
            page=page,
            outcome=ArtifactCheckOutcome.ARTIFACT_CORRUPT,
            detail=exc.reason,
        )

    if page is not None and artifact.page(page) is None:
        return CitationArtifactCheck(
            sha256=sha256,
            page=page,
            outcome=ArtifactCheckOutcome.PAGE_OUT_OF_RANGE,
            page_count=artifact.page_count,
            detail=f"page {page} is outside 1..{artifact.page_count}",
        )

    located = None
    if quote:
        located = bool(find_text(artifact, quote, page_number=page, max_matches=1))

    return CitationArtifactCheck(
        sha256=sha256,
        page=page,
        outcome=ArtifactCheckOutcome.PAGE_EXISTS,
        page_count=artifact.page_count,
        quote_located=located,
        detail="artifact and page verified; span support not assessed",
    )
