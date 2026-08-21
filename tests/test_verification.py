"""Mechanical evidence verification.

Every artifact here is synthetic. The real Schneider verification run is a local,
uncommitted script — a committed test must never depend on a third-party document.
"""

from __future__ import annotations

import pytest
from conftest_pdf import build_pdf
from skutruth.contracts import (
    AlphanumericValue,
    Condition,
    ConditionKind,
    ConditionSet,
    EvidenceVerification,
    IdentityScope,
    NumericValue,
    ProductInput,
    RangeValue,
)
from skutruth.identity import (
    EvidenceAnchor,
    ExactReferenceFact,
    IdentityEvidence,
    ReferenceCompletionFact,
    resolve_identity,
)
from skutruth.ingest import ingest_pdf_bytes
from skutruth.ingest.models import SourceMetadata
from skutruth.ingest.storage import ArtifactStore
from skutruth.verification import (
    VERIFIER_VERSION,
    EvidenceMode,
    ProductClaim,
    Relation,
    TextMatchMode,
    VerificationFailure,
    artifact_scope_supports_exact,
    parse_quantities,
    verify_claim,
    verify_table_claim,
)

MPN = "BASE100X1"
BRAND = "TestCo"

#: One coherent line stating a rating with its whole operating point.
RATING_LINE = "18 A (at <60 °C) at <= 440 V AC AC-3 for power circuit"
PAGES = [
    "TESTCO CONTACTOR DATA",
    RATING_LINE + "\n32 A (at <60 °C) at <= 440 V AC AC-1 for power circuit",
    "Control supply 230 V AC 50/60 Hz\n3 NO main contacts\nHousing Stainless Steel",
]


@pytest.fixture
def store(tmp_path) -> ArtifactStore:
    return ArtifactStore(tmp_path, writable=True)


def ingest(store: ArtifactStore, pages=None, **source_kw):
    """Ingest a synthetic document, by default an exact-SKU datasheet for `MPN`.

    Text evidence has no per-unit binding to a product, so the verifier requires the
    artifact's own scope to supply one. Most tests here are about matching, conditions,
    or integrity rather than scope, and an unscoped fixture would make every one of them
    fail for a reason they are not testing. Scope tests pass their own values.
    """
    pdf = build_pdf(pages if pages is not None else PAGES)
    source_kw.setdefault("identity_scope", IdentityScope.EXACT_SKU)
    source_kw.setdefault("covers_mpn", MPN)
    source = SourceMetadata(publisher=BRAND, **source_kw)
    artifact = ingest_pdf_bytes(pdf, source=source)
    store.save(artifact, pdf)
    return artifact


def conditions(*pairs) -> ConditionSet:
    return ConditionSet(conditions=tuple(Condition(kind=k, value=v) for k, v in pairs))


def claim(
    artifact,
    *,
    value=None,
    conds: ConditionSet | None = None,
    page: int = 2,
    fragment: str = "18 A",
    key: str = "EF001392",
    mpn: str = MPN,
) -> ProductClaim:
    return ProductClaim(
        key=key,
        value=value if value is not None else NumericValue(number=18.0, unit="A", raw="18 A"),
        conditions=conds if conds is not None else ConditionSet(),
        exact_mpn=mpn,
        artifact_sha256=artifact.sha256,
        page_number=page,
        source_fragment=fragment,
    )


def exact_identity(mpn: str = MPN):
    anchor = EvidenceAnchor(
        artifact_sha256="a" * 64,
        identity_scope=IdentityScope.EXACT_SKU,
        observed_statement="exists",
    )
    return resolve_identity(
        ProductInput(brand=BRAND, mpn=mpn, description="x"),
        IdentityEvidence(
            exact_facts=(ExactReferenceFact(brand=BRAND, exact_mpn=mpn, anchor=anchor),)
        ),
    )


class TestQuantityParsing:
    def test_operators_are_preserved(self):
        by_text = {q.text: q for q in parse_quantities(RATING_LINE)}
        assert by_text["18 A"].relation is Relation.EQ
        assert by_text["<60 °C"].relation is Relation.LT
        assert by_text["<= 440 V"].relation is Relation.LE

    def test_enumeration_yields_each_alternative(self):
        quantities = [q for q in parse_quantities("230 V AC 50/60 Hz") if q.unit == "Hz"]
        assert {q.number for q in quantities} == {50.0, 60.0}
        assert all(q.enumerated for q in quantities)

    def test_identifier_digits_are_not_quantities(self):
        """`AC-3` is a category, not the number three."""
        assert all(q.number != 3.0 for q in parse_quantities("AC-3 utilisation"))


