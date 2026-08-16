"""Adapters into the generic claim model.

The seam that keeps the verification engine vocabulary-independent. An ETIM-shaped
`ExtractionCandidate` becomes a `ProductClaim` here; when Unilog LOV-backed candidates
arrive, a second function in this module will do the same for them, and the verifier will
not change.

This module is the *only* place in the package that imports from `skutruth.extraction`.
A test asserts the engine itself does not.
"""

from __future__ import annotations

from skutruth.extraction.models import ExtractionCandidate, ExtractionRun

from .models import ProductClaim


def claim_from_candidate(
    candidate: ExtractionCandidate, *, exact_mpn: str, artifact_sha256: str
) -> ProductClaim:
    """Turn one validated ETIM extraction candidate into a generic claim."""
    return ProductClaim(
        key=candidate.etim_feature_id,
        label=candidate.feature_name,
        value=candidate.value,
        conditions=candidate.conditions,
        exact_mpn=exact_mpn,
        artifact_sha256=artifact_sha256,
        page_number=candidate.page_number,
        source_fragment=candidate.source_fragment,
    )


def claims_from_run(run: ExtractionRun) -> tuple[ProductClaim, ...]:
    """Every validated candidate in an extraction run, as generic claims."""
    return tuple(
        claim_from_candidate(
            candidate,
            exact_mpn=run.target.exact_mpn,
            artifact_sha256=run.target.artifact_sha256,
        )
        for candidate in run.validated.candidates
    )


__all__ = ["claim_from_candidate", "claims_from_run"]
