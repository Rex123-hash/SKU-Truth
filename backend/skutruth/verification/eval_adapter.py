"""Turning a verification outcome into the evaluator's citation shape.

The evaluation framework already scores citations, and it already treats
`span_verified` as decisive. Until now nothing could set that field honestly — a producer
asserting `True` was asserting it about itself.

This adapter closes that gap without touching a single metric. `span_verified` is `True`
only for `EXACT_SPAN`, so citation validity becomes verification-backed rather than
self-reported. Scoring rules, tallies, and `NOT_EVALUATED` semantics are unchanged.
"""

from __future__ import annotations

from skutruth.contracts import EvidenceVerification, IdentityScope
from skutruth.eval.models import PredictedCitation

from .models import VerificationOutcome


def citation_from_outcome(
    outcome: VerificationOutcome, *, identity_scope: IdentityScope | None = None
) -> PredictedCitation:
    """Build the citation a verified outcome supports.

    The quote is the **artifact's** text, not the model's proposed fragment: the whole
    point of verification is that the two can differ, and only one of them is evidence.

    `identity_scope` is supplied by the caller from the artifact's own source metadata.
    It is not inferred here — manufacturing exact applicability is precisely what the
    scope rules exist to prevent.
    """
    verified = outcome.status is EvidenceVerification.EXACT_SPAN
    return PredictedCitation(
        artifact_sha256=outcome.artifact_sha256,
        page=outcome.page_number,
        quote=outcome.matched_text or None,
        identity_scope=identity_scope,
        span_verified=verified,
    )


__all__ = ["citation_from_outcome"]
