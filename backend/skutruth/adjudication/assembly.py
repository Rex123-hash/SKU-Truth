"""Committed facts into delivery attribute slots — the first real bridge.

This is where the evidence half and the Unilog half finally touch:

    VerificationOutcome  →  adjudicate  →  resolve conflicts  →  attribute slots
                                                                       ↓
                                                                 DeliveryRecord

Everything the delivery row cannot carry — artifact hash, page, the document's own
words, the verifier version — stays on `AssemblyResult`. It is not written into the
252-column CSV, because that schema has nowhere to put it and inventing a column would
break the one contract the organizer stated explicitly. But it does not disappear.

## Slot order is explicit

Order comes from mapping priority, never from the alphabet and never from the order the
model happened to propose facts in. Target label breaks ties so that two rules at the
same priority still assemble identically on every run. When official category sequences
arrive they set `priority` and plug straight into this mechanism.

## Capacity is a hard edge

More committed attributes than declared slots raises. Truncating the tail would drop
verified facts into a file that looks complete, and nothing downstream could tell.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from skutruth.identity.models import IdentityResolution
from skutruth.unilog.delivery import DeliveryRecord, record_from_raw_row
from skutruth.unilog.input import RawProductRow
from skutruth.unilog.schema import DeliverySchema
from skutruth.verification import VerificationOutcome

from .conflicts import conflicted_targets, resolve_conflicts
from .errors import AdjudicationError, SlotCapacityError
from .mapping import MappingRegistry
from .models import (
    AdjudicatedFact,
    AdjudicationDecision,
    AssemblySummary,
    MappedUnilogAttribute,
)
from .policy import adjudicate, render_uom, render_value


@dataclass(frozen=True, slots=True)
class AssemblyResult:
    """One assembly: the row, every decision behind it, and the counts."""

    record: DeliveryRecord
    facts: tuple[AdjudicatedFact, ...]
    attributes: tuple[MappedUnilogAttribute, ...]
    summary: AssemblySummary
    registry_name: str
    #: False whenever any rule in play was hand-written rather than organizer-supplied.
    #: Consulted before anything describes this output as conforming to published rules.
    authoritative_mapping: bool

    def by_decision(self, decision: AdjudicationDecision) -> tuple[AdjudicatedFact, ...]:
        return tuple(f for f in self.facts if f.decision is decision)

    @property
    def committed(self) -> tuple[AdjudicatedFact, ...]:
        return self.by_decision(AdjudicationDecision.COMMIT)

    @property
    def withheld(self) -> tuple[AdjudicatedFact, ...]:
        return self.by_decision(AdjudicationDecision.WITHHOLD)

    @property
    def unmapped(self) -> tuple[AdjudicatedFact, ...]:
        return self.by_decision(AdjudicationDecision.UNMAPPED)

    @property
    def review(self) -> tuple[AdjudicatedFact, ...]:
        return self.by_decision(AdjudicationDecision.REVIEW)

    def provenance(self) -> tuple[dict, ...]:
        """Where every written attribute came from. For a reviewer, not for the CSV."""
        return tuple(
            {
                "slot": a.order,
                "label": a.label,
                "value": a.value_text,
                "uom": a.uom_text,
                "source_key": a.source_key,
                "supporting_source_keys": list(a.supporting_source_keys),
                "exact_mpn": a.exact_mpn,
                "artifact_sha256": a.artifact_sha256,
                "page": a.page_number,
                "evidence_text": a.evidence_text,
                "verifier_version": a.verifier_version,
                "authority": a.authority.value,
                "conditions": a.conditions.display(),
            }
            for a in self.attributes
        )


def build_attributes(facts: Sequence[AdjudicatedFact]) -> tuple[MappedUnilogAttribute, ...]:
    """Committed facts as slot-ready attributes, in explicit mapping order.

    Several source keys may map to one target, so two committed facts *could* in
    principle arrive here wanting the same slot. They cannot if conflicts were resolved
    first — identical facts merge, and anything else goes to review — so reaching this
    function with a contested target means `resolve_conflicts` was skipped. Raising says
    so; assigning both would let one silently overwrite the other, which is precisely the
    dictionary-overwrite failure the conflict engine exists to prevent.
    """
    committed = [f for f in facts if f.decision is AdjudicationDecision.COMMIT]

    seen: dict[str, str] = {}
    for fact in committed:
        assert fact.spec is not None
        first = seen.setdefault(fact.spec.target_label, fact.source_key)
        if first != fact.source_key:
            raise AdjudicationError(
                f"{first!r} and {fact.source_key!r} are both committed to "
                f"{fact.spec.target_label!r}. Convergent targets must go through "
                f"resolve_conflicts, which merges identical facts and sends every other "
                f"multiplicity to review; writing both would lose one."
            )

    ordered = sorted(
        committed,
        key=lambda f: (f.spec.priority, f.spec.target_label),  # type: ignore[union-attr]
    )

    attributes: list[MappedUnilogAttribute] = []
    for index, fact in enumerate(ordered, start=1):
        spec, value, outcome = fact.spec, fact.value, fact.outcome
        assert spec is not None and value is not None
        evidence = outcome.evidence.text if outcome.evidence is not None else outcome.matched_text
        attributes.append(
            MappedUnilogAttribute(
                label=spec.target_label,
                value_text=render_value(value),
                uom_text=render_uom(value),
                order=index,
                source_key=fact.source_key,
                supporting_source_keys=fact.supporting_source_keys,
                value=value,
                conditions=fact.conditions,
                authority=spec.authority,
                exact_mpn=outcome.exact_mpn,
                artifact_sha256=outcome.artifact_sha256,
                page_number=outcome.page_number,
                evidence_text=evidence,
                verifier_version=outcome.verifier_version,
            )
        )
    return tuple(attributes)


def write_attributes(
    record: DeliveryRecord, attributes: Sequence[MappedUnilogAttribute]
) -> None:
    """Fill attribute slots in order. Raises rather than truncating."""
    capacity = record.schema.attribute_slot_count
    if len(attributes) > capacity:
        raise SlotCapacityError(
            f"{len(attributes)} mapped attributes but the delivery template declares "
            f"{capacity} attribute slots. Refusing to truncate: the dropped facts are "
            f"verified, and a row with every slot full would look complete."
        )
    for attribute in attributes:
        record.set_attribute(
            attribute.order, attribute.label, attribute.value_text, attribute.uom_text
        )


def assemble_verified_attributes(
    outcomes: Sequence[VerificationOutcome],
    registry: MappingRegistry,
    schema: DeliverySchema,
    *,
    row: RawProductRow | None = None,
    identity: IdentityResolution | None = None,
) -> AssemblyResult:
    """Adjudicate verified facts and write the committed ones into a delivery record.

    `row`, when supplied, contributes only the byte-identical passthrough columns that
    `record_from_raw_row` already implements. No manufacturer, brand, classpath, title,
    description, or asset field is populated here — those need organizer rule data we
    do not have, and guessing at them is what this architecture exists to avoid.
    """
    facts = resolve_conflicts(adjudicate(outcomes, registry, identity=identity))
    attributes = build_attributes(facts)

    record = (
        record_from_raw_row(row, schema) if row is not None else DeliveryRecord(schema)
    )
    write_attributes(record, attributes)

    def count(decision: AdjudicationDecision) -> int:
        return sum(1 for f in facts if f.decision is decision)

    summary = AssemblySummary(
        input_facts=len(facts),
        verified=sum(1 for f in facts if f.is_verified),
        committed=count(AdjudicationDecision.COMMIT),
        withheld=count(AdjudicationDecision.WITHHOLD),
        unmapped=count(AdjudicationDecision.UNMAPPED),
        review=count(AdjudicationDecision.REVIEW),
        conflicts=len(conflicted_targets(facts)),
        attributes_written=len(attributes),
        slots_available=schema.attribute_slot_count,
    )
    return AssemblyResult(
        record=record,
        facts=facts,
        attributes=attributes,
        summary=summary,
        registry_name=registry.name,
        authoritative_mapping=registry.is_authoritative,
    )


__all__ = [
    "AssemblyResult",
    "assemble_verified_attributes",
    "build_attributes",
    "write_attributes",
]
