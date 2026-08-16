"""Deterministic identity resolution.

Identity is a hard gate. The single rule this module exists to enforce:

    constructing a candidate reference is not the same operation as
    confirming that the reference exists.

`BASE1` plus a documented rule `control_circuit/ac_230 -> X1` yields the candidate
`BASE1X1`. That concatenation succeeding proves only that the rule applied. It does not
prove that `BASE1X1` is a real orderable product — a catalogue's code table lists codes,
not which combinations the manufacturer actually builds. `EXACT` therefore requires a
separate `ExactReferenceFact` anchored to the candidate itself.

Getting this wrong is the project's most expensive possible failure: a confidently wrong
exact SKU is worse than an honest "which coil voltage?", because a buyer acts on it.

## No manufacturer logic lives here

No brand name, base reference, or completion code appears anywhere in this package — a
test enforces it. The resolver adjudicates over typed facts; a real vertical slice
supplies those facts from reviewed evidence in a local adapter. If a rule cannot be
expressed as a fact, it does not belong.

## What the resolver never does

* pick a default variant, or the most common one;
* treat "we have never seen this reference" as evidence that it is exact;
* let evidence for one manufacturer resolve another;
* let evidence for a sibling reference confirm this one;
* prefer whichever of two conflicting facts happened to be listed first.
"""

from __future__ import annotations

from skutruth.contracts import IdentityDisposition, ProductInput
from skutruth.contracts.mpn import canonical_mpn

from .evidence import (
    DiscriminatorMappingFact,
    EvidenceAnchor,
    IdentityEvidence,
    canonical_brand,
)
from .models import (
    DecisionStep,
    DiscriminatorSelection,
    IdentityResolution,
    TraceEntry,
)


class _Trace:
    """Accumulates numbered steps and the anchors they rest on, in order."""

    def __init__(self) -> None:
        self.entries: list[TraceEntry] = []
        self._anchors: list[EvidenceAnchor] = []

    def add(self, code: DecisionStep, detail: str, anchor: EvidenceAnchor | None = None) -> None:
        self.entries.append(
            TraceEntry(step=len(self.entries) + 1, code=code, detail=detail, anchor=anchor)
        )
        if anchor is not None and anchor not in self._anchors:
            self._anchors.append(anchor)

    @property
    def anchors(self) -> tuple[EvidenceAnchor, ...]:
        return tuple(self._anchors)


