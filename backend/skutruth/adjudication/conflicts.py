"""What to do when several facts want the same attribute slot.

Conflict is a property of a *set*, so it is settled after each fact has been judged on
its own. Four situations arise, and collapsing them would throw away exactly the
distinction the condition contracts exist to preserve.

| Values | Operating points | Outcome |
|---|---|---|
| same | same | one fact, the others merged into it |
| different | same | `CONFLICT` — a genuine disagreement, reviewed |
| same | different | `MULTIPLE_OPERATING_POINTS` — not a factual conflict |
| different | different | `MULTIPLE_OPERATING_POINTS` — both may well be true |

Rows three and four are the interesting ones. `18 A at AC-3` and `32 A at AC-1` do not
disagree about anything; they are two ratings of one device. Calling that a conflict
would be the classic mistake. But a single scalar cell cannot hold both either, so they
go to review rather than to the record — and the reason says which of the two problems
it is, so a person is not left guessing.

Facts reach one target either because a single source key was verified more than once,
or because several source keys legitimately map to the same output concept. The registry
permits that convergence deliberately; this module is where it is settled, on evidence.

## Never first-wins

Nothing here resolves a contest by input order, model order, or dictionary overwrite.
Facts merge only when they are *identical* — same semantic value, same operating point —
and every other multiplicity becomes a reviewed outcome. Silence would mean one verified
fact quietly overwriting another, which is unauditable by construction.

## Priority orders output; it never adjudicates

Mapping `priority` decides where an attribute sits in the delivery row. It is **not** a
precedence rule between disagreeing facts, and a lower number never wins an argument: two
sources stating different values under the same operating point both go to review however
they are prioritised. The only place priority is consulted here is choosing which of
several *identical* facts carries the merge — where there is nothing to win, because the
committed value is the same either way and only its position in the row is at stake.
"""

from __future__ import annotations

from collections.abc import Sequence

from .models import AdjudicatedFact, AdjudicationDecision, AdjudicationReason


def _fact_key(fact: AdjudicatedFact) -> tuple:
    """Value and operating point together. Two facts merge only if this matches."""
    assert fact.value is not None  # guaranteed for COMMIT by the model validator
    return (fact.value.semantic_key(), fact.conditions.key())


def _demote(
    fact: AdjudicatedFact, reason: AdjudicationReason, detail: str
) -> AdjudicatedFact:
    """Move a committed fact to review, dropping the value it would have written."""
    return AdjudicatedFact(
        outcome=fact.outcome,
        decision=AdjudicationDecision.REVIEW,
        reason=reason,
        detail=detail,
        spec=fact.spec,
    )


def resolve_conflicts(facts: Sequence[AdjudicatedFact]) -> tuple[AdjudicatedFact, ...]:
    """Settle contests between committed facts, preserving input order.

    Facts that were never committed pass through untouched: whatever refused them
    already said why, and re-deciding it here would overwrite a more specific reason
    with a less specific one.
    """
    committed = [f for f in facts if f.decision is AdjudicationDecision.COMMIT]
    by_target: dict[str, list[AdjudicatedFact]] = {}
    for fact in committed:
        assert fact.spec is not None
        by_target.setdefault(fact.spec.target_label, []).append(fact)

    replacements: dict[int, AdjudicatedFact] = {}

    for label, group in by_target.items():
        if len(group) == 1:
            continue

        operating_points = {f.conditions.key() for f in group}
        if len(operating_points) > 1:
            detail = (
                f"{len(group)} verified facts target {label!r} under "
                f"{len(operating_points)} different operating points "
                f"({'; '.join(sorted(f.conditions.display() for f in group))}); a single "
                f"attribute cell cannot represent them and the mapping does not say "
                f"which is meant"
            )
            for fact in group:
                replacements[id(fact)] = _demote(
                    fact, AdjudicationReason.MULTIPLE_OPERATING_POINTS, detail
                )
            continue

        values = {f.value.semantic_key() for f in group if f.value is not None}
        if len(values) > 1:
            detail = (
                f"{len(group)} verified facts state different values for {label!r} under "
                f"the same operating point: "
                f"{', '.join(sorted(f.value.display() for f in group if f.value))}"
            )
            for fact in group:
                replacements[id(fact)] = _demote(fact, AdjudicationReason.CONFLICT, detail)
            continue

        # Identical value, identical operating point. Genuinely the same fact observed
        # more than once — corroboration, not contention — so one attribute is written
        # and the rest are recorded as merged into it rather than discarded.
        #
        # The keeper is chosen by mapping priority, then source key. That is not priority
        # resolving a disagreement: these facts agree on value and operating point, so
        # the committed cell is identical whichever is kept, and the only thing being
        # decided is where the attribute sits in the row — which is exactly what priority
        # is for. The source key breaks ties so the result cannot depend on input order.
        keeper, *duplicates = sorted(
            group,
            key=lambda f: (f.spec.priority, f.source_key),  # type: ignore[union-attr]
        )
        replacements[id(keeper)] = AdjudicatedFact(
            outcome=keeper.outcome,
            decision=keeper.decision,
            reason=keeper.reason,
            detail=keeper.detail,
            spec=keeper.spec,
            value=keeper.value,
            merged_source_keys=tuple(sorted(d.source_key for d in duplicates)),
        )
        for duplicate in duplicates:
            replacements[id(duplicate)] = AdjudicatedFact(
                outcome=duplicate.outcome,
                decision=AdjudicationDecision.WITHHOLD,
                reason=AdjudicationReason.DUPLICATE_MERGED,
                detail=f"identical to {keeper.source_key} for {label!r}; merged into it",
                spec=duplicate.spec,
            )

    return tuple(replacements.get(id(f), f) for f in facts)


def conflicted_targets(facts: Sequence[AdjudicatedFact]) -> tuple[str, ...]:
    """Target labels that ended in a reviewed contest. Deterministic order."""
    contested = {
        AdjudicationReason.CONFLICT,
        AdjudicationReason.MULTIPLE_OPERATING_POINTS,
    }
    return tuple(
        sorted(
            {
                f.spec.target_label
                for f in facts
                if f.reason in contested and f.spec is not None
            }
        )
    )


__all__ = ["conflicted_targets", "resolve_conflicts"]
