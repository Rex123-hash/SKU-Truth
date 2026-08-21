"""The operator-reviewed Feit binding and its organizer-row consequences."""

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


def test_feit_review_licenses_the_exact_alias_and_reviewed_root_domain():
    registry = load_registry(REGISTRY_PATH)
    entry = registry.entry_for_hint("Feit Electric")

    assert entry is not None
    assert entry.key == "feit-electric"
    assert entry.authority_hints == ("Feit Electric Company, Inc.", "Feit Electric")
    assert entry.domains == ("feit.com",)
    assert entry.review is not None
    assert entry.review.reviewed_at == "2026-08-21"
    assert entry.review.reviewed_by == "Amaan Khan"
    assert "https://www.feit.com/pages/about-us" in entry.review.basis
    assert "SHOP-4X2-840-V1_SpecSheet.pdf" in entry.review.basis
    assert registry.licenses(entry)
    assert (
        classify_authority(
            "feit.com", registry=registry, manufacturer_hint="Feit Electric"
        )
        is SourceAuthority.APPROVED_MANUFACTURER
    )


def test_reviewed_feit_root_licenses_label_aware_subdomains_only():
    registry = load_registry(REGISTRY_PATH)

    assert (
        classify_authority(
            "appshopfy.feit.com", registry=registry, manufacturer_hint="Feit Electric"
        )
        is SourceAuthority.APPROVED_MANUFACTURER
    )
    for lookalike in ("notfeit.com", "feit.com.evil.example", "appshopfy.notfeit.com"):
        assert (
            classify_authority(
                lookalike, registry=registry, manufacturer_hint="Feit Electric"
            )
            is SourceAuthority.UNKNOWN
        )


def test_feit_does_not_cross_bind_and_existing_reviews_remain_intact():
    registry = load_registry(REGISTRY_PATH)

    cases = (
        ("feit.com", "Kichler Lighting"),
        ("feit.com", "Satco Prod Inc"),
        ("kichler.com", "Feit Electric"),
        ("satco.com", "Feit Electric"),
    )
    for host, hint in cases:
        assert (
            classify_authority(host, registry=registry, manufacturer_hint=hint)
            is SourceAuthority.OTHER_MANUFACTURER
        )

    assert (
        classify_authority(
            "kichler.com", registry=registry, manufacturer_hint="Kichler Lighting"
        )
        is SourceAuthority.APPROVED_MANUFACTURER
    )
    assert (
        classify_authority(
            "satco.com", registry=registry, manufacturer_hint="Satco Prod Inc"
        )
        is SourceAuthority.APPROVED_MANUFACTURER
    )


def test_feit_authority_fails_closed_without_review_provenance():
    registry = parse_registry(
        {
            "name": "unreviewed-feit",
            "authority": "REVIEWED",
            "manufacturer": [
                {
                    "key": "feit-electric",
                    "authority_hints": [
                        "Feit Electric Company, Inc.",
                        "Feit Electric",
                    ],
                    "domains": ["feit.com"],
                }
            ],
        },
        source="test",
    )

    assert registry.licensing_entries == ()
    assert (
        classify_authority(
            "appshopfy.feit.com",
            registry=registry,
            manufacturer_hint="Feit Electric",
        )
        is SourceAuthority.UNVERIFIED_MANUFACTURER
    )


def test_row_447_resolves_through_review_without_inventing_brand_truth():
    registry = load_registry(REGISTRY_PATH)
    row = next(item for item in read_unilog_input(INPUT_PATH) if item.row_number == 447)
    normalization = DeterministicNormalizer(
        manufacturers=reviewed_manufacturer_catalog(
            registry, source=REGISTRY_PATH.as_posix()
        )
    ).normalize(row)
    classification = DeterministicProductClassifier().classify(
        row, normalization=normalization
    )

    assert row.mfg_part_num == "SHOP/4X2/840/V1"
    assert row.part_desc == "4' Feit Shop Light 4500L 40k"
    assert row.part_manuf == "Feit Electric (3468)"
    assert row.dib_brand == "Feit Electric"
    assert row.manufacturer.display_name == "Feit Electric"
    assert row.manufacturer.supplier_code == "3468"
    assert normalization.manufacturer.decision is NormalizationDecision.COMMIT
    assert normalization.manufacturer.reason is NormalizationReason.EXACT_ALIAS
    assert (
        normalization.manufacturer.canonical_proposal
        == "Feit Electric Company, Inc."
    )
    assert normalization.manufacturer.authority is AuthorityLevel.HUMAN_APPROVED
    assert normalization.brand.decision is NormalizationDecision.REVIEW
    assert normalization.brand.reason is NormalizationReason.SINGLE_BRAND_SOURCE
    assert normalization.brand.canonical_proposal == "Feit Electric"
    assert classification.decision is ClassificationDecision.COMMIT
    assert classification.internal_family is InternalProductFamily.LIGHTING
