"""Conservative internal product-family classification and scoped classpath mapping.

Internal families are SKUTruth routing labels, not organizer taxonomy values.  They are
selected only by inspectable token/phrase rules over ``Part_Desc``.  Manufacturer and
brand normalization are preserved as context but never classify a row by themselves.

Delivery classification is a separate decision.  The two organizer output rows are
record-scoped examples, not a taxonomy LOV, so their values may be replayed only onto an
input row whose six passthrough fields match that example exactly.  All other delivery
classification fields remain blank until an organizer LOV or human-approved mapping is
available.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .input import REQUIRED_COLUMNS, RawProductRow
from .normalization import RowNormalization
from .placeholders import is_placeholder

DELIVERY_CLASSIFICATION_FIELDS: tuple[str, ...] = (
    "Dept",
    "Class",
    "Fine",
    "Classpath",
    "UNSPSC",
)

_TOKEN = re.compile(r"[a-z0-9]+")


class InternalProductFamily(StrEnum):
    DISHWASHER = "DISHWASHER"
    APPLIANCE = "APPLIANCE"
    LIGHTING = "LIGHTING"
    DECKING_LUMBER = "DECKING_LUMBER"
    POWER_TOOL_ACCESSORY = "POWER_TOOL_ACCESSORY"
    POWER_TOOL = "POWER_TOOL"
    ELECTRICAL = "ELECTRICAL"
    SAFETY_EQUIPMENT = "SAFETY_EQUIPMENT"
    UNKNOWN = "UNKNOWN"


class ClassificationDecision(StrEnum):
    COMMIT = "COMMIT"
    REVIEW = "REVIEW"
    WITHHOLD = "WITHHOLD"


class ClassificationAuthority(StrEnum):
    """What supports a classification; organizer examples are explicitly scoped."""

    ORGANIZER_EXAMPLE = "ORGANIZER_EXAMPLE"
    ORGANIZER_LOV = "ORGANIZER_LOV"
    ETIM_REFERENCE = "ETIM_REFERENCE"
    DETERMINISTIC_INTERNAL = "DETERMINISTIC_INTERNAL"
    MODEL_PROPOSAL = "MODEL_PROPOSAL"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    UNRESOLVED = "UNRESOLVED"

    @property
    def permits_delivery(self) -> bool:
        return self in {
            ClassificationAuthority.ORGANIZER_EXAMPLE,
            ClassificationAuthority.ORGANIZER_LOV,
            ClassificationAuthority.HUMAN_APPROVED,
        }


class ClassificationReason(StrEnum):
    STRONG_LEXICAL_CUE = "STRONG_LEXICAL_CUE"
    SPECIFIC_FAMILY_PRECEDENCE = "SPECIFIC_FAMILY_PRECEDENCE"
    OVERLAPPING_FAMILY_CUES = "OVERLAPPING_FAMILY_CUES"
    INSUFFICIENT_DESCRIPTION = "INSUFFICIENT_DESCRIPTION"
    NO_FAMILY_CUE = "NO_FAMILY_CUE"
    PLACEHOLDER_DESCRIPTION = "PLACEHOLDER_DESCRIPTION"
    EXACT_ORGANIZER_EXAMPLE = "EXACT_ORGANIZER_EXAMPLE"
    NO_DELIVERY_TAXONOMY_AUTHORITY = "NO_DELIVERY_TAXONOMY_AUTHORITY"


@dataclass(frozen=True, slots=True)
class ClassificationEvidence:
    raw_description: str
    normalized_description: str
    matched_cues: tuple[str, ...]
    source: str
    authority: ClassificationAuthority
    manufacturer_context: str | None = None
    brand_context: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True, slots=True)
class DeliveryClassificationValues:
    """Only the organizer's existing classification columns; no schema extension."""

    values: tuple[tuple[str, str], ...]

    def __post_init__(self) -> None:
        unknown = sorted(
            field for field, _ in self.values if field not in DELIVERY_CLASSIFICATION_FIELDS
        )
        duplicates = sorted(
            {field for field, _ in self.values if sum(f == field for f, _ in self.values) > 1}
        )
        if unknown:
            raise ValueError(f"unknown delivery classification fields: {unknown}")
        if duplicates:
            raise ValueError(f"duplicate delivery classification fields: {duplicates}")

    def get(self, field: str) -> str:
        return next((value for name, value in self.values if name == field), "")

    def populated(self) -> tuple[tuple[str, str], ...]:
        return tuple((field, value) for field, value in self.values if value.strip())


