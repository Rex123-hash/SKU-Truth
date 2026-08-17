"""Why one product's discovery ended where it did.

`RejectionReason` explains one *candidate*. This explains one *product*, which is a
different question with a different audience: a reviewer looking at a pilot run wants to
know whether a row failed because nothing was found, because everything found was a
distributor, or because a real manufacturer document is sitting behind a domain nobody
has reviewed yet. Those need different work, and lumping them together as "no source"
would hide which.

## One outcome, chosen by precedence

A product can be several of these at once — a run may return a marketplace listing *and*
an unreviewed manufacturer page. Reporting a set would push the ranking decision onto
whoever reads it, so `diagnose` returns the single most actionable state under a
documented precedence, and the full per-candidate detail stays available in
`DiscoveryResult.rejection_counts()`.

The precedence is ordered by *what the operator would do next*, not by severity.
`DOMAIN_REVIEW_REQUIRED` outranks `ONLY_DISTRIBUTORS` because a human review would unblock
the row, whereas the distributor result is just noise around it.

## No outcome here is a quality score

These are states, not grades. `NO_RESULTS` for an obscure part is the system working
correctly, and nothing in this module should be summed into a percentage.
"""

from __future__ import annotations

from enum import StrEnum

from .errors import RejectionReason
from .models import CandidateStatus, DiscoveryResult, MpnRelevance, SourceAuthority


class SearchOutcome(StrEnum):
    """What happened to one product, in one word."""

    #: A manufacturer document was fetched, validated, and stored.
    ACQUIRED = "ACQUIRED"
    #: An approved host named an exact-reference document; acquisition did not complete.
    #: The reason is a `RejectionReason` on the candidate — typically the fetch budget.
    ELIGIBLE_NOT_ACQUIRED = "ELIGIBLE_NOT_ACQUIRED"
    #: Eligible, and every fetch attempt failed at the network or content layer.
    FETCH_FAILED = "FETCH_FAILED"
    #: Eligible, fetched, and refused at the provenance gate: the search provider cannot
    #: state how it found the document in the frozen `DiscoveryMethod` vocabulary.
    #:
    #: Ranked above the content checks because `acquire_pdf` applies it first — with a
    #: provider that declares no method, a row can never reach `HTML_ONLY` or
    #: `NO_PDF_FOUND`, and reporting either would misname the blocker. Clearing this needs
    #: a contract decision, not a different document.
    PROVENANCE_UNDECLARED = "PROVENANCE_UNDECLARED"
    #: An eligible candidate exists but is an HTML page, which this milestone stores
    #: nothing from. A real source, out of current ingestion scope.
    HTML_ONLY = "HTML_ONLY"

    #: The registry associates a candidate's host with this manufacturer, but the binding
    #: carries no `DomainReview`, so nothing found there may be stored. **The blocker a
    #: person can actually clear**, which is why it outranks everything below it.
    DOMAIN_REVIEW_REQUIRED = "DOMAIN_REVIEW_REQUIRED"

    #: An approved manufacturer host, and no document about this exact reference.
    FAMILY_ONLY = "FAMILY_ONLY"
    SIBLING_ONLY = "SIBLING_ONLY"
    NO_EXACT_MPN = "NO_EXACT_MPN"
    #: An approved manufacturer host and an exact reference, but nothing ingestible.
    NO_PDF_FOUND = "NO_PDF_FOUND"

    #: Results came back, none from a host associated with this manufacturer.
    ONLY_DISTRIBUTORS = "ONLY_DISTRIBUTORS"
    ONLY_MARKETPLACES = "ONLY_MARKETPLACES"
    NO_MANUFACTURER_DOMAIN = "NO_MANUFACTURER_DOMAIN"

    #: The provider returned nothing for any query.
    NO_RESULTS = "NO_RESULTS"
    #: No query was run — the row had nothing to search for.
    NOT_SEARCHED = "NOT_SEARCHED"


