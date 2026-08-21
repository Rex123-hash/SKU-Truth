"""Conservative manufacturer and brand normalization with explicit authority.

The organizer's manufacturer and brand master is not present.  This module therefore
does not contain a built-in list and never treats string similarity as identity.  A
caller supplies exact canonical rules from an auditable source; everything else remains
a proposal for review.

Safe normalization is deliberately narrow: whitespace, case, punctuation, and common
legal suffixes may select an already-authorized rule.  They never create a rule.  If two
rules reduce to the same key, the result is review rather than an arbitrary winner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .input import RawProductRow
from .manufacturer import ManufacturerParse
from .placeholders import is_placeholder

_SPACE = re.compile(r"\s+")
_PUNCTUATION = re.compile(r"[^a-z0-9]+")
_LEGAL_SUFFIXES = frozenset(
    {
        "ag",
        "bv",
        "co",
        "company",
        "corp",
        "corporation",
        "gmbh",
        "inc",
        "incorporated",
        "limited",
        "llc",
        "ltd",
        "nv",
        "plc",
        "sa",
        "sas",
    }
)


class NormalizationSubject(StrEnum):
    MANUFACTURER = "MANUFACTURER"
    BRAND = "BRAND"


class NormalizationDecision(StrEnum):
    COMMIT = "COMMIT"
    REVIEW = "REVIEW"
    WITHHOLD = "WITHHOLD"


class AuthorityLevel(StrEnum):
    """Why a canonical value may be proposed; none means organizer-official."""

    SOURCE_EXACT = "SOURCE_EXACT"
    DATASET_CONSENSUS = "DATASET_CONSENSUS"
    EVIDENCE_SUPPORTED = "EVIDENCE_SUPPORTED"
    HUMAN_APPROVED = "HUMAN_APPROVED"
    UNRESOLVED = "UNRESOLVED"

    @property
    def permits_delivery(self) -> bool:
        """Whether this authority is sufficient for a canonical delivery field."""
        return self in {
            AuthorityLevel.DATASET_CONSENSUS,
            AuthorityLevel.EVIDENCE_SUPPORTED,
            AuthorityLevel.HUMAN_APPROVED,
        }


class NormalizationReason(StrEnum):
    EXACT_CANONICAL = "EXACT_CANONICAL"
    EXACT_ALIAS = "EXACT_ALIAS"
    WHITESPACE_NORMALIZED = "WHITESPACE_NORMALIZED"
    CASE_NORMALIZED = "CASE_NORMALIZED"
    PUNCTUATION_NORMALIZED = "PUNCTUATION_NORMALIZED"
    LEGAL_SUFFIX_NORMALIZED = "LEGAL_SUFFIX_NORMALIZED"
    BRAND_SOURCE_CONSENSUS = "BRAND_SOURCE_CONSENSUS"
    SINGLE_BRAND_SOURCE = "SINGLE_BRAND_SOURCE"
    CONFLICTING_BRAND_SOURCES = "CONFLICTING_BRAND_SOURCES"
    UNKNOWN_MANUFACTURER = "UNKNOWN_MANUFACTURER"
    UNKNOWN_BRAND = "UNKNOWN_BRAND"
    AMBIGUOUS_ALIAS = "AMBIGUOUS_ALIAS"
    MISSING_VALUE = "MISSING_VALUE"
    PLACEHOLDER = "PLACEHOLDER"
    AMBIGUOUS_MANUFACTURER = "AMBIGUOUS_MANUFACTURER"


@dataclass(frozen=True, slots=True)
class RawSignal:
    """One source field, preserved before and after placeholder cleaning."""

    field: str
    raw_value: str
    usable_value: str | None
    placeholder: bool


@dataclass(frozen=True, slots=True)
class AuthoritySource:
    """The provenance behind a proposal or decision."""

    authority: AuthorityLevel
    source: str
    detail: str = ""


@dataclass(frozen=True, slots=True)
class CanonicalRule:
    """A canonical value and exact aliases supplied by an auditable authority."""

    canonical_value: str
    aliases: tuple[str, ...]
    authority: AuthorityLevel
    source: str
    evidence: str = ""

    def __post_init__(self) -> None:
        if not self.canonical_value.strip():
            raise ValueError("canonical_value cannot be blank")
        if not self.source.strip():
            raise ValueError("a canonical rule must name its source")
        if self.authority in {AuthorityLevel.SOURCE_EXACT, AuthorityLevel.UNRESOLVED}:
            raise ValueError(
                f"{self.authority.value} cannot authorize a canonical rule"
            )

    @property
    def names(self) -> tuple[str, ...]:
        return (self.canonical_value, *self.aliases)


@dataclass(frozen=True, slots=True)
class RuleMatch:
    rule: CanonicalRule | None
    reason: NormalizationReason | None
    ambiguous_values: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class NormalizationResult:
    subject: NormalizationSubject
    raw_signals: tuple[RawSignal, ...]
    canonical_proposal: str | None
    decision: NormalizationDecision
    reason: NormalizationReason
    authority: AuthorityLevel
    authority_sources: tuple[AuthoritySource, ...]

    @property
    def delivery_value(self) -> str | None:
        """A publishable value, or ``None`` when review/withholding is required."""
        if (
            self.decision is NormalizationDecision.COMMIT
            and self.authority.permits_delivery
        ):
            return self.canonical_proposal
        return None


@dataclass(frozen=True, slots=True)
class RowNormalization:
    row_number: int
    manufacturer: NormalizationResult
    brand: NormalizationResult


def _trimmed(value: str) -> str:
    return _SPACE.sub(" ", value.strip())


def _case_key(value: str) -> str:
    return _trimmed(value).casefold()


def _punctuation_key(value: str) -> str:
    return " ".join(_PUNCTUATION.sub(" ", _case_key(value)).split())


def _manufacturer_key(value: str) -> str:
    tokens = _punctuation_key(value).split()
    kept = [token for token in tokens if token not in _LEGAL_SUFFIXES]
    return " ".join(kept or tokens)


class CanonicalCatalog:
    """A deterministic rule index. Collisions remain visible as ambiguity."""

    def __init__(self, rules: tuple[CanonicalRule, ...] = ()) -> None:
        self.rules = tuple(rules)

    def match(self, value: str, *, manufacturer: bool) -> RuleMatch:
        stages = (
            (NormalizationReason.EXACT_CANONICAL, lambda x: x),
            (NormalizationReason.WHITESPACE_NORMALIZED, _trimmed),
            (NormalizationReason.CASE_NORMALIZED, _case_key),
            (NormalizationReason.PUNCTUATION_NORMALIZED, _punctuation_key),
        )
        for reason, transform in stages:
            needle = transform(value)
            matches: list[tuple[CanonicalRule, bool]] = []
            for rule in self.rules:
                for index, name in enumerate(rule.names):
                    if transform(name) == needle:
                        matches.append((rule, index > 0))
                        break
            if matches:
                return _finish_matches(matches, reason)

        if manufacturer:
            needle = _manufacturer_key(value)
            matches = []
            for rule in self.rules:
                for index, name in enumerate(rule.names):
                    if _manufacturer_key(name) == needle:
                        matches.append((rule, index > 0))
                        break
            if matches:
                return _finish_matches(
                    matches, NormalizationReason.LEGAL_SUFFIX_NORMALIZED
                )
        return RuleMatch(rule=None, reason=None)


def _finish_matches(
    matches: list[tuple[CanonicalRule, bool]], reason: NormalizationReason
) -> RuleMatch:
    unique = {match.canonical_value: match for match, _ in matches}
    if len(unique) != 1:
        return RuleMatch(
            rule=None,
            reason=NormalizationReason.AMBIGUOUS_ALIAS,
            ambiguous_values=tuple(sorted(unique)),
        )
    rule = next(iter(unique.values()))
    alias_matched = any(is_alias for match, is_alias in matches if match is rule)
    if reason is NormalizationReason.EXACT_CANONICAL and alias_matched:
        reason = NormalizationReason.EXACT_ALIAS
    return RuleMatch(rule=rule, reason=reason)


class DeterministicNormalizer:
    """Normalize rows using only injected rules and exact source agreement."""

    def __init__(
        self,
        *,
        manufacturers: CanonicalCatalog | None = None,
        brands: CanonicalCatalog | None = None,
    ) -> None:
        self.manufacturers = manufacturers or CanonicalCatalog()
        self.brands = brands or CanonicalCatalog()

    def normalize(self, row: RawProductRow) -> RowNormalization:
        return RowNormalization(
            row_number=row.row_number,
            manufacturer=self.normalize_manufacturer(row),
            brand=self.normalize_brand(row),
        )

    def normalize_manufacturer(self, row: RawProductRow) -> NormalizationResult:
        parsed = row.manufacturer
        signal = _signal(row, "Part_Manuf")
        sources = (
            AuthoritySource(
                authority=AuthorityLevel.SOURCE_EXACT,
                source=f"organizer row {row.row_number}:Part_Manuf",
                detail=f"structural parse={parsed.status.value}",
            ),
        )
        if parsed.status is ManufacturerParse.PLACEHOLDER:
            return _withheld(
                NormalizationSubject.MANUFACTURER,
                (signal,),
                NormalizationReason.PLACEHOLDER,
                sources,
            )
        if parsed.status is ManufacturerParse.MISSING:
            return _withheld(
                NormalizationSubject.MANUFACTURER,
                (signal,),
                NormalizationReason.MISSING_VALUE,
                sources,
            )
        if parsed.status is ManufacturerParse.UNRESOLVED or not parsed.display_name:
            return _withheld(
                NormalizationSubject.MANUFACTURER,
                (signal,),
                NormalizationReason.AMBIGUOUS_MANUFACTURER,
                sources,
            )

        match = self.manufacturers.match(parsed.display_name, manufacturer=True)
        if match.reason is NormalizationReason.AMBIGUOUS_ALIAS:
            detail = "candidate canonical values: " + ", ".join(match.ambiguous_values)
            return NormalizationResult(
                subject=NormalizationSubject.MANUFACTURER,
                raw_signals=(signal,),
                canonical_proposal=None,
                decision=NormalizationDecision.REVIEW,
                reason=NormalizationReason.AMBIGUOUS_ALIAS,
                authority=AuthorityLevel.UNRESOLVED,
                authority_sources=(
                    *sources,
                    AuthoritySource(
                        AuthorityLevel.UNRESOLVED, "catalog collision", detail
                    ),
                ),
            )
        if match.rule is not None and match.reason is not None:
            rule = match.rule
            return NormalizationResult(
                subject=NormalizationSubject.MANUFACTURER,
                raw_signals=(signal,),
                canonical_proposal=rule.canonical_value,
                decision=(
                    NormalizationDecision.COMMIT
                    if rule.authority.permits_delivery
                    else NormalizationDecision.REVIEW
                ),
                reason=match.reason,
                authority=rule.authority,
                authority_sources=(
                    *sources,
                    AuthoritySource(rule.authority, rule.source, rule.evidence),
                ),
            )

        return NormalizationResult(
            subject=NormalizationSubject.MANUFACTURER,
            raw_signals=(signal,),
            canonical_proposal=parsed.display_name,
            decision=NormalizationDecision.REVIEW,
            reason=NormalizationReason.UNKNOWN_MANUFACTURER,
            authority=AuthorityLevel.SOURCE_EXACT,
            authority_sources=sources,
        )

    def normalize_brand(self, row: RawProductRow) -> NormalizationResult:
        signals = tuple(_signal(row, field) for field in ("E1_Brand", "Unilog_Brand", "DIB_Brand"))
        usable = tuple(signal.usable_value for signal in signals if signal.usable_value)
        source_records = tuple(
            AuthoritySource(
                AuthorityLevel.SOURCE_EXACT,
                f"organizer row {row.row_number}:{signal.field}",
            )
            for signal in signals
        )
        if not usable:
            reason = (
                NormalizationReason.PLACEHOLDER
                if any(signal.placeholder for signal in signals)
                else NormalizationReason.MISSING_VALUE
            )
            return _withheld(
                NormalizationSubject.BRAND, signals, reason, source_records
            )

        comparison_keys = {_punctuation_key(value) for value in usable}
        if len(usable) > 1 and len(comparison_keys) == 1:
            proposal = usable[0]
            return NormalizationResult(
                subject=NormalizationSubject.BRAND,
                raw_signals=signals,
                canonical_proposal=proposal,
                decision=NormalizationDecision.COMMIT,
                reason=NormalizationReason.BRAND_SOURCE_CONSENSUS,
                authority=AuthorityLevel.DATASET_CONSENSUS,
                authority_sources=(
                    *source_records,
                    AuthoritySource(
                        AuthorityLevel.DATASET_CONSENSUS,
                        "independent organizer brand fields",
                        "two or more non-placeholder fields agree after case/punctuation folding",
                    ),
                ),
            )
        if len(comparison_keys) > 1:
            return NormalizationResult(
                subject=NormalizationSubject.BRAND,
                raw_signals=signals,
                canonical_proposal=None,
                decision=NormalizationDecision.REVIEW,
                reason=NormalizationReason.CONFLICTING_BRAND_SOURCES,
                authority=AuthorityLevel.UNRESOLVED,
                authority_sources=source_records,
            )

        proposal = usable[0]
        match = self.brands.match(proposal, manufacturer=False)
        if match.reason is NormalizationReason.AMBIGUOUS_ALIAS:
            return NormalizationResult(
                subject=NormalizationSubject.BRAND,
                raw_signals=signals,
                canonical_proposal=None,
                decision=NormalizationDecision.REVIEW,
                reason=NormalizationReason.AMBIGUOUS_ALIAS,
                authority=AuthorityLevel.UNRESOLVED,
                authority_sources=source_records,
            )
        if match.rule is not None and match.reason is not None:
            rule = match.rule
            return NormalizationResult(
                subject=NormalizationSubject.BRAND,
                raw_signals=signals,
                canonical_proposal=rule.canonical_value,
                decision=(
                    NormalizationDecision.COMMIT
                    if rule.authority.permits_delivery
                    else NormalizationDecision.REVIEW
                ),
                reason=match.reason,
                authority=rule.authority,
                authority_sources=(
                    *source_records,
                    AuthoritySource(rule.authority, rule.source, rule.evidence),
                ),
            )
        return NormalizationResult(
            subject=NormalizationSubject.BRAND,
            raw_signals=signals,
            canonical_proposal=proposal,
            decision=NormalizationDecision.REVIEW,
            reason=(
                NormalizationReason.SINGLE_BRAND_SOURCE
                if len(usable) == 1
                else NormalizationReason.UNKNOWN_BRAND
            ),
            authority=AuthorityLevel.SOURCE_EXACT,
            authority_sources=source_records,
        )


def _signal(row: RawProductRow, field: str) -> RawSignal:
    raw = row.raw_value(field)
    return RawSignal(
        field=field,
        raw_value=raw,
        usable_value=row.cleaned(field),
        placeholder=is_placeholder(field, raw),
    )


def _withheld(
    subject: NormalizationSubject,
    signals: tuple[RawSignal, ...],
    reason: NormalizationReason,
    sources: tuple[AuthoritySource, ...],
) -> NormalizationResult:
    return NormalizationResult(
        subject=subject,
        raw_signals=signals,
        canonical_proposal=None,
        decision=NormalizationDecision.WITHHOLD,
        reason=reason,
        authority=AuthorityLevel.UNRESOLVED,
        authority_sources=sources,
    )


def reviewed_manufacturer_catalog(registry: object, *, source: str) -> CanonicalCatalog:
    """Adapt human-reviewed domain entries into manufacturer-name rules.

    The adapter uses only entries the registry says license evidence and only their
    authority hints. Locator hints are intentionally excluded.  This establishes the
    manufacturer name/domain binding; it does not establish any product-level fact.
    """
    rules: list[CanonicalRule] = []
    for entry in registry.licensing_entries:  # type: ignore[attr-defined]
        if not entry.authority_hints or entry.review is None:
            continue
        rules.append(
            CanonicalRule(
                canonical_value=entry.authority_hints[0],
                aliases=tuple(entry.authority_hints[1:]),
                authority=AuthorityLevel.HUMAN_APPROVED,
                source=f"{source}:{entry.key}",
                evidence=entry.review.describe(),
            )
        )
    return CanonicalCatalog(tuple(rules))


__all__ = [
    "AuthorityLevel",
    "AuthoritySource",
    "CanonicalCatalog",
    "CanonicalRule",
    "DeterministicNormalizer",
    "NormalizationDecision",
    "NormalizationReason",
    "NormalizationResult",
    "NormalizationSubject",
    "RawSignal",
    "RowNormalization",
    "reviewed_manufacturer_catalog",
]
