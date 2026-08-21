"""The operator-reviewed SATCO binding and its organizer-row consequences."""

from pathlib import Path

from skutruth.discovery.domains import load_registry, parse_registry
from skutruth.discovery.models import SourceAuthority
from skutruth.discovery.policy import classify_authority
from skutruth.unilog import (
    AuthorityLevel,
    ClassificationDecision,
    DeterministicNormalizer,
    DeterministicProductClassifier,
    InternalProductFamily,
    NormalizationDecision,
    NormalizationReason,
    read_unilog_input,
    reviewed_manufacturer_catalog,
)

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "data" / "discovery" / "manufacturer_domains.demo.toml"
INPUT_FILENAME = "Unihack" + "_ Sample Dataset - Input.csv"
INPUT_PATH = ROOT / "data" / "unilog_source" / INPUT_FILENAME


def test_satco_review_licenses_only_the_reviewed_manufacturer_binding():
    registry = load_registry(REGISTRY_PATH)
    entry = registry.entry_for_hint("Satco Prod Inc")

    assert entry is not None
    assert entry.key == "satco-products"
    assert entry.authority_hints == ("SATCO Products, Inc.", "Satco Prod Inc")
    assert entry.domains == ("satco.com",)
    assert entry.review is not None
    assert entry.review.reviewed_at == "2026-08-21"
    assert entry.review.reviewed_by == "Amaan Khan"
    assert "https://www.satco.com/catalog/product/specsheets/62-1875" in entry.review.basis
    assert registry.licenses(entry)
    assert (
        classify_authority(
            "www.satco.com", registry=registry, manufacturer_hint="Satco Prod Inc"
        )
        is SourceAuthority.APPROVED_MANUFACTURER
    )


def test_satco_does_not_cross_bind_or_change_host_refusals():
    registry = load_registry(REGISTRY_PATH)

    assert (
        classify_authority(
            "satco.com", registry=registry, manufacturer_hint="Kichler Lighting"
        )
        is SourceAuthority.OTHER_MANUFACTURER
    )
    assert (
        classify_authority(
            "kichler.com", registry=registry, manufacturer_hint="Satco Prod Inc"
        )
        is SourceAuthority.OTHER_MANUFACTURER
    )
    assert (
        classify_authority(
            "unrelated.example", registry=registry, manufacturer_hint="Satco Prod Inc"
        )
        is SourceAuthority.UNKNOWN
    )
    assert (
        classify_authority(
            "homedepot.com", registry=registry, manufacturer_hint="Satco Prod Inc"
        )
        is SourceAuthority.KNOWN_DISTRIBUTOR
    )
    assert (
        classify_authority(
            "amazon.com", registry=registry, manufacturer_hint="Satco Prod Inc"
        )
        is SourceAuthority.KNOWN_MARKETPLACE
    )


def test_existing_kichler_review_remains_intact():
    registry = load_registry(REGISTRY_PATH)
    entry = registry.entry_for_hint("Kichler Lighting")

    assert entry is not None
    assert entry.key == "kichler-lighting"
    assert entry.domains == ("kichler.com",)
    assert entry.review is not None
    assert entry.review.reviewed_at == "2026-08-21"
    assert entry.review.reviewed_by == "Amaan Khan"
    assert "https://www.kichler.com/why-kichler" in entry.review.basis
    assert (
        classify_authority(
            "kichler.com", registry=registry, manufacturer_hint="Kichler Lighting"
        )
        is SourceAuthority.APPROVED_MANUFACTURER
    )


def test_satco_authority_fails_closed_without_review_provenance():
    registry = parse_registry(
        {
            "name": "unreviewed-satco",
            "authority": "REVIEWED",
            "manufacturer": [
                {
                    "key": "satco-products",
                    "authority_hints": ["SATCO Products, Inc.", "Satco Prod Inc"],
                    "domains": ["satco.com"],
                }
            ],
        },
        source="test",
    )

    assert registry.licensing_entries == ()
    assert (
        classify_authority(
            "satco.com", registry=registry, manufacturer_hint="Satco Prod Inc"
        )
        is SourceAuthority.UNVERIFIED_MANUFACTURER
    )


def test_row_408_resolves_through_review_without_inventing_a_brand():
    registry = load_registry(REGISTRY_PATH)
    row = next(item for item in read_unilog_input(INPUT_PATH) if item.row_number == 408)
    normalization = DeterministicNormalizer(
        manufacturers=reviewed_manufacturer_catalog(
            registry, source=REGISTRY_PATH.as_posix()
        )
    ).normalize(row)
    classification = DeterministicProductClassifier().classify(
        row, normalization=normalization
    )

    assert row.mfg_part_num == "62-1875"
    assert row.part_desc == '62-1875 10" Led Ceiling Lt Bn'
    assert row.part_manuf == "Satco Prod Inc (5573)"
    assert row.manufacturer.display_name == "Satco Prod Inc"
    assert row.manufacturer.supplier_code == "5573"
    assert normalization.manufacturer.decision is NormalizationDecision.COMMIT
    assert normalization.manufacturer.reason is NormalizationReason.EXACT_ALIAS
    assert normalization.manufacturer.canonical_proposal == "SATCO Products, Inc."
    assert normalization.manufacturer.authority is AuthorityLevel.HUMAN_APPROVED
    assert normalization.brand.decision is NormalizationDecision.WITHHOLD
    assert normalization.brand.canonical_proposal is None
    assert classification.decision is ClassificationDecision.COMMIT
    assert classification.internal_family is InternalProductFamily.LIGHTING