class TestSourceUnitTypography:
    """Publishers write `KW` for kilowatt. That is typography, not a different quantity."""

    def test_unambiguous_case_variants_resolve(self):
        from skutruth.verification.quantities import resolve_source_unit

        assert resolve_source_unit("KW") == "kW"
        assert resolve_source_unit("Mm") == "mm"
        assert resolve_source_unit("a") == "A"

    def test_exact_symbols_are_returned_unchanged(self):
        from skutruth.verification.quantities import resolve_source_unit

        assert resolve_source_unit("mW") == "mW"
        assert resolve_source_unit("MW") == "MW"

    def test_case_bearing_collision_is_refused(self):
        """`mw` could be milliwatt or megawatt — a thousand-fold error. Refuse."""
        from skutruth.verification.quantities import resolve_source_unit

        assert resolve_source_unit("mw") is None

    def test_non_units_do_not_resolve(self):
        from skutruth.verification.quantities import resolve_source_unit

        assert resolve_source_unit("NO") is None
        assert resolve_source_unit("dBA") is None

    def test_typographic_unit_verifies_a_claim(self, store):
        artifact = ingest(store, ["x", "Rated power 7.5 KW at 400 V AC (AC-3)"])
        result = verify_claim(
            claim(
                artifact,
                value=NumericValue(number=7.5, unit="kW", raw="7.5 kW"),
                fragment="7.5 KW",
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_ambiguous_typographic_unit_does_not_verify(self, store):
        artifact = ingest(store, ["x", "Dissipation 5 mw stated loosely"])
        result = verify_claim(
            claim(
                artifact,
                value=NumericValue(number=5.0, unit="mW", raw="5 mW"),
                fragment="5 mw",
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED


class TestTextVerification:
    def test_exact_literal_value_verifies(self, store):
        artifact = ingest(store)
        result = verify_claim(claim(artifact), store=store)
        assert result.status is EvidenceVerification.EXACT_SPAN
        assert result.evidence_mode is EvidenceMode.TEXT_UNIT
        assert result.match_mode is TextMatchMode.LITERAL
        assert result.verifier_version == VERIFIER_VERSION

    def test_representation_only_variation_verifies(self, store):
        """NBSP differs from a space in bytes, not in meaning."""
        artifact = ingest(store)
        result = verify_claim(claim(artifact, fragment="18 A"), store=store)
        assert result.status is EvidenceVerification.EXACT_SPAN
        assert result.match_mode is TextMatchMode.NORMALIZED

    def test_ocr_status_is_never_used(self, store):
        """No OCR runs in this system, so FUZZY_OCR_SPAN must never be emitted."""
        artifact = ingest(store)
        for fragment in ("18 A", "18 A"):
            result = verify_claim(claim(artifact, fragment=fragment), store=store)
            assert result.status is not EvidenceVerification.FUZZY_OCR_SPAN

    def test_wrong_numeric_value_is_unverified(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, value=NumericValue(number=25.0, unit="A", raw="25 A")), store=store
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.VALUE_NOT_SUPPORTED

    def test_convertible_unit_verifies(self, store):
        """18000 mA is 18 A; the existing unit layer proves it."""
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, value=NumericValue(number=18000.0, unit="mA", raw="18000 mA")),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_incompatible_unit_is_unverified(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, value=NumericValue(number=18.0, unit="V", raw="18 V")), store=store
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure in {
            VerificationFailure.UNIT_NOT_SUPPORTED,
            VerificationFailure.VALUE_NOT_SUPPORTED,
        }

    def test_wrong_page_is_unverified(self, store):
        artifact = ingest(store)
        result = verify_claim(claim(artifact, page=1), store=store)
        assert result.failure is VerificationFailure.SOURCE_FRAGMENT_NOT_FOUND

    def test_page_beyond_document_is_unverified(self, store):
        artifact = ingest(store)
        result = verify_claim(claim(artifact, page=99), store=store)
        assert result.failure is VerificationFailure.PAGE_NOT_FOUND

    def test_absent_fragment_is_unverified(self, store):
        artifact = ingest(store)
        result = verify_claim(claim(artifact, fragment="not in the document"), store=store)
        assert result.failure is VerificationFailure.SOURCE_FRAGMENT_NOT_FOUND

    def test_both_proposed_and_actual_text_are_retained(self, store):
        artifact = ingest(store)
        result = verify_claim(claim(artifact, fragment="18 A"), store=store)
        assert result.proposed_fragment == "18 A"
        assert "18" in result.matched_text
        assert result.evidence is not None
        assert "AC-3" in result.evidence.text


class TestAmbiguity:
    def test_inconsistent_duplicate_occurrences_are_ambiguous(self, store):
        """The same fragment on two lines that disagree cannot be resolved."""
        pages = ["x", "18 A at AC-3 for power circuit\n18 A at AC-1 for power circuit"]
        artifact = ingest(store, pages)
        result = verify_claim(
            claim(
                artifact,
                conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3")),
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.AMBIGUOUS_MATCH

    def test_consistent_duplicates_verify_deterministically(self, store):
        """Every occurrence supports the claim identically, so the choice is moot."""
        pages = ["x", "18 A at AC-3 for power circuit\n18 A at AC-3 restated"]
        artifact = ingest(store, pages)
        result = verify_claim(
            claim(
                artifact,
                conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3")),
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN


class TestConditions:
    def test_complete_conditions_verify(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN
        assert all(o.supported for o in result.condition_outcomes)

    def test_missing_condition_is_unverified(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-4")),
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.CONDITION_NOT_SUPPORTED

    def test_wrong_utilization_category_fails(self, store):
        """AC-1 and AC-3 are different ratings of the same contactor."""
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-1"))),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED

    def test_condition_outcomes_are_itemised(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                conds=conditions(
                    (ConditionKind.UTILIZATION_CATEGORY, "AC-3"),
                    (ConditionKind.TEMPERATURE, "60 °C"),
                ),
            ),
            store=store,
        )
        by_kind = {o.kind: o for o in result.condition_outcomes}
        assert by_kind["UTILIZATION_CATEGORY"].supported is True
        assert by_kind["TEMPERATURE"].supported is False


class TestOperatorRegressions:
    """The three real failures from the first live Gemini run."""

    def test_less_than_60c_does_not_support_a_point_of_60c(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.TEMPERATURE, "60 °C"))),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.OPERATOR_MISMATCH

    def test_up_to_440v_does_not_support_a_point_of_440v(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.VOLTAGE, "440 V"))),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.OPERATOR_MISMATCH

    def test_up_to_440v_does_not_support_a_point_of_400v(self, store):
        """A value inside a bound is not a value the document states."""
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.VOLTAGE, "400 V"))),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED

    def test_bounded_value_does_not_support_a_point_claim(self, store):
        artifact = ingest(store, ["x", "rated up to <= 18 A for power circuit"])
        result = verify_claim(claim(artifact, fragment="18 A"), store=store)
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.OPERATOR_MISMATCH


class TestFrequencyEnumeration:
    """`50/60 Hz` asserts both frequencies discretely, so either may be bound."""

    def test_50hz_is_supported_by_50_60hz(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                value=NumericValue(number=230.0, unit="V", raw="230 V"),
                conds=conditions((ConditionKind.FREQUENCY, "50 Hz")),
                page=3,
                fragment="230 V AC 50/60 Hz",
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_60hz_is_also_supported(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                value=NumericValue(number=230.0, unit="V", raw="230 V"),
                conds=conditions((ConditionKind.FREQUENCY, "60 Hz")),
                page=3,
                fragment="230 V AC 50/60 Hz",
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_an_unstated_frequency_is_not_supported(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                value=NumericValue(number=230.0, unit="V", raw="230 V"),
                conds=conditions((ConditionKind.FREQUENCY, "400 Hz")),
                page=3,
                fragment="230 V AC 50/60 Hz",
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED


class TestOneEvidenceUnit:
    def test_coherent_single_line_claim_verifies(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3")),
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_value_and_condition_on_separate_lines_do_not_combine(self, store):
        """Frankenstein evidence: the number is real, the qualifier is real, the claim is not."""
        pages = ["x", "Rated operational current 18 A for power circuit\nUtilisation category AC-3"]
        artifact = ingest(store, pages)
        result = verify_claim(
            claim(
                artifact,
                conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3")),
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.CONDITION_NOT_SUPPORTED

    def test_qualifier_elsewhere_on_the_page_is_not_borrowed(self, store):
        pages = ["x", "AC-3 appears in this header line\n18 A stated with no qualifier"]
        artifact = ingest(store, pages)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED


class TestTableVerification:
    def _tables(self):
        from conftest_pdf import build_ruled_table_pdf
        from skutruth.ingest.tables import extract_page_tables

        rules = [(x, 700.0, 740.0) for x in (60, 160, 260, 360)]
        texts = [
            (65, 728, "Reference"),
            (165, 728, "AC-3"),
            (265, 728, "Current"),
            (65, 685, "BASE100X1"),
            (165, 685, "AC-3"),
            (265, 685, "18 A"),
            (65, 670, "BASE100Y2"),
            (165, 670, "AC-3"),
            (265, 670, "7.5 A"),
        ]
        return extract_page_tables(build_ruled_table_pdf(rules, texts), 1)

    def test_coherent_table_row_verifies(self, store):
        artifact = ingest(store)
        result = verify_table_claim(
            claim(artifact, conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))),
            self._tables(),
        )
        assert result.status is EvidenceVerification.EXACT_SPAN
        assert result.evidence_mode is EvidenceMode.TABLE_UNIT
        assert result.evidence.row_index is not None

    def test_correct_number_in_the_wrong_product_row_fails(self, store):
        """7.5 A belongs to the sibling; it must not verify for this reference."""
        artifact = ingest(store)
        result = verify_table_claim(
            claim(artifact, value=NumericValue(number=7.5, unit="A", raw="7.5 A")), self._tables()
        )
        assert result.status is EvidenceVerification.UNVERIFIED

    def test_row_for_another_reference_is_a_reference_mismatch(self, store):
        artifact = ingest(store)
        result = verify_table_claim(claim(artifact, mpn="NOTPRESENT9"), self._tables())
        assert result.failure is VerificationFailure.PRODUCT_REFERENCE_MISMATCH

    def test_family_placeholder_does_not_support_an_exact_child(self, store):
        """`BASE100pp` is a base reference; it is not its own child."""
        from conftest_pdf import build_ruled_table_pdf
        from skutruth.ingest.tables import extract_page_tables

        rules = [(x, 700.0, 740.0) for x in (60, 160, 260, 360)]
        texts = [
            (65, 728, "Reference"),
            (165, 728, "AC-3"),
            (265, 728, "Current"),
            (65, 685, "BASE100pp"),
            (165, 685, "AC-3"),
            (265, 685, "18 A"),
        ]
        artifact = ingest(store)
        result = verify_table_claim(
            claim(artifact), extract_page_tables(build_ruled_table_pdf(rules, texts), 1)
        )
        assert result.failure is VerificationFailure.PRODUCT_REFERENCE_MISMATCH

    def test_unresolved_table_structure_fails(self, store):
        from skutruth.ingest.tables import extract_page_tables

        artifact = ingest(store)
        unruled = extract_page_tables(build_pdf(["no ruling at all"]), 1)
        result = verify_table_claim(claim(artifact), unruled)
        assert result.failure is VerificationFailure.TABLE_STRUCTURE_UNRESOLVED


class TestArtifactIntegrity:
    def test_artifact_sha_mismatch_fails_closed(self, store):
        artifact = ingest(store)
        other = ingest(store, ["completely different document"])
        result = verify_claim(claim(artifact), store=store, artifact=other)
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.ARTIFACT_MISMATCH

    def test_corrupted_stored_artifact_fails_closed(self, store, tmp_path):
        artifact = ingest(store)
        page_file = tmp_path / artifact.sha256 / "pages" / "0002.txt"
        page_file.write_text("tampered content", encoding="utf-8")
        result = verify_claim(claim(artifact), store=store)
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.ARTIFACT_UNREADABLE

    def test_missing_artifact_fails_closed(self, store):
        artifact = ingest(store)
        store.delete(artifact.sha256)
        result = verify_claim(claim(artifact), store=store)
        assert result.failure is VerificationFailure.ARTIFACT_UNREADABLE


class TestProductBinding:
    def test_non_exact_identity_is_refused(self, store):
        artifact = ingest(store)
        anchor = EvidenceAnchor(
            artifact_sha256="a" * 64,
            identity_scope=IdentityScope.RANGE,
            observed_statement="base",
        )
        family = resolve_identity(
            ProductInput(brand=BRAND, mpn="BASE100", description="x"),
            IdentityEvidence(
                completion_facts=(
                    ReferenceCompletionFact(
                        brand=BRAND,
                        base_mpn="BASE100",
                        discriminator_key="control_circuit",
                        anchor=anchor,
                    ),
                )
            ),
        )
        result = verify_claim(claim(artifact), store=store, identity=family)
        assert result.failure is VerificationFailure.PRODUCT_SCOPE_NOT_SUPPORTED

    def test_identity_targeting_a_different_reference_is_refused(self, store):
        artifact = ingest(store)
        result = verify_claim(claim(artifact), store=store, identity=exact_identity("BASE100Y2"))
        assert result.failure is VerificationFailure.PRODUCT_REFERENCE_MISMATCH

    def test_matching_exact_identity_permits_verification(self, store):
        artifact = ingest(store)
        result = verify_claim(claim(artifact), store=store, identity=exact_identity())
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_range_artifact_does_not_prove_exact_scope(self, store):
        artifact = ingest(
            store,
            identity_scope=IdentityScope.RANGE,
            covers_mpn=None,
            final_artifact_url="https://example.invalid/x.pdf",
        )
        assert artifact_scope_supports_exact(artifact, MPN) is False

    def test_exact_sku_artifact_covering_the_reference_supports_exact_scope(self, store):
        artifact = ingest(
            store,
            identity_scope=IdentityScope.EXACT_SKU,
            covers_mpn=MPN,
            final_artifact_url="https://example.invalid/x.pdf",
        )
        assert artifact_scope_supports_exact(artifact, MPN) is True

    def test_exact_sku_artifact_for_a_sibling_does_not(self, store):
        artifact = ingest(
            store,
            identity_scope=IdentityScope.EXACT_SKU,
            covers_mpn="BASE100Y2",
            final_artifact_url="https://example.invalid/x.pdf",
        )
        assert artifact_scope_supports_exact(artifact, MPN) is False


class TestValueKinds:
    def test_alphanumeric_value_present_in_the_unit_verifies(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                value=AlphanumericValue(text="Stainless Steel", raw="Stainless Steel"),
                page=3,
                fragment="Housing Stainless Steel",
                key="EF000123",
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_alphanumeric_value_absent_is_unverified(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                value=AlphanumericValue(text="Brass", raw="Brass"),
                page=3,
                fragment="Housing Stainless Steel",
                key="EF000123",
            ),
            store=store,
        )
        assert result.failure is VerificationFailure.VALUE_NOT_SUPPORTED

    def test_range_values_are_withheld_not_approximated(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                value=RangeValue(minimum=230.0, maximum=230.0, unit="V", raw="230 V"),
                page=3,
                fragment="230 V AC 50/60 Hz",
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.UNSUPPORTED_VALUE_KIND

    def test_unitless_count_verifies(self, store):
        artifact = ingest(store)
        result = verify_claim(
            claim(
                artifact,
                value=NumericValue(number=3.0, raw="3"),
                page=3,
                fragment="3 NO main contacts",
                key="EF001374",
            ),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN


class TestVerifiedIsNotAccepted:
    def test_outcome_carries_no_confidence_or_grade(self):
        from skutruth.verification import models as verification_models

        forbidden = (
            "confidence",
            "probability",
            "support_grade",
            "grade",
            "accepted",
            "proves_family_scope",
        )
        checked = 0
        for name in dir(verification_models):
            obj = getattr(verification_models, name)
            fields = getattr(obj, "model_fields", None)
            if not fields or getattr(obj, "__module__", "") != verification_models.__name__:
                continue
            checked += 1
            for field_name in fields:
                assert not any(f in field_name.lower() for f in forbidden), f"{name}.{field_name}"
        assert checked >= 4

    def test_verifier_does_not_produce_a_product_attribute(self, store):
        from skutruth.contracts import ProductAttribute

        artifact = ingest(store)
        result = verify_claim(claim(artifact), store=store)
        assert not isinstance(result, ProductAttribute)
        assert not hasattr(result, "status_reason")

    def test_failures_always_carry_a_reason(self, store):
        artifact = ingest(store)
        result = verify_claim(claim(artifact, fragment="absent"), store=store)
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is not None
        assert result.failure_detail


class TestVocabularyIndependence:
    def test_engine_modules_do_not_import_extraction_or_etim_classes(self):
        """Only the adapter may know about ETIM-shaped candidates."""
        from pathlib import Path

        import skutruth.verification as pkg

        for path in Path(pkg.__file__).parent.glob("*.py"):
            # Representation adapters may know the proposal shape they adapt.  The
            # generic/PDF engine modules remain vocabulary- and extraction-independent.
            if path.name in {"adapters.py", "html_attributes.py", "__init__.py"}:
                continue
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            assert not [i for i in imports if "skutruth.extraction" in i], path.name

    def test_a_claim_needs_no_etim_specific_type(self, store):
        """A Unilog-shaped claim will build exactly the same way."""
        artifact = ingest(store)
        generic = ProductClaim(
            key="unilog:Amperage Rating",
            label="Amperage Rating",
            value=NumericValue(number=18.0, unit="A", raw="18 A"),
            conditions=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3")),
            exact_mpn=MPN,
            artifact_sha256=artifact.sha256,
            page_number=2,
            source_fragment="18 A",
        )
        assert verify_claim(generic, store=store).status is EvidenceVerification.EXACT_SPAN

    def test_adapter_converts_an_etim_candidate(self, store):
        from skutruth.extraction.models import ExtractionCandidate
        from skutruth.verification import claim_from_candidate

        candidate = ExtractionCandidate(
            etim_feature_id="EF001392",
            feature_name="Rated operation current",
            value=NumericValue(number=18.0, unit="A", raw="18 A"),
            conditions=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3")),
            source_fragment="18 A",
            page_number=2,
        )
        artifact = ingest(store)
        built = claim_from_candidate(candidate, exact_mpn=MPN, artifact_sha256=artifact.sha256)
        assert built.key == "EF001392"
        assert verify_claim(built, store=store).status is EvidenceVerification.EXACT_SPAN


class TestEvaluationIntegration:
    """Citation validity becomes verification-backed. No metric is rewritten."""

    def test_verified_outcome_yields_a_verified_citation(self, store):
        from skutruth.verification import citation_from_outcome

        artifact = ingest(store)
        outcome = verify_claim(claim(artifact), store=store)
        citation = citation_from_outcome(outcome, identity_scope=IdentityScope.EXACT_SKU)
        assert citation.span_verified is True
        assert citation.artifact_sha256 == artifact.sha256
        assert citation.page == 2
        assert citation.identity_scope is IdentityScope.EXACT_SKU

    def test_unverified_outcome_is_never_marked_verified(self, store):
        from skutruth.verification import citation_from_outcome

        artifact = ingest(store)
        outcome = verify_claim(claim(artifact, fragment="absent from the document"), store=store)
        assert citation_from_outcome(outcome).span_verified is False

    def test_citation_quote_is_the_artifact_text_not_the_model_fragment(self, store):
        """Only one of the two strings is evidence."""
        from skutruth.verification import citation_from_outcome

        artifact = ingest(store)
        outcome = verify_claim(claim(artifact, fragment="18 A"), store=store)
        assert citation_from_outcome(outcome).quote == outcome.matched_text

    def test_identity_scope_is_never_inferred(self, store):
        from skutruth.verification import citation_from_outcome

        artifact = ingest(store)
        outcome = verify_claim(claim(artifact), store=store)
        assert citation_from_outcome(outcome).identity_scope is None


class TestExactArtifactScope:
    """Text evidence must be bound to the product by the document's own provenance.

    A line stating `18 A` on a page shared by a whole product family says nothing about
    which family member it belongs to. Before this gate existed, such a line verified for
    any reference the caller happened to name.
    """

    def range_artifact(self, store, pages=None):
        return ingest(
            store,
            pages,
            identity_scope=IdentityScope.RANGE,
            covers_mpn=None,
            final_artifact_url="https://example.invalid/catalogue.pdf",
        )

    def test_range_artifact_cannot_verify_an_exact_text_claim(self, store):
        """A. The audit's failure shape: mechanically supported, but not this product's."""
        artifact = self.range_artifact(store)
        result = verify_claim(claim(artifact), store=store)
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.PRODUCT_SCOPE_NOT_SUPPORTED

    def test_matching_exact_identity_cannot_override_range_scope(self, store):
        """B. Identity says what we resolved; scope says whose evidence this is."""
        artifact = self.range_artifact(store)
        result = verify_claim(claim(artifact), store=store, identity=exact_identity())
        assert result.failure is VerificationFailure.PRODUCT_SCOPE_NOT_SUPPORTED

    def test_exact_sku_artifact_covering_the_reference_verifies(self, store):
        """C."""
        artifact = ingest(store, identity_scope=IdentityScope.EXACT_SKU, covers_mpn=MPN)
        assert verify_claim(claim(artifact), store=store).status is EvidenceVerification.EXACT_SPAN

    def test_exact_sku_artifact_for_a_sibling_is_a_reference_mismatch(self, store):
        """D. The document positively asserts it is about a different product."""
        artifact = ingest(store, identity_scope=IdentityScope.EXACT_SKU, covers_mpn="BASE100Y2")
        result = verify_claim(claim(artifact), store=store)
        assert result.failure is VerificationFailure.PRODUCT_REFERENCE_MISMATCH

    def test_unstated_scope_does_not_establish_exact_applicability(self, store):
        """Unknown provenance is not permissive provenance."""
        artifact = ingest(store, identity_scope=None, covers_mpn=None)
        result = verify_claim(claim(artifact), store=store)
        assert result.failure is VerificationFailure.PRODUCT_SCOPE_NOT_SUPPORTED

    def test_reference_in_page_text_does_not_establish_scope(self, store):
        """Scope is provenance, never a string that happens to appear on the page."""
        pages = ["x", f"{MPN} 18 A (at <60 °C) at <= 440 V AC AC-3 for power circuit"]
        artifact = self.range_artifact(store, pages)
        result = verify_claim(claim(artifact), store=store)
        assert result.failure is VerificationFailure.PRODUCT_SCOPE_NOT_SUPPORTED

    def test_a_table_row_binds_the_product_inside_a_range_catalogue(self, store):
        """Range evidence stays usable: the row itself carries the binding.

        This is the deliberate second proof of exact applicability. Removing it would
        make the table path — and every catalogue — worthless, which is a different
        error from the one this milestone fixes.
        """
        from conftest_pdf import build_ruled_table_pdf
        from skutruth.ingest.tables import extract_page_tables

        rules = [(x, 700.0, 740.0) for x in (60, 160, 260, 360)]
        texts = [
            (65, 728, "Reference"),
            (165, 728, "AC-3"),
            (265, 728, "Current"),
            (65, 685, MPN),
            (165, 685, "AC-3"),
            (265, 685, "18 A"),
        ]
        pdf = build_ruled_table_pdf(rules, texts)
        artifact = ingest_pdf_bytes(
            pdf,
            source=SourceMetadata(
                publisher=BRAND,
                identity_scope=IdentityScope.RANGE,
                covers_mpn=None,
                final_artifact_url="https://example.invalid/catalogue.pdf",
            ),
        )
        store.save(artifact, pdf)
        result = verify_claim(
            claim(artifact, page=1, conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))),
            store=store,
            tables=extract_page_tables(pdf, 1),
        )
        assert result.status is EvidenceVerification.EXACT_SPAN
        assert result.evidence_mode is EvidenceMode.TABLE_UNIT

    def test_scope_binding_classifies_the_three_cases(self, store):
        from skutruth.verification import ScopeBinding, artifact_scope_binding

        exact = ingest(store, identity_scope=IdentityScope.EXACT_SKU, covers_mpn=MPN)
        sibling = ingest(store, identity_scope=IdentityScope.EXACT_SKU, covers_mpn="BASE100Y2")
        catalogue = self.range_artifact(store, ["only page"])

        assert artifact_scope_binding(exact, MPN) is ScopeBinding.EXACT
        assert artifact_scope_binding(sibling, MPN) is ScopeBinding.CONTRADICTED
        assert artifact_scope_binding(catalogue, MPN) is ScopeBinding.NOT_ESTABLISHED


class TestPhraseBoundaryMatching:
    """Short controlled values must not be found inside longer words."""

    def alpha(self, store, text, *, page=3, fragment="Housing Stainless Steel", pages=None):
        artifact = ingest(store, pages)
        return verify_claim(
            claim(
                artifact,
                value=AlphanumericValue(text=text, raw=text),
                page=page,
                fragment=fragment,
                key="EF000123",
            ),
            store=store,
        )

    def test_standalone_short_token_verifies(self, store):
        """E."""
        pages = ["x", "y", "Voltage type AC"]
        result = self.alpha(store, "AC", fragment="Voltage type AC", pages=pages)
        assert result.status is EvidenceVerification.EXACT_SPAN

    @pytest.mark.parametrize("line", ["Housing VACUUM formed", "Mounted on a STACK rail"])
    def test_short_token_inside_a_word_does_not_verify(self, store, line):
        """F. The regression the old substring matcher would have passed."""
        result = self.alpha(store, "AC", fragment=line, pages=["x", "y", line])
        assert result.failure is VerificationFailure.VALUE_NOT_SUPPORTED

    def test_contact_token_verifies(self, store):
        """G."""
        result = self.alpha(store, "NO", fragment="3 NO main contacts")
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_no_does_not_match_normal(self, store):
        """H."""
        line = "Operation NORMAL under load"
        result = self.alpha(store, "NO", fragment=line, pages=["x", "y", line])
        assert result.failure is VerificationFailure.VALUE_NOT_SUPPORTED

    def test_exact_category_token_verifies(self, store):
        """I."""
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))),
            store=store,
        )
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_category_token_is_not_matched_by_a_longer_code(self, store):
        """J. `AC-3` must not be read out of `AC-30`."""
        line = "18 A (at <60 °C) at <= 440 V AC AC-30 for power circuit"
        artifact = ingest(store, ["x", line])
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))),
            store=store,
        )
        assert result.failure is VerificationFailure.CONDITION_NOT_SUPPORTED

    def test_multiword_phrase_verifies(self, store):
        """K."""
        result = self.alpha(store, "Stainless Steel")
        assert result.status is EvidenceVerification.EXACT_SPAN

    def test_phrase_is_not_matched_as_an_interior_substring(self, store):
        """L."""
        line = "Housing ULTRASTAINLESS STEELWORKS alloy"
        result = self.alpha(store, "Stainless Steel", fragment=line, pages=["x", "y", line])
        assert result.failure is VerificationFailure.VALUE_NOT_SUPPORTED

    def test_controlled_vocabulary_synonym_is_still_unverified(self, store):
        """M. A correct mapping is not a located span. It stays adjudication's job."""
        line = "Connection by screw clamp terminals"
        result = self.alpha(store, "Screw connection", fragment=line, pages=["x", "y", line])
        assert result.failure is VerificationFailure.VALUE_NOT_SUPPORTED

    @pytest.mark.parametrize(
        ("haystack", "phrase", "expected"),
        [
            ("Voltage type AC", "AC", True),
            ("AC-3 rated", "AC-3", True),
            ("AC-3 rated", "AC", False),
            ("AC-30 rated", "AC-3", False),
            ("VACUUM", "AC", False),
            ("BRASS body", "Brass", True),
            ("Brass-plated body", "Brass", False),
            ("Housing: Stainless Steel.", "Stainless Steel", True),
            ("Stainless  Steel", "Stainless Steel", True),
            ("screw clamp terminals", "Screw connection", False),
        ],
    )
    def test_boundary_rule(self, haystack, phrase, expected):
        from skutruth.verification import contains_phrase

        assert contains_phrase(haystack, phrase) is expected