def resolve_identity(
    product: ProductInput,
    evidence: IdentityEvidence,
    selections: tuple[DiscriminatorSelection, ...] = (),
) -> IdentityResolution:
    """Resolve `product` against `evidence`. Pure, deterministic, and total.

    Never raises for an unresolvable input — that is a disposition, not an error.
    """
    brand = canonical_brand(product.brand) or product.brand
    mpn = canonical_mpn(product.mpn) or product.mpn
    trace = _Trace()

    ignored = evidence.facts_for_other_brands(product.brand, product.mpn)
    warnings: list[str] = []
    if ignored:
        trace.add(
            DecisionStep.BRAND_EVIDENCE_IGNORED,
            f"{ignored} fact(s) mention {mpn} under a different manufacturer and were "
            f"not used; identity evidence must match the requested brand.",
        )
        warnings.append(
            f"{ignored} fact(s) about {mpn} belong to another manufacturer and were ignored."
        )

    axes = evidence.axes_for(product.brand, product.mpn)
    known_axes = tuple(sorted({a.axis_key for a in axes}))
    if known_axes:
        warnings.append(
            "This reference varies along additional axes ("
            + ", ".join(known_axes)
            + "); binding the completing discriminator does not remove every ambiguity."
        )

    def build(
        disposition: IdentityDisposition,
        *,
        exact_mpn: str | None = None,
        unresolved: tuple[str, ...] = (),
        candidates: tuple[str, ...] = (),
        confirmed: bool = False,
        extra_warnings: tuple[str, ...] = (),
    ) -> IdentityResolution:
        # Recorded last on every path: these are context on the answer, not steps toward
        # it, and leading with them would bury the reasoning.
        for axis in axes:
            trace.add(
                DecisionStep.VARIATION_AXIS_KNOWN,
                f"{mpn} also varies along '{axis.axis_key}': {axis.description}",
                axis.anchor,
            )
        return IdentityResolution(
            input=product,
            brand_normalized=brand,
            mpn_normalized=mpn,
            disposition=disposition,
            exact_mpn=exact_mpn,
            supplied_discriminators=selections,
            unresolved_discriminators=unresolved,
            candidate_references=candidates,
            candidate_exactness_confirmed=confirmed,
            known_variation_axes=known_axes,
            warnings=tuple(warnings) + extra_warnings,
            trace=tuple(trace.entries),
            evidence_anchors=trace.anchors,
        )

    exact_facts = evidence.exact_for(product.brand, product.mpn)
    completion_facts = evidence.completions_for(product.brand, product.mpn)

    # A reference cannot both be a finished product and require completion. Choosing
    # either reading would be arbitrary, so neither is chosen.
    if exact_facts and completion_facts:
        for fact in exact_facts:
            trace.add(
                DecisionStep.CONFLICT_EXACT_AND_INCOMPLETE,
                f"Evidence states {mpn} is an exact reference.",
                fact.anchor,
            )
        for fact in completion_facts:
            trace.add(
                DecisionStep.CONFLICT_EXACT_AND_INCOMPLETE,
                f"Equally applicable evidence states {mpn} must be completed by "
                f"'{fact.discriminator_key}'.",
                fact.anchor,
            )
        return build(IdentityDisposition.CONTRADICTORY)

    # -- the input is itself an exact reference -------------------------------
    if exact_facts:
        targets = sorted({canonical_mpn(f.exact_mpn) or f.exact_mpn for f in exact_facts})
        if len(targets) > 1:  # pragma: no cover - guarded by canonical matching above
            for fact in exact_facts:
                trace.add(
                    DecisionStep.CONFLICT_RIVAL_EXACT_TARGETS,
                    f"Exact evidence points at {fact.exact_mpn}.",
                    fact.anchor,
                )
            return build(IdentityDisposition.CONTRADICTORY)
        fact = exact_facts[0]
        status = f" ({fact.commercial_status})" if fact.commercial_status else ""
        trace.add(
            DecisionStep.EXACT_REFERENCE_CONFIRMED,
            f"{fact.anchor.publisher or fact.brand} evidence confirms {targets[0]} is an exact "
            f"reference{status}.",
            fact.anchor,
        )
        return build(IdentityDisposition.EXACT, exact_mpn=targets[0])

    # -- the input is a base reference needing completion ---------------------
    if completion_facts:
        for fact in completion_facts:
            trace.add(
                DecisionStep.BASE_REFERENCE_INCOMPLETE,
                f"{fact.anchor.publisher or fact.brand} evidence records {mpn} as a base "
                f"reference completed by adding a '{fact.discriminator_key}' code.",
                fact.anchor,
            )

        required = list(dict.fromkeys(f.discriminator_key for f in completion_facts))
        for axis in axes:
            if axis.blocks_resolution and axis.axis_key not in required:
                required.append(axis.axis_key)
                trace.add(
                    DecisionStep.DISCRIMINATOR_REQUIRED,
                    f"Evidence states '{axis.axis_key}' must also be bound before {mpn} resolves.",
                    axis.anchor,
                )

        supplied = {s.key: s for s in selections}
        unresolved = tuple(key for key in required if key not in supplied)
        if unresolved:
            for key in unresolved:
                trace.add(
                    DecisionStep.DISCRIMINATOR_UNRESOLVED,
                    f"No selection supplied for '{key}'; a default is never assumed.",
                )
            return build(IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE, unresolved=unresolved)

        # P0 supports one completing code. A multi-code scheme needs an ordering rule
        # the evidence does not yet carry, and inventing one would fabricate references.
        if len(required) > 1:
            trace.add(
                DecisionStep.CONSTRUCTION_NOT_SUPPORTED,
                f"{mpn} requires {len(required)} discriminators "
                f"({', '.join(required)}); composing multiple completion codes is not "
                f"supported, so no candidate was constructed.",
            )
            return build(
                IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE,
                unresolved=tuple(required),
                extra_warnings=(
                    "Multi-discriminator reference construction is not supported yet.",
                ),
            )

        key = required[0]
        selection = supplied[key]
        trace.add(
            DecisionStep.DISCRIMINATOR_SUPPLIED,
            f"Selection supplied for '{key}': {selection.label or selection.canonical_value}.",
        )

        mappings = evidence.mappings_for(product.brand, product.mpn, key, selection.canonical_value)
        if not mappings:
            trace.add(
                DecisionStep.SELECTION_NOT_MAPPED,
                f"No completion rule maps '{key}' = '{selection.canonical_value}' for "
                f"{mpn}; a code is never inferred.",
            )
            return build(IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE, unresolved=(key,))

        candidates = sorted({_construct(m, mpn) for m in mappings})
        if len(candidates) > 1:
            for mapping in mappings:
                trace.add(
                    DecisionStep.CONFLICT_RIVAL_COMPLETION_CODES,
                    f"Rule maps '{key}' = '{selection.canonical_value}' to code "
                    f"'{mapping.completion_code}', giving {_construct(mapping, mpn)}.",
                    mapping.anchor,
                )
            return build(IdentityDisposition.CONTRADICTORY, candidates=tuple(candidates))

        candidate = candidates[0]
        mapping = mappings[0]
        trace.add(
            DecisionStep.CANDIDATE_CONSTRUCTED,
            f"'{key}' = '{selection.canonical_value}' maps to code "
            f"'{mapping.completion_code}', giving candidate {candidate}.",
            mapping.anchor,
        )

        confirmations = evidence.exact_for(product.brand, candidate)
        if not confirmations:
            trace.add(
                DecisionStep.CANDIDATE_UNCONFIRMED,
                f"No exact-reference evidence confirms {candidate} exists as a product; "
                f"a constructed candidate is not an exact identity.",
            )
            return build(
                IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE,
                unresolved=(),
                candidates=(candidate,),
                extra_warnings=(
                    f"{candidate} was constructed from a documented rule but no evidence "
                    f"confirms it is a real reference.",
                ),
            )

        confirmation = confirmations[0]
        status = f" ({confirmation.commercial_status})" if confirmation.commercial_status else ""
        trace.add(
            DecisionStep.EXACT_REFERENCE_CONFIRMED,
            f"{confirmation.anchor.publisher or confirmation.brand} evidence confirms "
            f"{candidate} is an exact reference{status}.",
            confirmation.anchor,
        )
        return build(
            IdentityDisposition.EXACT,
            exact_mpn=canonical_mpn(confirmation.exact_mpn) or candidate,
            candidates=(candidate,),
            confirmed=True,
        )

    # -- nothing applicable ---------------------------------------------------
    trace.add(
        DecisionStep.NO_APPLICABLE_EVIDENCE,
        f"No authoritative evidence establishes {mpn} as an exact reference or as a "
        f"base reference requiring completion.",
    )
    return build(IdentityDisposition.UNKNOWN)


def _construct(mapping: DiscriminatorMappingFact, base_mpn: str) -> str:
    """Apply a mapping's template, then canonicalise the result."""
    built = mapping.construct(base_mpn)
    return canonical_mpn(built) or built


__all__ = ["resolve_identity"]
