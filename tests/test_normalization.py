"""Deterministic manufacturer/brand normalization; all fixtures are synthetic."""

from __future__ import annotations

import csv
import io

from skutruth.unilog import (
    AuthorityLevel,
    CanonicalCatalog,
    CanonicalRule,
    DeliverySchema,
    DeterministicNormalizer,
    NormalizationDecision,
    NormalizationReason,
    RawProductRow,
    read_rows,
    record_from_raw_row,
    reviewed_manufacturer_catalog,
)

HEADER = "Mfg_Part_Num,Part_Desc,E1_Brand,Unilog_Brand,DIB_Brand,Part_Manuf"


def row(
    *,
    manufacturer: str = "Acme Tools (ACME)",
    e1: str = "-- Unbranded --",
    unilog: str = "-- No Unilog Brand --",
    dib: str = "-- No DIB Brand --",
) -> RawProductRow:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(HEADER.split(","))
    writer.writerow(["A1", "Widget", e1, unilog, dib, manufacturer])
    buffer.seek(0)
    return next(read_rows(buffer))


def rule(
    canonical: str = "Acme Tools",
    *,
    aliases: tuple[str, ...] = (),
    authority: AuthorityLevel = AuthorityLevel.HUMAN_APPROVED,
    source: str = "synthetic human review",
) -> CanonicalRule:
    return CanonicalRule(canonical, aliases, authority, source)


def normalizer(*rules: CanonicalRule) -> DeterministicNormalizer:
    return DeterministicNormalizer(manufacturers=CanonicalCatalog(tuple(rules)))


def test_exact_manufacturer_is_preserved():
    result = normalizer(rule()).normalize(row()).manufacturer
    assert result.decision is NormalizationDecision.COMMIT
    assert result.canonical_proposal == "Acme Tools"
    assert result.reason is NormalizationReason.EXACT_CANONICAL
    assert result.raw_signals[0].raw_value == "Acme Tools (ACME)"


def test_placeholder_is_withheld_without_losing_raw_value():
    result = normalizer(rule()).normalize(row(manufacturer="-")).manufacturer
    assert result.decision is NormalizationDecision.WITHHOLD
    assert result.reason is NormalizationReason.PLACEHOLDER
    assert result.raw_signals[0].raw_value == "-"


def test_whitespace_and_case_normalization_selects_only_an_authorized_rule():
    result = normalizer(rule()).normalize(
        row(manufacturer="  acme   tools  (ACME)")
    ).manufacturer
    assert result.decision is NormalizationDecision.COMMIT
    assert result.canonical_proposal == "Acme Tools"
    assert result.reason is NormalizationReason.CASE_NORMALIZED


def test_punctuation_normalization_is_conservative_and_audited():
    result = normalizer(rule("A-B Tools")).normalize(
        row(manufacturer="A B Tools (AB)")
    ).manufacturer
    assert result.decision is NormalizationDecision.COMMIT
    assert result.reason is NormalizationReason.PUNCTUATION_NORMALIZED


def test_legal_suffix_can_select_an_existing_canonical_rule():
    result = normalizer(rule("Acme")).normalize(
        row(manufacturer="Acme, Inc. (ACME)")
    ).manufacturer
    assert result.decision is NormalizationDecision.COMMIT
    assert result.canonical_proposal == "Acme"
    assert result.reason is NormalizationReason.LEGAL_SUFFIX_NORMALIZED


def test_exact_alias_mapping_uses_the_rule_canonical_value():
    result = normalizer(rule("Kichler Lighting", aliases=("Kichler",))).normalize(
        row(manufacturer="Kichler (KICLI)")
    ).manufacturer
    assert result.decision is NormalizationDecision.COMMIT
    assert result.canonical_proposal == "Kichler Lighting"
    assert result.reason is NormalizationReason.EXACT_ALIAS


def test_conflicting_brand_sources_require_review_and_preserve_both():
    result = normalizer().normalize(row(e1="Alpha", dib="Beta")).brand
    assert result.decision is NormalizationDecision.REVIEW
    assert result.reason is NormalizationReason.CONFLICTING_BRAND_SOURCES
    assert result.canonical_proposal is None
    assert [signal.raw_value for signal in result.raw_signals] == [
        "Alpha",
        "-- No Unilog Brand --",
        "Beta",
    ]


def test_missing_brand_is_withheld():
    result = normalizer().normalize(row()).brand
    assert result.decision is NormalizationDecision.WITHHOLD
    assert result.delivery_value is None


def test_malformed_manufacturer_is_ambiguous_and_withheld():
    result = normalizer(rule()).normalize(row(manufacturer="Acme (AC")).manufacturer
    assert result.decision is NormalizationDecision.WITHHOLD
    assert result.reason is NormalizationReason.AMBIGUOUS_MANUFACTURER