@dataclass(frozen=True, slots=True)
class DeliveryClassificationProposal:
    values: DeliveryClassificationValues | None
    decision: ClassificationDecision
    authority: ClassificationAuthority
    reason: ClassificationReason
    evidence: tuple[ClassificationEvidence, ...]

    @property
    def delivery_values(self) -> tuple[tuple[str, str], ...]:
        if (
            self.decision is ClassificationDecision.COMMIT
            and self.authority.permits_delivery
            and self.values is not None
        ):
            return self.values.populated()
        return ()

    @property
    def classpath(self) -> str | None:
        value = self.values.get("Classpath") if self.values is not None else ""
        return value or None


@dataclass(frozen=True, slots=True)
class ClassificationProposal:
    row_number: int
    raw_description: str
    normalized_cues: tuple[str, ...]
    internal_family: InternalProductFamily
    candidate_families: tuple[InternalProductFamily, ...]
    decision: ClassificationDecision
    authority: ClassificationAuthority
    reason: ClassificationReason
    evidence: tuple[ClassificationEvidence, ...]
    delivery: DeliveryClassificationProposal

    @property
    def is_high_confidence(self) -> bool:
        return (
            self.decision is ClassificationDecision.COMMIT
            and self.authority is ClassificationAuthority.DETERMINISTIC_INTERNAL
        )


def tokenize(value: str | None) -> tuple[str, ...]:
    return tuple(_TOKEN.findall((value or "").casefold()))


def _contains(tokens: tuple[str, ...], phrase: str) -> bool:
    wanted = tokenize(phrase)
    size = len(wanted)
    return bool(wanted) and any(
        tokens[index : index + size] == wanted
        for index in range(len(tokens) - size + 1)
    )


@dataclass(frozen=True, slots=True)
class CuePattern:
    """Every phrase in one pattern must occur; patterns are alternatives."""

    phrases: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.phrases or any(not tokenize(phrase) for phrase in self.phrases):
            raise ValueError("a cue pattern needs one or more nonblank phrases")

    @property
    def label(self) -> str:
        return " + ".join(self.phrases)

    def matches(self, tokens: tuple[str, ...]) -> bool:
        return all(_contains(tokens, phrase) for phrase in self.phrases)