class TestTypedConditionFailures:
    """Failure classification comes from the comparison, never from its own prose."""

    def test_operator_mismatch_reason_is_typed(self, store):
        """N."""
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.TEMPERATURE, "60 °C"))), store=store
        )
        assert result.failure is VerificationFailure.OPERATOR_MISMATCH
        unmet = [o for o in result.condition_outcomes if not o.supported]
        assert [o.failure for o in unmet] == [VerificationFailure.OPERATOR_MISMATCH]

    def test_unsupported_condition_reason_is_typed(self, store):
        """O."""
        artifact = ingest(store)
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-4"))),
            store=store,
        )
        assert result.failure is VerificationFailure.CONDITION_NOT_SUPPORTED
        unmet = [o for o in result.condition_outcomes if not o.supported]
        assert all(o.failure is VerificationFailure.CONDITION_NOT_SUPPORTED for o in unmet)

    def test_every_unsupported_outcome_carries_a_typed_reason(self, store):
        """The invariant that replaces sniffing `detail`."""
        artifact = ingest(store)
        for condition_value in ("60 °C", "AC-4", "999 V", "50 Hz"):
            result = verify_claim(
                claim(artifact, conds=conditions((ConditionKind.OTHER, condition_value))),
                store=store,
            )
            for outcome in result.condition_outcomes:
                assert outcome.supported or outcome.failure is not None

    def test_multi_quantity_condition_fails_closed(self, store):
        """P. `400 V` is on the line; `50 Hz` is not, and must not be discarded."""
        artifact = ingest(store, ["x", "18 A at 400 V AC-3 for power circuit"])
        result = verify_claim(
            claim(artifact, conds=conditions((ConditionKind.OTHER, "400 V 50 Hz"))), store=store
        )
        assert result.status is EvidenceVerification.UNVERIFIED
        assert result.failure is VerificationFailure.CONDITION_NOT_SUPPORTED
        assert "independent quantities" in result.condition_outcomes[0].detail

    def test_enumerated_claim_needs_every_alternative(self, store):
        """`50/60 Hz` claimed is two assertions, not one."""
        supported = verify_claim(
            claim(
                ingest(store),
                page=3,
                fragment="Control supply 230 V AC 50/60 Hz",
                value=NumericValue(number=230.0, unit="V", raw="230 V"),
                conds=conditions((ConditionKind.FREQUENCY, "50/60 Hz")),
            ),
            store=store,
        )
        assert supported.status is EvidenceVerification.EXACT_SPAN

        line = "Control supply 230 V AC 50 Hz"
        partial = verify_claim(
            claim(
                ingest(store, ["x", "y", line]),
                page=3,
                fragment=line,
                value=NumericValue(number=230.0, unit="V", raw="230 V"),
                conds=conditions((ConditionKind.FREQUENCY, "50/60 Hz")),
            ),
            store=store,
        )
        assert partial.failure is VerificationFailure.CONDITION_NOT_SUPPORTED
