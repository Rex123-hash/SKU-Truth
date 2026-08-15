"""Manifest validation and the locked fingerprint."""

from __future__ import annotations

import pytest
from conftest_eval import case, expected_attr, family_case, manifest
from skutruth.contracts import Applicability, AttributeStatus, IdentityDisposition
from skutruth.eval import (
    EvaluationManifest,
    ExpectedIdentity,
    ManifestValidationError,
    ReviewStatus,
    Split,
    load_named_manifest,
    validate_against_etim,
)


class TestFingerprint:
    def test_identical_content_yields_an_identical_fingerprint(self):
        assert manifest([case()]).fingerprint() == manifest([case()]).fingerprint()

    def test_case_ordering_does_not_change_the_fingerprint(self):
        """Case ids are unique and order carries no meaning, so a reorder is the same set."""
        a = manifest([case(case_id="A"), case(case_id="B", product_family_id="F-B")])
        b = manifest([case(case_id="B", product_family_id="F-B"), case(case_id="A")])
        assert a.fingerprint() == b.fingerprint()

    def test_changing_a_truth_value_changes_the_fingerprint(self):
        from conftest_eval import AMPS_32

        before = manifest([case()])
        after = manifest([case(expected_attributes=(expected_attr(value=AMPS_32),))])
        assert before.fingerprint() != after.fingerprint()

    def test_changing_expected_identity_changes_the_fingerprint(self):
        before = manifest([case()])
        after = manifest([case(case_id="TEST-100", expected_identity=ExpectedIdentity(
            disposition=IdentityDisposition.UNKNOWN))])
        assert before.fingerprint() != after.fingerprint()

    def test_adding_a_case_changes_the_fingerprint(self):
        before = manifest([case()])
        after = manifest([case(), family_case()])
        assert before.fingerprint() != after.fingerprint()

    def test_description_is_not_part_of_the_fingerprint(self):
        """Prose about the set is not part of the set."""
        a = manifest([case()], description="one")
        b = manifest([case()], description="two")
        assert a.fingerprint() == b.fingerprint()

    def test_manifest_version_is_part_of_the_fingerprint(self):
        a = manifest([case()], manifest_version="1")
        b = manifest([case()], manifest_version="2")
        assert a.fingerprint() != b.fingerprint()


class TestValidation:
    def test_duplicate_case_ids_are_rejected(self):
        with pytest.raises(ManifestValidationError, match="duplicate case_id"):
            manifest([case(case_id="DUP"), case(case_id="DUP", product_family_id="F-2")])

    def test_a_family_may_not_appear_in_both_splits(self):
        """Otherwise development on one sibling is preparation for the locked test."""
        with pytest.raises(ManifestValidationError, match="more than one split"):
            manifest(
                [
                    case(case_id="A", product_family_id="SHARED", split=Split.DEV),
                    case(case_id="B", product_family_id="SHARED", split=Split.LOCKED_TEST),
                ]
            )

    def test_the_same_family_within_one_split_is_fine(self):
        m = manifest(
            [
                case(case_id="A", product_family_id="SHARED"),
                case(case_id="B", product_family_id="SHARED"),
            ]
        )
        assert len(m.cases) == 2

    def test_exact_truth_without_an_exact_mpn_is_rejected(self):
        with pytest.raises(ValueError, match="must name the exact MPN"):
            ExpectedIdentity(disposition=IdentityDisposition.EXACT)

    def test_incomplete_reference_truth_must_name_a_discriminator(self):
        with pytest.raises(ManifestValidationError, match="names no missing discriminator"):
            manifest(
                [
                    case(
                        expected_identity=ExpectedIdentity(
                            disposition=IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
                        )
                    )
                ]
            )

    def test_duplicate_truth_for_one_operating_point_is_rejected(self):
        with pytest.raises(ValueError, match="states truth twice"):
            case(expected_attributes=(expected_attr(), expected_attr()))

    def test_the_same_feature_at_different_operating_points_is_allowed(self):
        from conftest_eval import AC1_400V, AMPS_32

        c = case(
            expected_attributes=(
                expected_attr(),
                expected_attr(
                    etim_feature_id="EF001393", value=AMPS_32, conditions=AC1_400V
                ),
            )
        )
        assert len(c.expected_attributes) == 2

    def test_not_applicable_truth_may_not_carry_a_value(self):
        with pytest.raises(ValueError, match="NOT_APPLICABLE but carries an expected value"):
            expected_attr(applicability=Applicability.NOT_APPLICABLE)

    def test_not_applicable_may_not_be_buyer_critical(self):
        with pytest.raises(ManifestValidationError, match="buyer-critical and NOT_APPLICABLE"):
            manifest(
                [
                    case(
                        expected_attributes=(
                            expected_attr(
                                applicability=Applicability.NOT_APPLICABLE,
                                value=None,
                                expected_status=None,
                                buyer_critical=True,
                            ),
                        )
                    )
                ]
            )

    def test_expected_accepted_requires_an_expected_value(self):
        with pytest.raises(ValueError, match="records no expected value"):
            expected_attr(value=None, expected_status=AttributeStatus.ACCEPTED)

    def test_all_problems_are_collected_not_just_the_first(self):
        with pytest.raises(ManifestValidationError) as exc:
            manifest(
                [
                    case(case_id="DUP"),
                    case(case_id="DUP", product_family_id="SHARED", split=Split.DEV),
                    case(case_id="C", product_family_id="SHARED", split=Split.LOCKED_TEST),
                ]
            )
        assert len(exc.value.problems) >= 2