#: Rejections that mean the fetch itself failed, as opposed to a policy refusal.
_FETCH_FAILURES = frozenset(
    {
        RejectionReason.TIMEOUT,
        RejectionReason.HTTP_ERROR,
        RejectionReason.TRANSPORT_ERROR,
        RejectionReason.DNS_FAILURE,
        RejectionReason.RESPONSE_TOO_LARGE,
        RejectionReason.INVALID_PDF,
        RejectionReason.CONTENT_INTEGRITY_ERROR,
        RejectionReason.REDIRECT_BLOCKED,
        RejectionReason.TOO_MANY_REDIRECTS,
        RejectionReason.REDIRECT_AUTHORITY_LOST,
    }
)


def _has(candidates, reason: RejectionReason) -> bool:
    return any(reason.value in c.rejections for c in candidates)


def diagnose(result: DiscoveryResult) -> SearchOutcome:
    """The single most actionable state for this product. See the module docstring."""
    candidates = result.candidates

    if not result.executed_queries:
        return SearchOutcome.NOT_SEARCHED
    if not candidates:
        return SearchOutcome.NO_RESULTS

    if result.acquired:
        return SearchOutcome.ACQUIRED

    # -- something was eligible; say how far it got ----------------------------
    eligible = [c for c in candidates if c.is_eligible]
    if eligible:
        # Mirrors the order the gates actually run in `acquire_pdf`.
        if _has(eligible, RejectionReason.DISCOVERY_PROVENANCE_UNDECLARED):
            return SearchOutcome.PROVENANCE_UNDECLARED
        if _has(eligible, RejectionReason.NOT_INGESTABLE_YET):
            return SearchOutcome.HTML_ONLY
        if any(r in _FETCH_FAILURES for c in eligible for r in _reasons(c)):
            return SearchOutcome.FETCH_FAILED
        if _has(eligible, RejectionReason.UNSUPPORTED_CONTENT_TYPE):
            return SearchOutcome.NO_PDF_FOUND
        return SearchOutcome.ELIGIBLE_NOT_ACQUIRED

    # -- the blocker a human can clear ----------------------------------------
    if any(c.authority is SourceAuthority.UNVERIFIED_MANUFACTURER for c in candidates):
        return SearchOutcome.DOMAIN_REVIEW_REQUIRED

    # -- an approved host, but not this product -------------------------------
    approved = [c for c in candidates if c.authority.may_license_evidence]
    if approved:
        relevances = {c.relevance for c in approved}
        if relevances == {MpnRelevance.FAMILY_ONLY}:
            return SearchOutcome.FAMILY_ONLY
        if relevances == {MpnRelevance.SIBLING}:
            return SearchOutcome.SIBLING_ONLY
        return SearchOutcome.NO_EXACT_MPN

    # -- nothing manufacturer-associated at all --------------------------------
    authorities = {c.authority for c in candidates}
    if authorities == {SourceAuthority.KNOWN_DISTRIBUTOR}:
        return SearchOutcome.ONLY_DISTRIBUTORS
    if authorities == {SourceAuthority.KNOWN_MARKETPLACE}:
        return SearchOutcome.ONLY_MARKETPLACES
    return SearchOutcome.NO_MANUFACTURER_DOMAIN


def _reasons(candidate) -> tuple[RejectionReason, ...]:
    """A candidate's rejections as typed values, ignoring any we no longer recognise."""
    out: list[RejectionReason] = []
    for raw in candidate.rejections:
        try:
            out.append(RejectionReason(raw))
        except ValueError:  # pragma: no cover - defensive
            continue
    return tuple(out)


def outcome_counts(outcomes) -> dict[str, int]:
    """Tally outcomes for a run. Counts only — never a rate, never a score."""
    counts: dict[str, int] = {}
    for outcome in outcomes:
        counts[outcome.value] = counts.get(outcome.value, 0) + 1
    return dict(sorted(counts.items()))


def candidate_states(result: DiscoveryResult) -> dict[str, int]:
    """How many candidates ended in each status, for the per-row report."""
    counts: dict[str, int] = {s.value: 0 for s in CandidateStatus}
    for candidate in result.candidates:
        counts[candidate.status.value] += 1
    return counts


__all__ = ["SearchOutcome", "candidate_states", "diagnose", "outcome_counts"]
