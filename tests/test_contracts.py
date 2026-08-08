"""The contract invariants are the product. These tests are the lock on them."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from skutruth.contracts import (
    AlphanumericValue,
    AttributeStatus,
    ConfidenceFactors,
    EtimFeatureType,
    Evidence,
    EvidenceCluster,
    EvidenceModality,
    IdentityKind,
    NumericValue,
    ProductAttribute,
    ProductIdentity,
    RangeValue,
    SkuSpecificity,
    SourceType,
    VariantAxis,
)


def make_evidence(
    *,
    url: str = "https://iportal.se.com/Contents/docs/SQD-LC1D18P7_DATASHEET.PDF",
    modality: EvidenceModality = EvidenceModality.SPEC_TABLE,
    specificity: SkuSpecificity = SkuSpecificity.EXACT_SKU,
    quote: str = "Rated operational current Ie ... 18 A",
) -> Evidence:
    return Evidence(
        evidence_id="ev_1",
        source_url=url,
        source_type=SourceType.MANUFACTURER_DATASHEET,
        publisher="Schneider Electric",
        document_sha256="0" * 64,
        quote=quote,
        modality=modality,
        sku_specificity=specificity,
        retrieved_at=datetime(2026, 8, 9, tzinfo=UTC),
        extractor_model="gemini-3.1-flash-lite",
        prompt_version="extract@v1",
        run_id="run_1",
    )


def make_cluster(cluster_id: str = "ec_1", number: float = 18.0) -> EvidenceCluster:
    return EvidenceCluster(
        cluster_id=cluster_id,
        representative_value=NumericValue(raw=f"{number:g} A", number=number, unit="A"),
        members=[make_evidence()],
    )


def make_attribute(**overrides) -> ProductAttribute:
    kwargs = {
        "etim_feature_id": "EF001392",
        "name": "Rated operation current Ie at AC-3, 400 V",
        "feature_type": EtimFeatureType.NUMERIC,
        "expected_unit": "A",
        "value": NumericValue(raw="18 A", number=18.0, unit="A"),
        "status": AttributeStatus.SINGLE_SOURCE,
        "confidence": 0.7,
        "evidence_clusters": [make_cluster()],
    }
    kwargs.update(overrides)
    return ProductAttribute(**kwargs)


class TestNoCommittedValueWithoutEvidence:
    """Invariant 1 — the central promise of the system."""

    def test_value_without_evidence_is_rejected(self):
        with pytest.raises(ValidationError, match="no evidence cluster"):
            make_attribute(evidence_clusters=[])

    def test_value_with_evidence_is_accepted(self):
        assert make_attribute().value is not None


class TestAbstentionCarriesNoValue:
    """Invariant 2 — there is no half-abstention."""

    @pytest.mark.parametrize(
        "status",
        [AttributeStatus.INSUFFICIENT_EVIDENCE, AttributeStatus.VARIANT_DEPENDENT],
    )
    def test_abstention_with_a_value_is_rejected(self, status):
        with pytest.raises(ValidationError, match="must not carry a committed value"):
            make_attribute(status=status)

    @pytest.mark.parametrize(
        "status",
        [AttributeStatus.INSUFFICIENT_EVIDENCE, AttributeStatus.VARIANT_DEPENDENT],
    )
    def test_abstention_without_a_value_is_accepted(self, status):
        attr = make_attribute(status=status, value=None, evidence_clusters=[], confidence=0.0)
        assert attr.is_abstention
        assert attr.value is None

    @pytest.mark.parametrize(
        "status",
        [
            AttributeStatus.VERIFIED,
            AttributeStatus.SINGLE_SOURCE,
            AttributeStatus.CONFLICTED,
        ],
    )
    def test_committed_status_without_a_value_is_rejected(self, status):
        with pytest.raises(ValidationError, match="requires a value"):
            make_attribute(status=status, value=None)

    def test_variant_dependent_may_retain_evidence_while_abstaining(self):
        """A family abstention still shows the reviewer what it found per variant."""
        attr = make_attribute(
            status=AttributeStatus.VARIANT_DEPENDENT,
            value=None,
            confidence=0.0,
            evidence_clusters=[make_cluster("ec_1", 24.0), make_cluster("ec_2", 230.0)],
        )
        assert attr.is_abstention
        assert len(attr.evidence_clusters) == 2


class TestVerifiedRequiresIndependentCorroboration:
    """Invariant 3 — the defence against false confidence from copied sources."""

    def test_verified_with_one_cluster_is_rejected(self):
        with pytest.raises(ValidationError, match=">=2 independent evidence clusters"):
            make_attribute(status=AttributeStatus.VERIFIED, evidence_clusters=[make_cluster()])

    def test_verified_with_two_clusters_is_accepted(self):
        attr = make_attribute(
            status=AttributeStatus.VERIFIED,
            confidence=0.93,
            evidence_clusters=[make_cluster("ec_1"), make_cluster("ec_2")],
        )
        assert attr.status is AttributeStatus.VERIFIED

    def test_many_copies_in_one_cluster_do_not_reach_verified(self):
        """Three distributors copying one datasheet is one observation, not three."""
        copied = EvidenceCluster(
            cluster_id="ec_1",
            representative_value=NumericValue(raw="18 A", number=18.0, unit="A"),
            members=[
                make_evidence(url="https://distributor-a.example/lc1d18p7"),
                make_evidence(url="https://distributor-b.example/lc1d18p7"),
                make_evidence(url="https://distributor-c.example/lc1d18p7"),
            ],
            independence_note="3 URLs collapsed: near-duplicate of manufacturer datasheet text",
        )
        assert copied.size == 3
        with pytest.raises(ValidationError, match=">=2 independent evidence clusters"):
            make_attribute(status=AttributeStatus.VERIFIED, evidence_clusters=[copied])


class TestFamilyIdentityDeclaresVariance:
    """Invariant 4 — keeps family detection honest."""

    def test_family_without_variance_is_rejected(self):
        with pytest.raises(ValidationError, match="at least one variant axis"):
            ProductIdentity(
                kind=IdentityKind.FAMILY,
                confidence=0.9,
                reasoning="looks like a family",
            )

    def test_family_with_a_variant_axis_is_accepted(self):
        identity = ProductIdentity(
            kind=IdentityKind.FAMILY,
            brand_normalized="Schneider Electric",
            mpn_normalized="LC1D18",
            confidence=0.9,
            reasoning="LC1D18 is a TeSys D family stem; orderable references append a coil code.",
            variant_axes=[
                VariantAxis(
                    name="Rated control supply voltage",
                    observed_values=["24 V DC", "230 V AC"],
                    example_mpns=["LC1D18BD", "LC1D18P7"],
                )
            ],
        )
        assert identity.kind is IdentityKind.FAMILY

    def test_exact_sku_needs_no_variance(self):
        identity = ProductIdentity(
            kind=IdentityKind.EXACT_SKU,
            mpn_normalized="LC1D18P7",
            confidence=0.97,
            reasoning="Fully qualified reference with a matching manufacturer datasheet.",
        )
        assert not identity.variant_axes


class TestRangeIsWellFormed:
    """Invariant 5 — definitional, not a physical estimate."""

    def test_inverted_range_is_rejected(self):
        with pytest.raises(ValidationError, match="exceeds maximum"):
            RangeValue(raw="230-24 V", minimum=230.0, maximum=24.0, unit="V")

    def test_ordered_range_is_accepted(self):
        assert RangeValue(raw="24-230 V", minimum=24.0, maximum=230.0, unit="V").maximum == 230.0

    def test_degenerate_range_is_allowed(self):
        assert RangeValue(raw="24 V", minimum=24.0, maximum=24.0, unit="V").minimum == 24.0


class TestConfidenceIsNotModelGenerated:
    def test_factors_default_to_uncalibrated(self):
        """Until a fitted curve exists, the aggregate is an ordinal score, not a probability."""
        factors = ConfidenceFactors(
            authority_prior=0.95,
            modality=0.95,
            sku_specificity=1.0,
            independent_cluster_agreement=0.5,
            etim_validation=1.0,
            recency=0.9,
        )
        assert factors.calibrated is False

    def test_factors_are_bounded(self):
        with pytest.raises(ValidationError):
            ConfidenceFactors(
                authority_prior=1.4,
                modality=0.9,
                sku_specificity=1.0,
                independent_cluster_agreement=0.5,
                etim_validation=1.0,
                recency=0.9,
            )


class TestEvidencePresentation:
    def test_best_member_prefers_exact_sku_spec_table(self):
        cluster = EvidenceCluster(
            cluster_id="ec_1",
            representative_value=AlphanumericValue(raw="AC", text="AC"),
            members=[
                make_evidence(
                    url="https://web.example/blog",
                    modality=EvidenceModality.MARKETING,
                    specificity=SkuSpecificity.RANGE,
                ),
                make_evidence(
                    url="https://iportal.se.com/datasheet.pdf",
                    modality=EvidenceModality.SPEC_TABLE,
                    specificity=SkuSpecificity.EXACT_SKU,
                ),
            ],
        )
        assert cluster.best_member.source_url.endswith("datasheet.pdf")

    def test_evidence_requires_a_verbatim_quote(self):
        with pytest.raises(ValidationError):
            make_evidence(quote="")
