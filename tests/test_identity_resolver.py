"""Deterministic identity resolution.

Every fixture is synthetic. No test here depends on a local manufacturer artifact, and
no real manufacturer reference appears — the resolver must contain no vendor logic, so
its tests must not smuggle any in either.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from skutruth.contracts import IdentityDisposition, IdentityScope, ProductInput
from skutruth.identity import (
    DecisionStep,
    DiscriminatorMappingFact,
    DiscriminatorSelection,
    EvidenceAnchor,
    ExactReferenceFact,
    IdentityEvidence,
    MalformedConstructionRule,
    ReferenceCompletionFact,
    VariationAxisFact,
    canonical_brand,
    identity_prediction_fields,
    resolve_identity,
    to_case_prediction,
)
from skutruth.identity.evidence import validate_construction_template

BRAND = "TestCo"
OTHER_BRAND = "RivalCo"
BASE = "BASE100"
CODE_X = "X1"
CODE_Y = "Y2"
CANDIDATE_X = "BASE100X1"
CANDIDATE_Y = "BASE100Y2"
KEY = "control_circuit"
VALUE = "ac_230v_50_60hz"

CATALOGUE_SHA = "a" * 64
DATASHEET_SHA = "b" * 64


def anchor(sha: str = CATALOGUE_SHA, scope: IdentityScope = IdentityScope.RANGE, **kw):
    return EvidenceAnchor(
        artifact_sha256=sha,
        page_number=kw.pop("page", 4),
        publisher=kw.pop("publisher", BRAND),
        identity_scope=scope,
        observed_statement=kw.pop("statement", "base reference completed by a code"),
    )


def completion(brand: str = BRAND, base: str = BASE, key: str = KEY):
    return ReferenceCompletionFact(
        brand=brand, base_mpn=base, discriminator_key=key, anchor=anchor()
    )


def mapping(code: str = CODE_X, *, brand: str = BRAND, value: str = VALUE, template=None):
    kwargs = {} if template is None else {"construction_template": template}
    return DiscriminatorMappingFact(
        brand=brand,
        base_mpn=BASE,
        discriminator_key=KEY,
        canonical_value=value,
        completion_code=code,
        label="230 V AC, 50/60 Hz",
        anchor=anchor(),
        **kwargs,
    )


def exact(mpn: str, brand: str = BRAND, status: str | None = "Commercialised"):
    return ExactReferenceFact(
        brand=brand,
        exact_mpn=mpn,
        commercial_status=status,
        anchor=anchor(DATASHEET_SHA, IdentityScope.EXACT_SKU, page=1, statement=f"{mpn} exists"),
    )


def product(mpn: str = BASE, brand: str = BRAND) -> ProductInput:
    return ProductInput(brand=brand, mpn=mpn, description="Widget")


SELECTION = DiscriminatorSelection(key=KEY, canonical_value=VALUE, label="230 V AC, 50/60 Hz")


class TestIncompleteReference:
    """A base reference with nothing bound is a question, not a product."""

    def test_missing_discriminator_is_family_or_incomplete(self):
        result = resolve_identity(product(), IdentityEvidence(completion_facts=(completion(),)))
        assert result.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        assert result.unresolved_discriminators == (KEY,)

    def test_no_default_variant_is_guessed(self):
        """Even with exactly one mapping available, an unsupplied selection stays unbound."""
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(),),
            exact_facts=(exact(CANDIDATE_X),),
        )
        result = resolve_identity(product(), evidence)
        assert result.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        assert result.exact_mpn is None
        assert result.candidate_references == ()

    def test_selection_without_a_mapping_rule_does_not_invent_a_code(self):
        evidence = IdentityEvidence(completion_facts=(completion(),), mapping_facts=())
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        assert result.candidate_references == ()
        assert any(e.code is DecisionStep.SELECTION_NOT_MAPPED for e in result.trace)


class TestCandidateIsNotExact:
    """The central regression: a constructed candidate must never score as resolved."""

    def test_candidate_without_exact_evidence_is_not_exact(self):
        evidence = IdentityEvidence(completion_facts=(completion(),), mapping_facts=(mapping(),))
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.disposition is not IdentityDisposition.EXACT
        assert result.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        assert result.candidate_references == (CANDIDATE_X,)
        assert result.candidate_exactness_confirmed is False

    def test_unconfirmed_candidate_is_never_exposed_as_exact_mpn(self):
        evidence = IdentityEvidence(completion_facts=(completion(),), mapping_facts=(mapping(),))
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.exact_mpn is None

    def test_model_forbids_exact_mpn_on_a_non_exact_disposition(self):
        """Defence in depth: the shape itself refuses to carry a candidate as resolved."""
        from skutruth.identity.models import IdentityResolution

        evidence = IdentityEvidence(completion_facts=(completion(),), mapping_facts=(mapping(),))
        result = resolve_identity(product(), evidence, (SELECTION,))
        with pytest.raises(ValidationError, match="must not carry exact_mpn"):
            IdentityResolution.model_validate(result.model_dump() | {"exact_mpn": CANDIDATE_X})

    def test_model_requires_exact_mpn_when_disposition_is_exact(self):
        from skutruth.identity.models import IdentityResolution

        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X),))
        result = resolve_identity(product(CANDIDATE_X), evidence)
        with pytest.raises(ValidationError, match="EXACT requires exact_mpn"):
            IdentityResolution.model_validate(result.model_dump() | {"exact_mpn": None})

    def test_sibling_exact_evidence_does_not_confirm_the_candidate(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(CODE_X),),
            exact_facts=(exact(CANDIDATE_Y),),  # a sibling, not our candidate
        )
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        assert result.candidate_references == (CANDIDATE_X,)
        assert result.exact_mpn is None


class TestExactConfirmation:
    def test_candidate_with_matching_exact_evidence_is_exact(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(),),
            exact_facts=(exact(CANDIDATE_X),),
        )
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.disposition is IdentityDisposition.EXACT
        assert result.exact_mpn == CANDIDATE_X
        assert result.candidate_exactness_confirmed is True

    def test_direct_exact_input_resolves_without_rebuilding_a_base(self):
        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X),))
        result = resolve_identity(product(CANDIDATE_X), evidence)
        assert result.disposition is IdentityDisposition.EXACT
        assert result.exact_mpn == CANDIDATE_X
        # Nothing was constructed on this path.
        assert result.candidate_exactness_confirmed is False
        assert result.candidate_references == ()

    def test_exact_matching_is_case_and_whitespace_insensitive_only(self):
        evidence = IdentityEvidence(exact_facts=(exact("base100 x1"),))
        assert resolve_identity(product("BASE100X1"), evidence).disposition is (
            IdentityDisposition.EXACT
        )

    def test_hyphenation_is_not_folded_away(self):
        """Conservative canonicalisation: a hyphen may distinguish real parts."""
        evidence = IdentityEvidence(exact_facts=(exact("BASE100-X1"),))
        assert resolve_identity(product("BASE100X1"), evidence).disposition is (
            IdentityDisposition.UNKNOWN
        )


class TestExactEvidenceMustBeExactSkuScoped:
    """Only evidence bound to one commercial reference may license EXACT.

    A catalogue is RANGE: it can prove a reference is a family stem, but it lists codes
    rather than which combinations are built, so it can never establish that one
    particular child exists. The invariant sits on the model, so such a fact cannot be
    constructed at all.
    """

    def test_exact_sku_scoped_anchor_is_valid(self):
        fact = ExactReferenceFact(
            brand=BRAND,
            exact_mpn=CANDIDATE_X,
            anchor=anchor(DATASHEET_SHA, IdentityScope.EXACT_SKU, page=1, statement="exists"),
        )
        assert fact.anchor.identity_scope is IdentityScope.EXACT_SKU

    @pytest.mark.parametrize("scope", [IdentityScope.RANGE, IdentityScope.FAMILY])
    def test_broader_scope_is_rejected(self, scope):
        with pytest.raises(ValidationError, match="EXACT_SKU"):
            ExactReferenceFact(
                brand=BRAND,
                exact_mpn=CANDIDATE_X,
                anchor=anchor(DATASHEET_SHA, scope, page=1, statement="catalogue row"),
            )

    def test_missing_identity_scope_is_rejected(self):
        unscoped = EvidenceAnchor(
            artifact_sha256=DATASHEET_SHA,
            page_number=1,
            publisher=BRAND,
            observed_statement="scope not recorded",
        )
        assert unscoped.identity_scope is None
        with pytest.raises(ValidationError, match="no identity_scope"):
            ExactReferenceFact(brand=BRAND, exact_mpn=CANDIDATE_X, anchor=unscoped)

    def test_scope_is_never_silently_upgraded(self):
        """Rejection, not correction. A rewritten scope would forge provenance."""
        with pytest.raises(ValidationError):
            ExactReferenceFact(
                brand=BRAND,
                exact_mpn=CANDIDATE_X,
                anchor=anchor(CATALOGUE_SHA, IdentityScope.RANGE, statement="catalogue row"),
            )

    def test_range_scoped_exact_evidence_cannot_reach_the_resolver(self):
        """The candidate path stays non-EXACT because the fact is inadmissible."""
        with pytest.raises(ValidationError):
            IdentityEvidence(
                completion_facts=(completion(),),
                mapping_facts=(mapping(),),
                exact_facts=(
                    ExactReferenceFact(
                        brand=BRAND,
                        exact_mpn=CANDIDATE_X,
                        anchor=anchor(CATALOGUE_SHA, IdentityScope.RANGE),
                    ),
                ),
            )

        # With that fact absent, the candidate is constructed but never confirmed.
        result = resolve_identity(
            product(),
            IdentityEvidence(completion_facts=(completion(),), mapping_facts=(mapping(),)),
            (SELECTION,),
        )
        assert result.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        assert result.candidate_references == (CANDIDATE_X,)
        assert result.exact_mpn is None

    def test_direct_exact_input_still_resolves_with_a_properly_scoped_fact(self):
        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X),))
        result = resolve_identity(product(CANDIDATE_X), evidence)
        assert result.disposition is IdentityDisposition.EXACT
        assert result.exact_mpn == CANDIDATE_X

    def test_other_fact_types_still_accept_range_scoped_catalogue_evidence(self):
        """Only the fact that licenses EXACT is restricted; catalogue evidence stays usable."""
        range_anchor = anchor(CATALOGUE_SHA, IdentityScope.RANGE)
        assert ReferenceCompletionFact(
            brand=BRAND, base_mpn=BASE, discriminator_key=KEY, anchor=range_anchor
        )
        assert DiscriminatorMappingFact(
            brand=BRAND,
            base_mpn=BASE,
            discriminator_key=KEY,
            canonical_value=VALUE,
            completion_code=CODE_X,
            anchor=range_anchor,
        )
        assert VariationAxisFact(
            brand=BRAND,
            base_mpn=BASE,
            axis_key="connection_type",
            description="variants exist",
            anchor=range_anchor,
        )


class TestUnknown:
    def test_no_evidence_is_unknown_not_exact(self):
        result = resolve_identity(product("NEVERSEEN9"), IdentityEvidence())
        assert result.disposition is IdentityDisposition.UNKNOWN
        assert result.exact_mpn is None

    def test_family_evidence_for_another_reference_does_not_resolve_this_one(self):
        evidence = IdentityEvidence(completion_facts=(completion(base="OTHERBASE"),))
        assert resolve_identity(product(), evidence).disposition is (IdentityDisposition.UNKNOWN)


class TestContradictory:
    def test_exact_and_incomplete_for_the_same_reference(self):
        evidence = IdentityEvidence(completion_facts=(completion(),), exact_facts=(exact(BASE),))
        result = resolve_identity(product(), evidence)
        assert result.disposition is IdentityDisposition.CONTRADICTORY
        codes = [e.code for e in result.trace]
        assert codes.count(DecisionStep.CONFLICT_EXACT_AND_INCOMPLETE) == 2

    def test_rival_completion_codes_for_one_selection(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(CODE_X), mapping(CODE_Y)),
        )
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.disposition is IdentityDisposition.CONTRADICTORY
        assert set(result.candidate_references) == {CANDIDATE_X, CANDIDATE_Y}
        assert result.exact_mpn is None

    def test_duplicate_identical_mappings_are_not_a_conflict(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(CODE_X), mapping(CODE_X)),
        )
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        assert result.candidate_references == (CANDIDATE_X,)

    def test_conflict_does_not_prefer_the_first_fact(self):
        forward = IdentityEvidence(
            completion_facts=(completion(),), mapping_facts=(mapping(CODE_X), mapping(CODE_Y))
        )
        reversed_ = IdentityEvidence(
            completion_facts=(completion(),), mapping_facts=(mapping(CODE_Y), mapping(CODE_X))
        )
        a = resolve_identity(product(), forward, (SELECTION,))
        b = resolve_identity(product(), reversed_, (SELECTION,))
        assert a.disposition is b.disposition is IdentityDisposition.CONTRADICTORY
        assert a.candidate_references == b.candidate_references


class TestBrandBinding:
    def test_evidence_for_another_brand_cannot_resolve_this_one(self):
        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X, brand=OTHER_BRAND),))
        result = resolve_identity(product(CANDIDATE_X), evidence)
        assert result.disposition is IdentityDisposition.UNKNOWN
        assert result.warnings

    def test_ignored_brand_evidence_is_surfaced_in_the_trace(self):
        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X, brand=OTHER_BRAND),))
        result = resolve_identity(product(CANDIDATE_X), evidence)
        assert any(e.code is DecisionStep.BRAND_EVIDENCE_IGNORED for e in result.trace)

    def test_brand_normalization_is_case_and_whitespace_only(self):
        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X, brand="testco"),))
        assert (
            resolve_identity(product(CANDIDATE_X, brand="  TestCo  "), evidence).disposition
            is IdentityDisposition.EXACT
        )

    def test_brand_prefix_is_not_a_match(self):
        assert canonical_brand("Schneider") != canonical_brand("Schneider Electric")
        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X, brand="Widget Corp"),))
        assert (
            resolve_identity(product(CANDIDATE_X, brand="Widget"), evidence).disposition
            is IdentityDisposition.UNKNOWN
        )


class TestConstruction:
    def test_construction_is_deterministic(self):
        evidence = IdentityEvidence(completion_facts=(completion(),), mapping_facts=(mapping(),))
        first = resolve_identity(product(), evidence, (SELECTION,))
        second = resolve_identity(product(), evidence, (SELECTION,))
        assert first == second
        assert first.candidate_references == (CANDIDATE_X,)

    def test_custom_template_is_honoured(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(template="{base}-{code}"),),
        )
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.candidate_references == ("BASE100-X1",)

    def test_template_without_code_placeholder_is_rejected(self):
        with pytest.raises(ValidationError):
            mapping(template="{base}")

    def test_template_with_unknown_placeholder_is_rejected(self):
        with pytest.raises(ValidationError):
            mapping(template="{base}{code}{region}")

    def test_template_validation_raises_the_typed_error(self):
        with pytest.raises(MalformedConstructionRule):
            validate_construction_template("{base}-{unknown}")


class TestVariationAxes:
    """Extra axes inform; they do not silently block."""

    def _axes(self, blocks: bool = False):
        return (
            VariationAxisFact(
                brand=BRAND,
                base_mpn=BASE,
                axis_key="connection_type",
                description="screw clamp and spring terminal variants exist",
                blocks_resolution=blocks,
                anchor=anchor(),
            ),
            VariationAxisFact(
                brand=BRAND,
                base_mpn=BASE,
                axis_key="sub_range",
                description="a separate eco sub-range exists",
                anchor=anchor(),
            ),
        )

    def test_axes_are_reported_without_blocking_exact_resolution(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(),),
            exact_facts=(exact(CANDIDATE_X),),
            variation_axes=self._axes(),
        )
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.disposition is IdentityDisposition.EXACT
        assert result.known_variation_axes == ("connection_type", "sub_range")
        assert any("additional axes" in w for w in result.warnings)

    def test_axes_are_not_added_to_unresolved_discriminators(self):
        evidence = IdentityEvidence(completion_facts=(completion(),), variation_axes=self._axes())
        result = resolve_identity(product(), evidence)
        assert result.unresolved_discriminators == (KEY,)

    def test_a_blocking_axis_is_required_only_when_evidence_says_so(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(),),
            exact_facts=(exact(CANDIDATE_X),),
            variation_axes=self._axes(blocks=True),
        )
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert result.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        assert "connection_type" in result.unresolved_discriminators


class TestTrace:
    def test_trace_is_numbered_and_deterministic(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(),),
            exact_facts=(exact(CANDIDATE_X),),
        )
        result = resolve_identity(product(), evidence, (SELECTION,))
        assert [e.step for e in result.trace] == list(range(1, len(result.trace) + 1))
        assert result == resolve_identity(product(), evidence, (SELECTION,))

    def test_trace_records_the_full_exact_path(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(),),
            exact_facts=(exact(CANDIDATE_X),),
        )
        codes = [e.code for e in resolve_identity(product(), evidence, (SELECTION,)).trace]
        assert DecisionStep.BASE_REFERENCE_INCOMPLETE in codes
        assert DecisionStep.CANDIDATE_CONSTRUCTED in codes
        assert DecisionStep.EXACT_REFERENCE_CONFIRMED in codes

    def test_explain_renders_every_step(self):
        evidence = IdentityEvidence(completion_facts=(completion(),))
        result = resolve_identity(product(), evidence)
        assert len(result.explain().splitlines()) == len(result.trace)

    def test_anchors_used_are_collected(self):
        evidence = IdentityEvidence(
            completion_facts=(completion(),),
            mapping_facts=(mapping(),),
            exact_facts=(exact(CANDIDATE_X),),
        )
        shas = {
            a.artifact_sha256
            for a in resolve_identity(product(), evidence, (SELECTION,)).evidence_anchors
        }
        assert shas == {CATALOGUE_SHA, DATASHEET_SHA}


class TestNoConfidenceScores:
    def test_no_probability_field_exists_anywhere_in_the_result(self):
        """A float would invite callers to treat 0.9 as 'exact enough'."""
        from skutruth.identity.models import IdentityResolution

        for name, field in IdentityResolution.model_fields.items():
            assert "float" not in str(field.annotation).lower(), name
            assert not any(
                token in name.lower() for token in ("confidence", "probability", "score")
            ), name


class TestEvalAdapter:
    def test_exact_resolution_reports_its_mpn(self):
        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X),))
        fields = identity_prediction_fields(resolve_identity(product(CANDIDATE_X), evidence))
        assert fields["identity_disposition"] is IdentityDisposition.EXACT
        assert fields["identity_mpn"] == CANDIDATE_X

    def test_unconfirmed_candidate_never_reaches_the_resolved_mpn_field(self):
        """The false-exact guard: a guess must not be scored as a resolution."""
        evidence = IdentityEvidence(completion_facts=(completion(),), mapping_facts=(mapping(),))
        resolution = resolve_identity(product(), evidence, (SELECTION,))
        fields = identity_prediction_fields(resolution)
        assert resolution.candidate_references == (CANDIDATE_X,)
        assert fields["identity_disposition"] is (
            IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        )
        assert fields["identity_mpn"] is None

    def test_case_prediction_carries_no_attributes(self):
        evidence = IdentityEvidence(exact_facts=(exact(CANDIDATE_X),))
        prediction = to_case_prediction(
            resolve_identity(product(CANDIDATE_X), evidence), case_id="case-1"
        )
        assert prediction.case_id == "case-1"
        assert prediction.attributes == ()
        assert prediction.succeeded


class TestNoVendorLogicInResolver:
    def test_resolver_source_contains_no_manufacturer_specifics(self):
        """The vertical slice must live in evidence, never in the decision code."""
        from pathlib import Path

        import skutruth.identity as pkg

        source = "\n".join(
            p.read_text(encoding="utf-8") for p in Path(pkg.__file__).parent.glob("*.py")
        ).upper()
        for token in ("LC1D18", "SCHNEIDER", "TESYS", "P7"):
            assert token not in source, f"{token} must not appear in identity logic"

    def test_resolver_does_not_import_a_pdf_library(self):
        from pathlib import Path

        import skutruth.identity as pkg

        source = "\n".join(
            p.read_text(encoding="utf-8") for p in Path(pkg.__file__).parent.glob("*.py")
        )
        for token in ("import pdfplumber", "import pypdf", "from pdfplumber", "from pypdf"):
            assert token not in source
