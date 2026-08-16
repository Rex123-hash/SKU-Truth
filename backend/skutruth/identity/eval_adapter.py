"""Narrow bridge from a resolution to the existing evaluation framework.

The evaluation framework already scores identity: it compares `identity_disposition`,
checks `identity_mpn` when truth says `EXACT`, and keeps a `false_exact` tally over
every case whose truth is *not* exact. Nothing there needs changing.

The one thing this adapter must get right is that **`identity_mpn` is populated only for
`EXACT`.** A constructed-but-unconfirmed candidate lives in `candidate_references`, and
leaking it into the resolved-MPN field would let a guess score as a resolution — which
is exactly the failure `false_exact` exists to catch.
"""

from __future__ import annotations

from skutruth.contracts import IdentityDisposition
from skutruth.eval.models import CasePrediction

from .models import IdentityResolution


def identity_prediction_fields(resolution: IdentityResolution) -> dict[str, object]:
    """The identity half of a `CasePrediction`, as keyword arguments.

    Returned as a mapping rather than a built `CasePrediction` so a caller can merge it
    with attribute predictions and run metadata it owns.
    """
    return {
        "identity_disposition": resolution.disposition,
        # Only a confirmed exact reference is a resolved MPN. Candidates are not.
        "identity_mpn": (
            resolution.exact_mpn if resolution.disposition is IdentityDisposition.EXACT else None
        ),
    }


def to_case_prediction(resolution: IdentityResolution, case_id: str) -> CasePrediction:
    """A prediction carrying only what identity resolution determined.

    Attributes stay empty: this milestone produces no `ProductAttribute`, and an
    identity result must not be presented as though it had extracted product data.
    """
    return CasePrediction(case_id=case_id, **identity_prediction_fields(resolution))


__all__ = ["identity_prediction_fields", "to_case_prediction"]