class TestCoverage:
    def test_coverage_summarises_the_set(self):
        m = manifest(
            [
                case(case_id="A"),
                case(case_id="B", product_family_id="F-B", manufacturer="OtherCo"),
                case(case_id="C", product_family_id="F-C", split=Split.LOCKED_TEST),
            ]
        )
        cov = m.coverage()
        assert cov.cases == 3
        assert cov.manufacturers == 2
        assert cov.families == 3
        assert cov.etim_classes == 1
        assert (cov.dev_cases, cov.locked_test_cases) == (2, 1)

    def test_coverage_can_be_scoped_to_a_split(self):
        m = manifest([case(case_id="A"), case(case_id="C", product_family_id="F-C",
                                              split=Split.LOCKED_TEST)])
        assert m.coverage(Split.LOCKED_TEST).cases == 1

    def test_synthetic_sets_are_flagged(self):
        assert manifest([case()]).contains_only_synthetic_cases
        assert not manifest(
            [case(review_status=ReviewStatus.REVIEWED)]
        ).contains_only_synthetic_cases


@pytest.fixture(scope="module")
def smoke():
    return load_named_manifest("synthetic-smoke")


class TestShippedSyntheticManifest:
    def test_it_loads_and_validates(self, smoke):
        assert smoke.manifest_id == "synthetic-smoke"
        assert len(smoke.cases) == 3

    def test_every_case_is_labelled_synthetic(self, smoke):
        """It must be impossible to mistake these for benchmark results."""
        assert smoke.contains_only_synthetic_cases
        assert all(c.review_status is ReviewStatus.SYNTHETIC for c in smoke.cases)

    def test_families_do_not_cross_the_split(self, smoke):
        dev = {c.product_family_id for c in smoke.for_split(Split.DEV)}
        locked = {c.product_family_id for c in smoke.for_split(Split.LOCKED_TEST)}
        assert not (dev & locked)

    def test_its_feature_ids_are_real_etim_features(self, smoke):
        assert validate_against_etim(smoke) == []

    def test_it_round_trips_through_json(self, smoke):
        again = EvaluationManifest.model_validate_json(smoke.model_dump_json())
        assert again.fingerprint() == smoke.fingerprint()


class TestEtimCrossCheck:
    def test_an_unknown_etim_class_is_reported(self):
        m = manifest([case(etim_class_id="EC999999")])
        assert any("unknown ETIM class" in p for p in validate_against_etim(m))

    def test_a_feature_not_on_the_class_is_reported(self):
        m = manifest([case(expected_attributes=(expected_attr(etim_feature_id="EF999999"),))])
        assert any("is not a feature of" in p for p in validate_against_etim(m))