@dataclass(frozen=True, slots=True)
class LexicalFamilyRule:
    family: InternalProductFamily
    patterns: tuple[CuePattern, ...]

    def __post_init__(self) -> None:
        if self.family is InternalProductFamily.UNKNOWN:
            raise ValueError("UNKNOWN cannot have a lexical commit rule")
        if not self.patterns:
            raise ValueError(f"{self.family.value} needs at least one cue pattern")

    def matched_cues(self, tokens: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(pattern.label for pattern in self.patterns if pattern.matches(tokens))


def _patterns(*patterns: str | tuple[str, ...]) -> tuple[CuePattern, ...]:
    return tuple(
        CuePattern((pattern,) if isinstance(pattern, str) else pattern)
        for pattern in patterns
    )


# Phrases come from the supplied 1,000-row sample. They are internal routing rules, not
# claims about the organizer's taxonomy. Exact token matching prevents `lt` in `Dewalt`
# and `led` in `assembled` from becoming lighting evidence.
DEFAULT_FAMILY_RULES: tuple[LexicalFamilyRule, ...] = (
    LexicalFamilyRule(
        InternalProductFamily.DISHWASHER,
        _patterns("dishwasher"),
    ),
    LexicalFamilyRule(
        InternalProductFamily.APPLIANCE,
        _patterns(
            "dryer",
            "washer",
            "freezer",
            "fridge",
            "microwave",
            "mocrowave",
            "cooktop",
            "toaster",
            "espresso",
            "beverage center",
            "coffee maker",
            "laundry center",
            "wall oven",
            "toast oven",
            "electric range",
            "elect range",
            "elec range",
            "gas range",
            "heater kit",
        ),
    ),
    LexicalFamilyRule(
        InternalProductFamily.LIGHTING,
        _patterns(
            "lamp",
            "bulb",
            "chandelier",
            "chand",
            "pendant",
            "sconce",
            "highbay",
            "flashlt",
            "incan",
            "halogen",
            "flor",
            "sodium",
            "wall light",
            "wall lt",
            "bath light",
            "bath lt",
            "ceiling light",
            "ceiling lt",
            "post light",
            "post lt",
            "down light",
            "downlight",
            "strip light",
            "tape light",
            "motion light",
            "motion lt",
            "shop light",
            "work light",
            "clip light",
            "flash light",
            "rechargeable light",
            ("led", "a19"),
            ("led", "med"),
            ("led", "cand"),
            ("led", "retro"),
            ("led", "cob"),
            ("led", "light"),
            ("led", "lt"),
        ),
    ),
    LexicalFamilyRule(
        InternalProductFamily.DECKING_LUMBER,
        _patterns(
            "decking",
            "fascia",
            "baluster",
            "drywall",
            "mortar",
            "rainscreen",
            "hardie",
            "rail kit",
            "rail panel",
            "deck joist",
            "patio dr",
            "doug fir",
            "post wrap",
            "post trim",
            "post cap",
            "gate sq bal",
            "alum post",
        ),
    ),
    LexicalFamilyRule(
        InternalProductFamily.POWER_TOOL_ACCESSORY,
        _patterns(
            "disc",
            "blade",
            "bit",
            "abrasive",
            "abranet",
            "fence",
            "staple",
            "nail",
            "grinding wheel",
            "sanding belt",
            "sanding sponge",
            "stikit film",
            "socket adapter",
            "starter kit",
            "zero clearance insert",
            "dado pro set",
            "saw plate",
            ("battery", "20v"),
            ("battery", "18v"),
            ("battery", "starter"),
            ("battery", "powerpack"),
            ("battery", "mount"),
        ),
    ),
    LexicalFamilyRule(
        InternalProductFamily.POWER_TOOL,
        _patterns(
            "drill",
            "jigsaw",
            "sander",
            "bandsaw",
            "planer",
            "jointer",
            "shaper",
            "trimmer",
            "nailer",
            "screwdriver",
            "vacuum",
            "grinder",
            "saw",
            "grease gun",
            "rotary tool",
            "impact driver",
            "drill press",
            "stock feeder",
        ),
    ),
    LexicalFamilyRule(
        InternalProductFamily.ELECTRICAL,
        _patterns(
            "outlet",
            "outler",
            "dimmer",
            "gfci",
            "gfi",
            "wire",
            "switch",
            "wallplate",
            "timer",
            "load center",
            "load cntr",
            "box cover",
            "wall tap",
            "elect tape",
            "cord grip",
            "cord conn",
            "entrance cable",
            "decor plate",
            "voltage detector",
        ),
    ),
    LexicalFamilyRule(
        InternalProductFamily.SAFETY_EQUIPMENT,
        _patterns(
            "glove",
            "alarm",
            "extinguisher",
            "safety glasses",
            "hearing protector",
            "kneeling pad",
        ),
    ),
)


@dataclass(frozen=True, slots=True)
class OrganizerExampleRule:
    """One exact organizer output example; never a family-wide taxonomy rule."""

    input_values: tuple[tuple[str, str], ...]
    delivery_values: DeliveryClassificationValues
    source: str
    example_number: int

    def matches(self, row: RawProductRow) -> bool:
        return all(row.raw_value(field) == value for field, value in self.input_values)


class OrganizerExampleCatalog:
    def __init__(self, rules: tuple[OrganizerExampleRule, ...] = ()) -> None:
        self.rules = tuple(rules)

    def match(self, row: RawProductRow) -> OrganizerExampleRule | None:
        matches = [rule for rule in self.rules if rule.matches(row)]
        if len(matches) > 1:
            raise ValueError(
                f"row {row.row_number} matches multiple organizer examples; "
                "example authority must be record-specific"
            )
        return matches[0] if matches else None


def organizer_example_rule(
    row: Mapping[str, str], *, source: str, example_number: int
) -> OrganizerExampleRule:
    missing = [field for field in REQUIRED_COLUMNS if field not in row]
    missing += [field for field in DELIVERY_CLASSIFICATION_FIELDS if field not in row]
    if missing:
        raise ValueError(f"organizer example is missing fields: {sorted(set(missing))}")
    return OrganizerExampleRule(
        input_values=tuple((field, row[field]) for field in REQUIRED_COLUMNS),
        delivery_values=DeliveryClassificationValues(
            tuple((field, row[field]) for field in DELIVERY_CLASSIFICATION_FIELDS)
        ),
        source=source,
        example_number=example_number,
    )


def load_organizer_example_catalog(path: str | Path) -> OrganizerExampleCatalog:
    file = Path(path)
    with file.open(encoding="utf-8-sig", newline="") as handle:
        rows = tuple(csv.DictReader(handle))
    return OrganizerExampleCatalog(
        tuple(
            organizer_example_rule(
                row,
                source=file.name,
                example_number=index,
            )
            for index, row in enumerate(rows, start=1)
        )
    )


class DeterministicProductClassifier:
    """Classify internal family and independently assess delivery taxonomy authority."""

    def __init__(
        self,
        *,
        rules: Iterable[LexicalFamilyRule] = DEFAULT_FAMILY_RULES,
        organizer_examples: OrganizerExampleCatalog | None = None,
        insufficient_content_tokens: int = 2,
    ) -> None:
        self.rules = tuple(rules)
        self.organizer_examples = organizer_examples or OrganizerExampleCatalog()
        self.insufficient_content_tokens = insufficient_content_tokens

    def classify(
        self,
        row: RawProductRow,
        *,
        normalization: RowNormalization | None = None,
    ) -> ClassificationProposal:
        raw = row.raw_value("Part_Desc")
        tokens = tokenize(row.part_desc)
        content_tokens = _without_mpn_prefix(tokens, tokenize(row.mfg_part_num))
        matches: dict[InternalProductFamily, tuple[str, ...]] = {}
        for rule in self.rules:
            matched = rule.matched_cues(tokens)
            if matched:
                matches[rule.family] = matched
        matches, precedence_applied = _apply_specificity(matches)
        cues = tuple(
            sorted({cue for family_cues in matches.values() for cue in family_cues})
        )
        context = _context_evidence(row, normalization, tokens, cues)

        if row.part_desc is None and is_placeholder("Part_Desc", raw):
            family = InternalProductFamily.UNKNOWN
            candidates: tuple[InternalProductFamily, ...] = ()
            decision = ClassificationDecision.WITHHOLD
            authority = ClassificationAuthority.UNRESOLVED
            reason = ClassificationReason.PLACEHOLDER_DESCRIPTION
        elif len(matches) == 1:
            family = next(iter(matches))
            candidates = (family,)
            decision = ClassificationDecision.COMMIT
            authority = ClassificationAuthority.DETERMINISTIC_INTERNAL
            reason = (
                ClassificationReason.SPECIFIC_FAMILY_PRECEDENCE
                if precedence_applied
                else ClassificationReason.STRONG_LEXICAL_CUE
            )
        elif len(matches) > 1:
            family = InternalProductFamily.UNKNOWN
            candidates = tuple(sorted(matches, key=lambda value: value.value))
            decision = ClassificationDecision.REVIEW
            authority = ClassificationAuthority.UNRESOLVED
            reason = ClassificationReason.OVERLAPPING_FAMILY_CUES
        else:
            family = InternalProductFamily.UNKNOWN
            candidates = ()
            decision = ClassificationDecision.WITHHOLD
            authority = ClassificationAuthority.UNRESOLVED
            reason = (
                ClassificationReason.INSUFFICIENT_DESCRIPTION
                if len(content_tokens) <= self.insufficient_content_tokens
                else ClassificationReason.NO_FAMILY_CUE
            )

        return ClassificationProposal(
            row_number=row.row_number,
            raw_description=raw,
            normalized_cues=cues,
            internal_family=family,
            candidate_families=candidates,
            decision=decision,
            authority=authority,
            reason=reason,
            evidence=(context,),
            delivery=self._delivery(row, context),
        )

    def _delivery(
        self, row: RawProductRow, context: ClassificationEvidence
    ) -> DeliveryClassificationProposal:
        example = self.organizer_examples.match(row)
        if example is None:
            return DeliveryClassificationProposal(
                values=None,
                decision=ClassificationDecision.WITHHOLD,
                authority=ClassificationAuthority.UNRESOLVED,
                reason=ClassificationReason.NO_DELIVERY_TAXONOMY_AUTHORITY,
                evidence=(context,),
            )
        evidence = ClassificationEvidence(
            raw_description=context.raw_description,
            normalized_description=context.normalized_description,
            matched_cues=context.matched_cues,
            source=f"{example.source}:example row {example.example_number}",
            authority=ClassificationAuthority.ORGANIZER_EXAMPLE,
            manufacturer_context=context.manufacturer_context,
            brand_context=context.brand_context,
            detail="all six organizer passthrough fields match the example exactly",
        )
        return DeliveryClassificationProposal(
            values=example.delivery_values,
            decision=ClassificationDecision.COMMIT,
            authority=ClassificationAuthority.ORGANIZER_EXAMPLE,
            reason=ClassificationReason.EXACT_ORGANIZER_EXAMPLE,
            evidence=(evidence,),
        )


def _without_mpn_prefix(
    description: tuple[str, ...], mpn: tuple[str, ...]
) -> tuple[str, ...]:
    if mpn and description[: len(mpn)] == mpn:
        return description[len(mpn) :]
    return description


def _apply_specificity(
    matches: dict[InternalProductFamily, tuple[str, ...]],
) -> tuple[dict[InternalProductFamily, tuple[str, ...]], bool]:
    reduced = dict(matches)
    applied = False
    # A dishwasher is a specific appliance product. An accessory phrase such as "saw
    # blade" identifies the accessory itself rather than the tool named inside it.
    precedence = (
        (InternalProductFamily.DISHWASHER, InternalProductFamily.APPLIANCE),
        (InternalProductFamily.POWER_TOOL_ACCESSORY, InternalProductFamily.POWER_TOOL),
    )
    for specific, general in precedence:
        if specific in reduced and general in reduced:
            reduced.pop(general)
            applied = True
    return reduced, applied


def _context_evidence(
    row: RawProductRow,
    normalization: RowNormalization | None,
    tokens: tuple[str, ...],
    cues: tuple[str, ...],
) -> ClassificationEvidence:
    manufacturer = None
    brands = row.brand_signals
    if normalization is not None:
        manufacturer = normalization.manufacturer.canonical_proposal
        brand = normalization.brand.canonical_proposal
        if brand and brand not in brands:
            brands = (*brands, brand)
    elif row.manufacturer.display_name:
        manufacturer = row.manufacturer.display_name
    return ClassificationEvidence(
        raw_description=row.raw_value("Part_Desc"),
        normalized_description=" ".join(tokens),
        matched_cues=cues,
        source=f"organizer row {row.row_number}:Part_Desc",
        authority=ClassificationAuthority.DETERMINISTIC_INTERNAL,
        manufacturer_context=manufacturer,
        brand_context=brands,
        detail="identity is recorded as context and is not a classification cue",
    )


__all__ = [
    "DEFAULT_FAMILY_RULES",
    "DELIVERY_CLASSIFICATION_FIELDS",
    "ClassificationAuthority",
    "ClassificationDecision",
    "ClassificationEvidence",
    "ClassificationProposal",
    "ClassificationReason",
    "CuePattern",
    "DeliveryClassificationProposal",
    "DeliveryClassificationValues",
    "DeterministicProductClassifier",
    "InternalProductFamily",
    "LexicalFamilyRule",
    "OrganizerExampleCatalog",
    "OrganizerExampleRule",
    "load_organizer_example_catalog",
    "organizer_example_rule",
    "tokenize",
]