def test_alias_collision_stays_unresolved():
    rules = (
        rule("Alpha Industries", aliases=("Shared",)),
        rule("Beta Industries", aliases=("Shared",)),
    )
    result = normalizer(*rules).normalize(
        row(manufacturer="Shared (SHRD)")
    ).manufacturer
    assert result.decision is NormalizationDecision.REVIEW
    assert result.reason is NormalizationReason.AMBIGUOUS_ALIAS
    assert result.canonical_proposal is None


def test_repeated_execution_is_structurally_identical():
    subject = row(manufacturer="Acme, Inc. (ACME)", e1="Brand-X", dib="brand x")
    engine = normalizer(rule("Acme"))
    assert engine.normalize(subject) == engine.normalize(subject)


def test_no_silent_fuzzy_merge():
    result = normalizer(rule("Philips Lighting")).normalize(
        row(manufacturer="Phillips Lighting (5831)")
    ).manufacturer
    assert result.decision is NormalizationDecision.REVIEW
    assert result.reason is NormalizationReason.UNKNOWN_MANUFACTURER
    assert result.canonical_proposal == "Phillips Lighting"
    assert result.delivery_value is None


def test_delivery_record_maps_only_committed_identity_values():
    manufacturer_rule = rule("Acme Tools")
    brand_rule = rule("Acme Brand", source="synthetic brand review")
    engine = DeterministicNormalizer(
        manufacturers=CanonicalCatalog((manufacturer_rule,)),
        brands=CanonicalCatalog((brand_rule,)),
    )
    source = row(e1="Acme Brand")
    normalized = engine.normalize(source)
    schema = DeliverySchema(
        ["Part_Manuf", "E1_Brand", "MANUFACTURER_NAME", "BRAND_NAME"]
    )
    delivery = record_from_raw_row(source, schema, normalization=normalized)
    assert delivery.get("Part_Manuf") == "Acme Tools (ACME)"
    assert delivery.get("E1_Brand") == "Acme Brand"
    assert delivery.get("MANUFACTURER_NAME") == "Acme Tools"
    assert delivery.get("BRAND_NAME") == "Acme Brand"


def test_unknown_manufacturer_remains_unresolved_in_delivery():
    source = row(manufacturer="Unknown Works (UNKN)")
    normalized = normalizer().normalize(source)
    schema = DeliverySchema(["Part_Manuf", "MANUFACTURER_NAME"])
    delivery = record_from_raw_row(source, schema, normalization=normalized)
    assert normalized.manufacturer.decision is NormalizationDecision.REVIEW
    assert normalized.manufacturer.authority is AuthorityLevel.SOURCE_EXACT
    assert delivery.get("MANUFACTURER_NAME") == ""


def test_two_independent_brand_sources_can_form_dataset_consensus():
    result = normalizer().normalize(row(e1="Brand-X", dib="brand x")).brand
    assert result.decision is NormalizationDecision.COMMIT
    assert result.authority is AuthorityLevel.DATASET_CONSENSUS
    assert result.canonical_proposal == "Brand-X"
    assert result.delivery_value == "Brand-X"


def test_reviewed_registry_adapter_excludes_unreviewed_and_locator_hints():
    from skutruth.discovery.domains import parse_registry

    registry = parse_registry(
        {
            "name": "synthetic-reviewed",
            "authority": "REVIEWED",
            "manufacturer": [
                {
                    "key": "approved",
                    "authority_hints": ["Approved Manufacturing", "Approved"],
                    "locator_hints": ["Possible Approved"],
                    "domains": ["approved.example"],
                    "review": {
                        "reviewed_at": "2026-01-01",
                        "reviewed_by": "Reviewer",
                        "basis": "opened the manufacturer site",
                    },
                },
                {
                    "key": "unchecked",
                    "authority_hints": ["Unchecked Manufacturing"],
                    "domains": ["unchecked.example"],
                },
            ],
        }
    )
    engine = DeterministicNormalizer(
        manufacturers=reviewed_manufacturer_catalog(
            registry, source="synthetic registry"
        )
    )

    approved = engine.normalize(row(manufacturer="Approved (APPR)")).manufacturer
    locator = engine.normalize(
        row(manufacturer="Possible Approved (POSS)")
    ).manufacturer
    unchecked = engine.normalize(
        row(manufacturer="Unchecked Manufacturing (UNCH)")
    ).manufacturer

    assert approved.delivery_value == "Approved Manufacturing"
    assert approved.authority is AuthorityLevel.HUMAN_APPROVED
    assert locator.decision is NormalizationDecision.REVIEW
    assert unchecked.decision is NormalizationDecision.REVIEW
