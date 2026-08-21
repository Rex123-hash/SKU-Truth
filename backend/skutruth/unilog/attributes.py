"""Authority-gated Unilog attribute profiles, candidates, and deterministic parsing.

Profiles answer *which label belongs in which ordered delivery slot*.  Candidates answer
*what value was proposed and why*.  Keeping those questions separate prevents an ETIM
feature name, internal family, or model proposal from silently becoming an official
Unilog label.

The organizer examples are loadable evidence with exact-record scope.  They are not a
category taxonomy: their shared labels may be replayed only for the records observed in
the supplied file.  An organizer LOV or human approval can later supply broader scope
without changing the contracts in this module.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

from skutruth.contracts import EvidenceVerification

from .classification import ClassificationDecision
from .schema import DeliverySchema


class AttributeValueKind(StrEnum):
    TEXT = "TEXT"
    NUMBER = "NUMBER"
    RANGE = "RANGE"
    ENUM = "ENUM"
    BOOLEAN = "BOOLEAN"


class AttributeAuthority(StrEnum):
    """What licenses a profile label or candidate value.

    Label and value authority are deliberately different.  Manufacturer evidence can
    establish a product value but cannot name an official Unilog attribute.  ETIM can
    constrain an internal proposal but licenses neither a Unilog label nor a product
    value by itself.
    """

    ORGANIZER_EXAMPLE = "ORGANIZER_EXAMPLE"
    ORGANIZER_LOV = "ORGANIZER_LOV"
    MANUFACTURER_EVIDENCE = "MANUFACTURER_EVIDENCE"
    ETIM_REFERENCE = "ETIM_REFERENCE"
    MODEL_PROPOSAL = "MODEL_PROPOSAL"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    UNRESOLVED = "UNRESOLVED"

    @property
    def permits_profile_labels(self) -> bool:
        return self in {
            AttributeAuthority.ORGANIZER_EXAMPLE,
            AttributeAuthority.ORGANIZER_LOV,
            AttributeAuthority.HUMAN_APPROVED,
        }

    @property
    def permits_product_values(self) -> bool:
        return self in {
            AttributeAuthority.ORGANIZER_EXAMPLE,
            AttributeAuthority.MANUFACTURER_EVIDENCE,
            AttributeAuthority.HUMAN_APPROVED,
        }


class AttributeReason(StrEnum):
    ORGANIZER_EXAMPLE_VALUE = "ORGANIZER_EXAMPLE_VALUE"
    ELIGIBLE = "ELIGIBLE"
    NO_CANDIDATE = "NO_CANDIDATE"
    CANDIDATE_WITHHELD = "CANDIDATE_WITHHELD"
    CANDIDATE_REQUIRES_REVIEW = "CANDIDATE_REQUIRES_REVIEW"
    INSUFFICIENT_VALUE_AUTHORITY = "INSUFFICIENT_VALUE_AUTHORITY"
    MANUFACTURER_EVIDENCE_UNVERIFIED = "MANUFACTURER_EVIDENCE_UNVERIFIED"
    UNKNOWN_UOM = "UNKNOWN_UOM"
    LABEL_MISMATCH = "LABEL_MISMATCH"
    VALUE_KIND_MISMATCH = "VALUE_KIND_MISMATCH"
    UOM_MISMATCH = "UOM_MISMATCH"
    DUPLICATE_AGREEMENT = "DUPLICATE_AGREEMENT"
    CONFLICTING_VALUES = "CONFLICTING_VALUES"
    UNKNOWN_PROFILE_SLOT = "UNKNOWN_PROFILE_SLOT"
    PROFILE_AUTHORITY_INSUFFICIENT = "PROFILE_AUTHORITY_INSUFFICIENT"
    PROFILE_OUT_OF_SCOPE = "PROFILE_OUT_OF_SCOPE"


class UomResolution(StrEnum):
    NONE = "NONE"
    EXACT = "EXACT"
    ALIAS = "ALIAS"
    UNRESOLVED = "UNRESOLVED"


# Exact, reviewed spellings only.  This is formatting normalization, not conversion.
# It intentionally does not import or modify the frozen ETIM unit registry.
_UOM_ALIASES: dict[str, str] = {
    "V": "V",
    "volt": "V",
    "volts": "V",
    "A": "A",
    "amp": "A",
    "amps": "A",
    "in": "in",
    "inch": "in",
    "inches": "in",
    "dB": "dB",
    "dBA": "dBA",
}


def normalize_uom(raw_uom: str | None) -> tuple[str | None, UomResolution]:
    """Normalize only an exact known spelling; never guess or convert dimensions."""
    raw = "" if raw_uom is None else str(raw_uom)
    if not raw:
        return None, UomResolution.NONE
    normalized = _UOM_ALIASES.get(raw)
    if normalized is None:
        return None, UomResolution.UNRESOLVED
    resolution = UomResolution.EXACT if normalized == raw else UomResolution.ALIAS
    return normalized, resolution


@dataclass(frozen=True, slots=True)
class DecimalRange:
    minimum: Decimal
    maximum: Decimal

    def __post_init__(self) -> None:
        if self.minimum > self.maximum:
            raise ValueError("range minimum exceeds maximum")

    def display(self) -> str:
        return f"{self.minimum:f} to {self.maximum:f}"


NormalizedValue = str | Decimal | DecimalRange | bool


@dataclass(frozen=True, slots=True)
class UnilogAttributeValue:
    """Raw source representation beside a deterministic normalized representation."""

    raw_value: str
    normalized_value: NormalizedValue
    raw_uom: str
    normalized_uom: str | None
    value_kind: AttributeValueKind
    uom_resolution: UomResolution

    def __post_init__(self) -> None:
        if not self.raw_value:
            raise ValueError("attribute value cannot be blank")
        if self.raw_uom and self.uom_resolution is UomResolution.NONE:
            raise ValueError("a nonblank raw UOM cannot have NONE resolution")
        if not self.raw_uom and self.uom_resolution is not UomResolution.NONE:
            raise ValueError("a blank raw UOM must have NONE resolution")
        if self.uom_resolution is UomResolution.UNRESOLVED and self.normalized_uom is not None:
            raise ValueError("an unresolved UOM cannot carry a normalized UOM")

    @property
    def uom_is_resolved(self) -> bool:
        return self.uom_resolution is not UomResolution.UNRESOLVED

    def semantic_key(self) -> tuple[object, ...]:
        value = self.normalized_value
        if isinstance(value, DecimalRange):
            normalized: object = (value.minimum, value.maximum)
        elif isinstance(value, str):
            normalized = value.casefold() if self.value_kind is AttributeValueKind.ENUM else value
        else:
            normalized = value
        return (self.value_kind, normalized, self.normalized_uom)

    def delivery_value(self) -> str:
        value = self.normalized_value
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, DecimalRange):
            return value.display()
        if isinstance(value, Decimal):
            return f"{value:f}"
        return value

    def delivery_uom(self) -> str:
        return self.normalized_uom or ""


def _value(
    raw_value: str,
    normalized_value: NormalizedValue,
    kind: AttributeValueKind,
    raw_uom: str | None,
) -> UnilogAttributeValue:
    raw_unit = "" if raw_uom is None else str(raw_uom)
    normalized_uom, resolution = normalize_uom(raw_unit)
    return UnilogAttributeValue(
        raw_value=raw_value,
        normalized_value=normalized_value,
        raw_uom=raw_unit,
        normalized_uom=normalized_uom,
        value_kind=kind,
        uom_resolution=resolution,
    )


def parse_text(raw_value: str, *, raw_uom: str | None = None) -> UnilogAttributeValue:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError("text value cannot be blank")
    return _value(raw_value, normalized, AttributeValueKind.TEXT, raw_uom)


def parse_controlled_value(
    raw_value: str, *, raw_uom: str | None = None
) -> UnilogAttributeValue:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError("controlled value cannot be blank")
    return _value(raw_value, normalized, AttributeValueKind.ENUM, raw_uom)


def _decimal(text: str) -> Decimal:
    try:
        number = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"{text!r} is not a decimal number") from exc
    if not number.is_finite():
        raise ValueError(f"{text!r} is not a finite decimal number")
    return number


def parse_number(raw_value: str, *, raw_uom: str | None = None) -> UnilogAttributeValue:
    normalized = raw_value.strip()
    if not normalized:
        raise ValueError("number cannot be blank")
    return _value(raw_value, _decimal(normalized), AttributeValueKind.NUMBER, raw_uom)


def parse_decimal(raw_value: str, *, raw_uom: str | None = None) -> UnilogAttributeValue:
    """Parse an exact decimal spelling without converting through binary float."""
    return parse_number(raw_value, raw_uom=raw_uom)


_INTEGER = re.compile(r"^[+-]?\d+$")


def parse_integer(raw_value: str, *, raw_uom: str | None = None) -> UnilogAttributeValue:
    normalized = raw_value.strip()
    if not _INTEGER.fullmatch(normalized):
        raise ValueError(f"{raw_value!r} is not an integer")
    return _value(raw_value, Decimal(normalized), AttributeValueKind.NUMBER, raw_uom)


_NUMBER_WITH_UNIT = re.compile(
    r"^(?P<number>[+-]?(?:\d+(?:\.\d*)?|\.\d+))\s+(?P<uom>\S(?:.*\S)?)$"
)


def parse_number_with_unit(raw_value: str) -> UnilogAttributeValue:
    match = _NUMBER_WITH_UNIT.fullmatch(raw_value.strip())
    if match is None:
        raise ValueError(f"{raw_value!r} is not a number followed by a unit")
    return _value(
        raw_value,
        _decimal(match.group("number")),
        AttributeValueKind.NUMBER,
        match.group("uom"),
    )


_SIMPLE_RANGE = re.compile(
    r"^(?P<minimum>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"\s*(?:to|\.\.|–|—|\s-\s)\s*"
    r"(?P<maximum>[+-]?(?:\d+(?:\.\d*)?|\.\d+))"
    r"(?:\s+(?P<uom>\S(?:.*\S)?))?$",
    re.IGNORECASE,
)


def parse_simple_range(
    raw_value: str, *, raw_uom: str | None = None
) -> UnilogAttributeValue:
    match = _SIMPLE_RANGE.fullmatch(raw_value.strip())
    if match is None:
        raise ValueError(f"{raw_value!r} is not a simple numeric range")
    captured_uom = match.group("uom") or ""
    supplied_uom = "" if raw_uom is None else raw_uom
    if captured_uom and supplied_uom and captured_uom != supplied_uom:
        raise ValueError("range contains a UOM that conflicts with raw_uom")
    unit = supplied_uom or captured_uom
    span = DecimalRange(
        minimum=_decimal(match.group("minimum")),
        maximum=_decimal(match.group("maximum")),
    )
    return _value(raw_value, span, AttributeValueKind.RANGE, unit)


_TRUE = frozenset({"true", "yes", "1"})
_FALSE = frozenset({"false", "no", "0"})


def parse_boolean(raw_value: str) -> UnilogAttributeValue:
    token = raw_value.strip().casefold()
    if token in _TRUE:
        normalized = True
    elif token in _FALSE:
        normalized = False
    else:
        raise ValueError(f"{raw_value!r} is not a supported logical spelling")
    return _value(raw_value, normalized, AttributeValueKind.BOOLEAN, None)


@dataclass(frozen=True, slots=True)
class AttributeEvidence:
    """Optional manufacturer-evidence locator; organizer examples need not fake one."""

    artifact_id: str | None = None
    source_locator: str | None = None
    page: int | None = None
    source_fragment: str | None = None
    span_start: int | None = None
    span_end: int | None = None
    verification: EvidenceVerification | None = None

    def __post_init__(self) -> None:
        if self.page is not None and self.page < 1:
            raise ValueError("evidence page is 1-based")
        if self.span_start is not None and self.span_start < 0:
            raise ValueError("span_start cannot be negative")
        if self.span_end is not None and self.span_end < 0:
            raise ValueError("span_end cannot be negative")
        if (
            self.span_start is not None
            and self.span_end is not None
            and self.span_end < self.span_start
        ):
            raise ValueError("span_end cannot precede span_start")

    @property
    def licenses_manufacturer_value(self) -> bool:
        return bool(
            self.artifact_id
            and self.source_locator
            and self.verification is not None
            and self.verification.may_support_accepted_value
        )


@dataclass(frozen=True, slots=True)
class AttributeProfileEvidence:
    source_locator: str
    observed_record_keys: tuple[str, ...]
    detail: str


@dataclass(frozen=True, slots=True)
class AttributeProfileScope:
    """Where a profile may be used; family is context, never authority by itself."""

    exact_record_keys: tuple[str, ...] = ()
    internal_family: str | None = None
    candidate_classpath: str | None = None
    detail: str = ""

    def contains_exact_record(self, record_key: str) -> bool:
        return bool(record_key) and record_key in self.exact_record_keys


@dataclass(frozen=True, slots=True)
class AttributeProfileSlot:
    index: int
    source_key: str
    label: str
    expected_value_kind: AttributeValueKind | None = None
    expected_uom: str | None = None
    blank_allowed: bool = True

    def __post_init__(self) -> None:
        if self.index < 1:
            raise ValueError("attribute profile slots are 1-based")
        if not self.source_key.strip():
            raise ValueError("attribute profile slot needs a source_key")
        if not self.label.strip():
            raise ValueError("attribute profile slot needs a label")


@dataclass(frozen=True, slots=True)
class AttributeProfile:
    profile_id: str
    slots: tuple[AttributeProfileSlot, ...]
    authority: AttributeAuthority
    evidence: tuple[AttributeProfileEvidence, ...]
    scope: AttributeProfileScope

    def __post_init__(self) -> None:
        if not self.profile_id.strip():
            raise ValueError("attribute profile needs an identifier")
        if not self.slots:
            raise ValueError("attribute profile needs at least one ordered slot")
        indices = tuple(slot.index for slot in self.slots)
        if indices != tuple(sorted(indices)):
            raise ValueError("profile slots must already be in authoritative slot order")
        if len(indices) != len(set(indices)):
            raise ValueError("profile slot indices must be unique")
        keys = tuple(slot.source_key for slot in self.slots)
        if len(keys) != len(set(keys)):
            raise ValueError("profile source keys must be unique")

    def can_populate_labels(
        self, record_key: str, *, candidate_classpath: str | None = None
    ) -> bool:
        """A family hint alone never licenses labels in a delivery record."""
        if not self.authority.permits_profile_labels:
            return False
        if self.authority is AttributeAuthority.ORGANIZER_EXAMPLE:
            return self.scope.contains_exact_record(record_key)
        if self.authority in {
            AttributeAuthority.ORGANIZER_LOV,
            AttributeAuthority.HUMAN_APPROVED,
        }:
            return bool(
                self.scope.contains_exact_record(record_key)
                or (
                    candidate_classpath
                    and self.scope.candidate_classpath
                    and candidate_classpath == self.scope.candidate_classpath
                )
            )
        return False

    def slot_for(self, source_key: str) -> AttributeProfileSlot | None:
        return next((slot for slot in self.slots if slot.source_key == source_key), None)


@dataclass(frozen=True, slots=True)
class AttributeCandidate:
    source_key: str
    label: str
    value: UnilogAttributeValue | None
    decision: ClassificationDecision
    reason: AttributeReason
    authority: AttributeAuthority
    evidence: tuple[AttributeEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not self.source_key.strip():
            raise ValueError("attribute candidate needs a source_key")
        if not self.label.strip():
            raise ValueError("attribute candidate needs a label")
        if self.decision is ClassificationDecision.COMMIT and self.value is None:
            raise ValueError("a committed attribute candidate needs a value")

    @property
    def has_value_authority(self) -> bool:
        if not self.authority.permits_product_values:
            return False
        if self.authority is AttributeAuthority.MANUFACTURER_EVIDENCE:
            return any(item.licenses_manufacturer_value for item in self.evidence)
        return True

    @property
    def is_delivery_eligible(self) -> bool:
        return bool(
            self.decision is ClassificationDecision.COMMIT
            and self.value is not None
            and self.value.uom_is_resolved
            and self.has_value_authority
        )

    def sort_key(self) -> tuple[str, ...]:
        value = self.value
        return (
            self.source_key,
            self.label,
            self.authority.value,
            self.decision.value,
            value.raw_value if value else "",
            value.raw_uom if value else "",
        )


@dataclass(frozen=True, slots=True)
class AttributeResolution:
    source_key: str
    label: str
    decision: ClassificationDecision
    reason: AttributeReason
    candidate: AttributeCandidate | None = None
    candidates: tuple[AttributeCandidate, ...] = ()


@dataclass(frozen=True, slots=True)
class MappedAttributeSlot:
    index: int
    label: str
    value: str
    uom: str


@dataclass(frozen=True, slots=True)
class AttributeMapping:
    profile: AttributeProfile
    record_key: str
    decision: ClassificationDecision
    reason: AttributeReason
    resolutions: tuple[AttributeResolution, ...]
    unmapped_candidates: tuple[AttributeCandidate, ...] = ()
    candidate_classpath: str | None = None

    def __post_init__(self) -> None:
        expected = tuple(slot.source_key for slot in self.profile.slots)
        actual = tuple(item.source_key for item in self.resolutions)
        if actual != expected:
            raise ValueError("attribute resolutions must match profile slot order exactly")

    @property
    def labels_authorized(self) -> bool:
        return self.profile.can_populate_labels(
            self.record_key, candidate_classpath=self.candidate_classpath
        )

    def delivery_slots(self) -> tuple[MappedAttributeSlot, ...]:
        if not self.labels_authorized:
            return ()
        by_key = {item.source_key: item for item in self.resolutions}
        output: list[MappedAttributeSlot] = []
        for slot in self.profile.slots:
            resolution = by_key[slot.source_key]
            candidate = resolution.candidate
            if (
                resolution.decision is ClassificationDecision.COMMIT
                and candidate is not None
                and candidate.is_delivery_eligible
                and candidate.value is not None
            ):
                value = candidate.value.delivery_value()
                uom = candidate.value.delivery_uom()
            else:
                value = ""
                uom = ""
            output.append(MappedAttributeSlot(slot.index, slot.label, value, uom))
        return tuple(output)


def _candidate_reason(candidate: AttributeCandidate) -> AttributeReason:
    if candidate.decision is ClassificationDecision.REVIEW:
        return AttributeReason.CANDIDATE_REQUIRES_REVIEW
    if candidate.decision is ClassificationDecision.WITHHOLD:
        return AttributeReason.CANDIDATE_WITHHELD
    if candidate.value is not None and not candidate.value.uom_is_resolved:
        return AttributeReason.UNKNOWN_UOM
    if (
        candidate.authority is AttributeAuthority.MANUFACTURER_EVIDENCE
        and not candidate.has_value_authority
    ):
        return AttributeReason.MANUFACTURER_EVIDENCE_UNVERIFIED
    if not candidate.has_value_authority:
        return AttributeReason.INSUFFICIENT_VALUE_AUTHORITY
    return AttributeReason.ELIGIBLE


def _resolve_slot(
    slot: AttributeProfileSlot, candidates: tuple[AttributeCandidate, ...]
) -> AttributeResolution:
    if not candidates:
        return AttributeResolution(
            slot.source_key,
            slot.label,
            ClassificationDecision.WITHHOLD,
            AttributeReason.NO_CANDIDATE,
        )
    ordered = tuple(sorted(candidates, key=AttributeCandidate.sort_key))
    if any(candidate.label != slot.label for candidate in ordered):
        return AttributeResolution(
            slot.source_key,
            slot.label,
            ClassificationDecision.REVIEW,
            AttributeReason.LABEL_MISMATCH,
            candidates=ordered,
        )

    if any(
        candidate.value is not None
        and slot.expected_value_kind is not None
        and candidate.value.value_kind is not slot.expected_value_kind
        for candidate in ordered
    ):
        return AttributeResolution(
            slot.source_key,
            slot.label,
            ClassificationDecision.REVIEW,
            AttributeReason.VALUE_KIND_MISMATCH,
            candidates=ordered,
        )
    if any(
        candidate.value is not None
        and slot.expected_uom is not None
        and candidate.value.normalized_uom != slot.expected_uom
        for candidate in ordered
    ):
        return AttributeResolution(
            slot.source_key,
            slot.label,
            ClassificationDecision.REVIEW,
            AttributeReason.UOM_MISMATCH,
            candidates=ordered,
        )

    valued = tuple(candidate for candidate in ordered if candidate.value is not None)
    semantic_values = {candidate.value.semantic_key() for candidate in valued if candidate.value}
    if len(semantic_values) > 1:
        return AttributeResolution(
            slot.source_key,
            slot.label,
            ClassificationDecision.REVIEW,
            AttributeReason.CONFLICTING_VALUES,
            candidates=ordered,
        )

    eligible = tuple(candidate for candidate in ordered if candidate.is_delivery_eligible)
    if eligible:
        winner = eligible[0]
        reason = (
            AttributeReason.DUPLICATE_AGREEMENT
            if len(valued) > 1
            else AttributeReason.ELIGIBLE
        )
        return AttributeResolution(
            slot.source_key,
            slot.label,
            ClassificationDecision.COMMIT,
            reason,
            candidate=winner,
            candidates=ordered,
        )

    candidate = ordered[0]
    reason = _candidate_reason(candidate)
    decision = (
        ClassificationDecision.REVIEW
        if any(item.decision is ClassificationDecision.REVIEW for item in ordered)
        or any(item.decision is ClassificationDecision.COMMIT for item in ordered)
        else ClassificationDecision.WITHHOLD
    )
    return AttributeResolution(
        slot.source_key,
        slot.label,
        decision,
        reason,
        candidates=ordered,
    )


def resolve_attribute_candidates(
    profile: AttributeProfile,
    candidates: Iterable[AttributeCandidate],
    *,
    record_key: str,
    candidate_classpath: str | None = None,
) -> AttributeMapping:
    """Resolve unordered candidates against explicit profile order, fail closed."""
    grouped: dict[str, list[AttributeCandidate]] = defaultdict(list)
    unknown: list[AttributeCandidate] = []
    known_keys = {slot.source_key for slot in profile.slots}
    for candidate in candidates:
        if candidate.source_key in known_keys:
            grouped[candidate.source_key].append(candidate)
        else:
            unknown.append(candidate)

    resolutions = tuple(
        _resolve_slot(slot, tuple(grouped.get(slot.source_key, ()))) for slot in profile.slots
    )
    unknown_ordered = tuple(sorted(unknown, key=AttributeCandidate.sort_key))
    if not profile.authority.permits_profile_labels:
        decision = ClassificationDecision.WITHHOLD
        reason = AttributeReason.PROFILE_AUTHORITY_INSUFFICIENT
    elif not profile.can_populate_labels(
        record_key, candidate_classpath=candidate_classpath
    ):
        decision = ClassificationDecision.WITHHOLD
        reason = AttributeReason.PROFILE_OUT_OF_SCOPE
    elif any(item.decision is ClassificationDecision.REVIEW for item in resolutions):
        decision = ClassificationDecision.REVIEW
        reason = next(
            item.reason
            for item in resolutions
            if item.decision is ClassificationDecision.REVIEW
        )
    else:
        decision = ClassificationDecision.COMMIT
        reason = AttributeReason.ELIGIBLE
    return AttributeMapping(
        profile=profile,
        record_key=record_key,
        decision=decision,
        reason=reason,
        resolutions=resolutions,
        unmapped_candidates=unknown_ordered,
        candidate_classpath=candidate_classpath,
    )


@dataclass(frozen=True, slots=True)
class OrganizerAttributeSlot:
    index: int
    label: str
    value: str
    uom: str


@dataclass(frozen=True, slots=True)
class OrganizerAttributeExample:
    record_key: str
    example_number: int
    slots: tuple[OrganizerAttributeSlot, ...]
    source_locator: str
    candidate_classpath: str | None = None

    @property
    def labels_populated(self) -> int:
        return sum(bool(slot.label) for slot in self.slots)

    @property
    def values_populated(self) -> int:
        return sum(bool(slot.value) for slot in self.slots)

    @property
    def uoms_populated(self) -> int:
        return sum(bool(slot.uom) for slot in self.slots)

    def candidates_for(self, profile: AttributeProfile) -> tuple[AttributeCandidate, ...]:
        candidates: list[AttributeCandidate] = []
        profile_by_index = {slot.index: slot for slot in profile.slots}
        for observed in self.slots:
            if not observed.label or not observed.value:
                continue
            slot = profile_by_index.get(observed.index)
            if slot is None or slot.label != observed.label:
                raise ValueError(
                    f"example {self.record_key!r} does not match profile slot "
                    f"{observed.index}"
                )
            candidates.append(
                AttributeCandidate(
                    source_key=slot.source_key,
                    label=slot.label,
                    value=parse_text(observed.value, raw_uom=observed.uom),
                    decision=ClassificationDecision.COMMIT,
                    reason=AttributeReason.ORGANIZER_EXAMPLE_VALUE,
                    authority=AttributeAuthority.ORGANIZER_EXAMPLE,
                )
            )
        return tuple(candidates)


@dataclass(frozen=True, slots=True)
class OrganizerAttributeCatalog:
    schema: DeliverySchema
    examples: tuple[OrganizerAttributeExample, ...]
    source_locator: str

    def example(self, record_key: str) -> OrganizerAttributeExample | None:
        return next((row for row in self.examples if row.record_key == record_key), None)

    def derive_profile(
        self,
        *,
        profile_id: str | None = None,
        internal_family: str | None = None,
    ) -> AttributeProfile:
        if not self.examples:
            raise ValueError("cannot derive an attribute profile without organizer examples")
        sequences = tuple(
            tuple((slot.index, slot.label) for slot in row.slots if slot.label)
            for row in self.examples
        )
        if any(sequence != sequences[0] for sequence in sequences[1:]):
            raise ValueError("organizer examples do not share one ordered label sequence")

        classpaths = {row.candidate_classpath for row in self.examples if row.candidate_classpath}
        candidate_classpath = next(iter(classpaths)) if len(classpaths) == 1 else None
        slots: list[AttributeProfileSlot] = []
        for index, label in sequences[0]:
            observed = tuple(
                next(slot for slot in row.slots if slot.index == index)
                for row in self.examples
            )
            value_uoms = tuple(item.uom for item in observed if item.value)
            expected_uom = (
                value_uoms[0]
                if value_uoms and all(unit == value_uoms[0] and unit for unit in value_uoms)
                else None
            )
            slots.append(
                AttributeProfileSlot(
                    index=index,
                    source_key=f"organizer-slot:{index}",
                    label=label,
                    expected_uom=expected_uom,
                    blank_allowed=True,
                )
            )

        record_keys = tuple(row.record_key for row in self.examples)
        if profile_id is None:
            payload = json.dumps(
                {"records": record_keys, "slots": sequences[0]},
                ensure_ascii=False,
                separators=(",", ":"),
            )
            profile_id = "organizer-example:" + hashlib.sha256(
                payload.encode("utf-8")
            ).hexdigest()[:16]
        return AttributeProfile(
            profile_id=profile_id,
            slots=tuple(slots),
            authority=AttributeAuthority.ORGANIZER_EXAMPLE,
            evidence=(
                AttributeProfileEvidence(
                    source_locator=self.source_locator,
                    observed_record_keys=record_keys,
                    detail="shared ordered labels observed in supplied organizer examples",
                ),
            ),
            scope=AttributeProfileScope(
                exact_record_keys=record_keys,
                internal_family=internal_family,
                candidate_classpath=candidate_classpath,
                detail="exact organizer example records only",
            ),
        )


def organizer_attribute_example(
    row: Mapping[str, str],
    schema: DeliverySchema,
    *,
    source_locator: str,
    example_number: int,
    record_key_field: str = "Mfg_Part_Num",
) -> OrganizerAttributeExample:
    if record_key_field not in row or not row[record_key_field]:
        raise ValueError(f"organizer example is missing {record_key_field!r}")
    slots = tuple(
        OrganizerAttributeSlot(
            index=spec.index,
            label=row.get(spec.label_field, ""),
            value=row.get(spec.value_field, ""),
            uom=row.get(spec.uom_field, ""),
        )
        for spec in schema.attribute_slots
    )
    malformed = tuple(
        slot.index
        for slot in slots
        if (slot.value or slot.uom) and not slot.label
    )
    if malformed:
        raise ValueError(
            f"organizer example has VALUE/UOM without LABEL in slots {malformed}"
        )
    return OrganizerAttributeExample(
        record_key=row[record_key_field],
        example_number=example_number,
        slots=slots,
        source_locator=source_locator,
        candidate_classpath=row.get("Classpath") or None,
    )


def load_organizer_attribute_catalog(
    path: str | Path, *, record_key_field: str = "Mfg_Part_Num"
) -> OrganizerAttributeCatalog:
    """Load all delivery triplets dynamically; no labels or slot count are hard-coded."""
    file = Path(path)
    schema = DeliverySchema.from_csv(file)
    with file.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    examples = tuple(
        organizer_attribute_example(
            row,
            schema,
            source_locator=file.name,
            example_number=index,
            record_key_field=record_key_field,
        )
        for index, row in enumerate(rows, start=1)
    )
    keys = tuple(row.record_key for row in examples)
    if len(keys) != len(set(keys)):
        raise ValueError("organizer attribute examples have duplicate record keys")
    return OrganizerAttributeCatalog(schema, examples, file.name)


def map_organizer_attribute_example(
    example: OrganizerAttributeExample, profile: AttributeProfile
) -> AttributeMapping:
    return resolve_attribute_candidates(
        profile,
        example.candidates_for(profile),
        record_key=example.record_key,
        candidate_classpath=example.candidate_classpath,
    )


__all__ = [
    "AttributeAuthority",
    "AttributeCandidate",
    "AttributeEvidence",
    "AttributeMapping",
    "AttributeProfile",
    "AttributeProfileEvidence",
    "AttributeProfileScope",
    "AttributeProfileSlot",
    "AttributeReason",
    "AttributeResolution",
    "AttributeValueKind",
    "DecimalRange",
    "MappedAttributeSlot",
    "OrganizerAttributeCatalog",
    "OrganizerAttributeExample",
    "OrganizerAttributeSlot",
    "UnilogAttributeValue",
    "UomResolution",
    "load_organizer_attribute_catalog",
    "map_organizer_attribute_example",
    "normalize_uom",
    "organizer_attribute_example",
    "parse_boolean",
    "parse_controlled_value",
    "parse_decimal",
    "parse_integer",
    "parse_number",
    "parse_number_with_unit",
    "parse_simple_range",
    "parse_text",
    "resolve_attribute_candidates",
]
