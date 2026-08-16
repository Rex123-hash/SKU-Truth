"""Model-backed extraction, offline.

No test here needs Vertex, credentials, or a network. The provider is a deterministic
fake, and the document is the synthetic PDF used across ingestion tests — the real
Schneider run is a local, uncommitted script.
"""

from __future__ import annotations

import pytest
from conftest_pdf import datasheet_pdf
from pydantic import ValidationError
from skutruth.contracts import (
    ConditionCompleteness,
    ConditionKind,
    IdentityScope,
    ProductInput,
    RunMode,
)
from skutruth.etim.demo_classes import load_demo_class
from skutruth.etim.loader import load_etim
from skutruth.etim.schema_gen import build_extraction_schema
from skutruth.extraction import (
    PROMPT_VERSION,
    ExtractionCandidate,
    IdentityNotExactError,
    ProviderResult,
    RejectionCode,
    VertexConfig,
    build_interaction_request,
    extract_product_attributes,
    require_exact_identity,
)
from skutruth.identity import (
    EvidenceAnchor,
    ExactReferenceFact,
    IdentityEvidence,
    ReferenceCompletionFact,
    resolve_identity,
)
from skutruth.ingest import ingest_pdf_bytes
from skutruth.replay.errors import ReplayMissError
from skutruth.replay.store import CassetteStore

CLASS_ID = "EC000066"
CURRENT = "EF001392"  # numeric, amperes, requires utilization category + voltage
BRAND = "TestCo"
EXACT_MPN = "BASE100X1"
SHA = "a" * 64


@pytest.fixture(scope="module")
def etim_class():
    return load_etim().require(CLASS_ID)


@pytest.fixture(scope="module")
def demo_config():
    return load_demo_class(CLASS_ID)


@pytest.fixture(scope="module")
def artifact_bytes():
    return datasheet_pdf()


@pytest.fixture(scope="module")
def artifact(artifact_bytes):
    return ingest_pdf_bytes(artifact_bytes)


def anchor(scope=IdentityScope.EXACT_SKU):
    return EvidenceAnchor(
        artifact_sha256=SHA,
        page_number=1,
        publisher=BRAND,
        identity_scope=scope,
        observed_statement="reference exists",
    )


def exact_identity():
    return resolve_identity(
        ProductInput(brand=BRAND, mpn=EXACT_MPN, description="Widget"),
        IdentityEvidence(
            exact_facts=(ExactReferenceFact(brand=BRAND, exact_mpn=EXACT_MPN, anchor=anchor()),)
        ),
    )


def incomplete_identity():
    return resolve_identity(
        ProductInput(brand=BRAND, mpn="BASE100", description="Widget"),
        IdentityEvidence(
            completion_facts=(
                ReferenceCompletionFact(
                    brand=BRAND,
                    base_mpn="BASE100",
                    discriminator_key="control_circuit",
                    anchor=anchor(IdentityScope.RANGE),
                ),
            )
        ),
    )


def payload(features: dict) -> dict:
    return {"etim_class_id": CLASS_ID, "features": features}


def current_proposal(**overrides):
    base = {
        "number": 18,
        "unit": "A",
        "raw_text": "18 A at <= 440 V AC AC-3",
        "page": 1,
        "conditions": [
            {"kind": "UTILIZATION_CATEGORY", "value": "AC-3"},
            {"kind": "VOLTAGE", "value": "440 V"},
        ],
    }
    base.update(overrides)
    return base


class FakeProvider:
    """Returns a fixed payload and counts calls. The whole provider surface."""

    def __init__(self, response: dict):
        self.response = response
        self.calls = 0
        self.last_call = None

    def generate(self, call):
        self.calls += 1
        self.last_call = call
        return ProviderResult(payload=self.response)


def run(
    tmp_path,
    *,
    features,
    identity=None,
    mode=RunMode.LIVE,
    provider=None,
    etim_class=None,
    demo_config=None,
    artifact=None,
    artifact_bytes=None,
    config=None,
    feature_ids=(CURRENT,),
):
    provider = provider or FakeProvider(payload(features))
    return extract_product_attributes(
        identity=identity or exact_identity(),
        artifact=artifact,
        artifact_bytes=artifact_bytes,
        etim_class=etim_class,
        provider=provider,
        store=CassetteStore(tmp_path, writable=True),
        config=config or VertexConfig(project="test-project"),
        mode=mode,
        demo_config=demo_config,
        feature_ids=feature_ids,
    ), provider


@pytest.fixture
def go(tmp_path, etim_class, demo_config, artifact, artifact_bytes):
    def _go(**kw):
        kw.setdefault("etim_class", etim_class)
        kw.setdefault("demo_config", demo_config)
        kw.setdefault("artifact", artifact)
        kw.setdefault("artifact_bytes", artifact_bytes)
        return run(tmp_path, **kw)

    return _go


class TestIdentityGate:
    def test_non_exact_identity_is_refused(self, go):
        with pytest.raises(IdentityNotExactError, match="FAMILY_OR_INCOMPLETE"):
            go(features={}, identity=incomplete_identity())

    def test_unknown_identity_is_refused(self, go):
        unknown = resolve_identity(
            ProductInput(brand=BRAND, mpn="NEVERSEEN1", description="x"), IdentityEvidence()
        )
        with pytest.raises(IdentityNotExactError, match="UNKNOWN"):
            go(features={}, identity=unknown)

    def test_exact_identity_is_accepted(self, go):
        result, _ = go(features={CURRENT: current_proposal()})
        assert result.target.exact_mpn == EXACT_MPN
        assert result.validated.candidate_count == 1

    def test_gate_helper_returns_the_reference(self):
        assert require_exact_identity(exact_identity()) == EXACT_MPN

    def test_model_is_never_asked_which_product(self, go):
        """The refusal happens before any provider call."""
        provider = FakeProvider(payload({}))
        with pytest.raises(IdentityNotExactError):
            go(features={}, identity=incomplete_identity(), provider=provider)
        assert provider.calls == 0


class TestRequestDescriptor:
    def test_descriptor_carries_model_prompt_schema_and_artifact(
        self, etim_class, demo_config, artifact
    ):
        from skutruth.extraction.models import ExtractionTarget

        schema = build_extraction_schema(etim_class, demo_config)
        target = ExtractionTarget(
            brand=BRAND,
            exact_mpn=EXACT_MPN,
            etim_class_id=CLASS_ID,
            artifact_sha256=artifact.sha256,
            page_count=artifact.page_count,
        )
        request = build_interaction_request(
            target, schema, VertexConfig(project="p", location="europe-west4", model="m-1")
        )
        assert request.provider == "vertex-ai"
        assert request.model == "m-1"
        assert request.prompt_version == PROMPT_VERSION
        assert request.schema_version == schema.fingerprint()
        assert request.artifact_hashes == (artifact.sha256,)
        assert request.payload["location"] == "europe-west4"

    def test_model_change_changes_the_replay_key(self, etim_class, demo_config, artifact):
        from skutruth.extraction.models import ExtractionTarget

        schema = build_extraction_schema(etim_class, demo_config)
        target = ExtractionTarget(
            brand=BRAND,
            exact_mpn=EXACT_MPN,
            etim_class_id=CLASS_ID,
            artifact_sha256=artifact.sha256,
            page_count=artifact.page_count,
        )
        a = build_interaction_request(target, schema, VertexConfig(project="p", model="m-1"))
        b = build_interaction_request(target, schema, VertexConfig(project="p", model="m-2"))
        assert a.key_material() != b.key_material()

    def test_location_change_changes_the_replay_key(self, etim_class, demo_config, artifact):
        from skutruth.extraction.models import ExtractionTarget

        schema = build_extraction_schema(etim_class, demo_config)
        target = ExtractionTarget(
            brand=BRAND,
            exact_mpn=EXACT_MPN,
            etim_class_id=CLASS_ID,
            artifact_sha256=artifact.sha256,
            page_count=artifact.page_count,
        )
        a = build_interaction_request(target, schema, VertexConfig(project="p", location="a"))
        b = build_interaction_request(target, schema, VertexConfig(project="p", location="b"))
        assert a.key_material() != b.key_material()

    def test_schema_narrowing_changes_the_replay_key(self, etim_class, demo_config, artifact):
        from skutruth.extraction.models import ExtractionTarget

        target = ExtractionTarget(
            brand=BRAND,
            exact_mpn=EXACT_MPN,
            etim_class_id=CLASS_ID,
            artifact_sha256=artifact.sha256,
            page_count=artifact.page_count,
        )
        cfg = VertexConfig(project="p")
        full = build_extraction_schema(etim_class, demo_config)
        one = build_extraction_schema(etim_class, demo_config, feature_ids=(CURRENT,))
        assert build_interaction_request(target, full, cfg).key_material() != (
            build_interaction_request(target, one, cfg).key_material()
        )


class TestValidation:
    def test_schema_conforming_response_parses(self, go):
        result, _ = go(features={CURRENT: current_proposal()})
        candidate = result.validated.candidate(CURRENT)
        assert candidate is not None
        assert candidate.value.number == 18.0
        assert candidate.value.unit == "A"
        assert candidate.page_number == 1

    def test_unknown_feature_is_rejected(self, go):
        result, _ = go(features={"EF999999": current_proposal()})
        assert result.validated.candidate_count == 0
        assert result.validated.rejected[0].code is RejectionCode.UNKNOWN_FEATURE

    def test_wrong_value_kind_is_rejected(self, go):
        """A numeric ETIM feature offered a text value."""
        result, _ = go(features={CURRENT: current_proposal(number=None, text="eighteen")})
        assert result.validated.candidate_count == 0
        assert result.validated.rejected[0].code is RejectionCode.INVALID_VALUE

    def test_incompatible_unit_is_rejected(self, go):
        result, _ = go(features={CURRENT: current_proposal(unit="V")})
        assert result.validated.candidate_count == 0
        assert result.validated.rejected[0].code is RejectionCode.INVALID_VALUE

    def test_compatible_unit_is_converted_by_existing_deterministic_layer(self, go):
        """18000 mA is 18 A. The model proposes; `units.normalize_numeric` converts."""
        result, _ = go(features={CURRENT: current_proposal(number=18000, unit="mA")})
        candidate = result.validated.candidate(CURRENT)
        assert candidate.value.number == pytest.approx(18.0)
        assert candidate.value.unit == "A"

    def test_page_zero_is_rejected(self, go):
        result, _ = go(features={CURRENT: current_proposal(page=0)})
        assert result.validated.candidate_count == 0
        assert result.validated.rejected[0].code in {
            RejectionCode.MALFORMED_PROPOSAL,
            RejectionCode.MISSING_SOURCE_FRAGMENT,
        }

    def test_page_beyond_the_artifact_is_rejected_not_clamped(self, go, artifact):
        result, _ = go(features={CURRENT: current_proposal(page=artifact.page_count + 5)})
        assert result.validated.candidate_count == 0
        rejection = result.validated.rejected[0]
        assert rejection.code is RejectionCode.PAGE_OUT_OF_RANGE
        assert "does not exist" in rejection.detail

    def test_value_without_source_fragment_is_rejected(self, go):
        proposal = current_proposal()
        del proposal["raw_text"]
        result, _ = go(features={CURRENT: proposal})
        assert result.validated.candidate_count == 0
        assert result.validated.rejected[0].code is RejectionCode.MISSING_SOURCE_FRAGMENT

    def test_value_without_page_is_rejected(self, go):
        proposal = current_proposal()
        del proposal["page"]
        result, _ = go(features={CURRENT: proposal})
        assert result.validated.rejected[0].code is RejectionCode.MISSING_SOURCE_FRAGMENT

    def test_null_abstention_is_accepted_and_recorded(self, go):
        result, _ = go(features={CURRENT: None})
        assert result.validated.candidate_count == 0
        assert result.validated.rejected == ()
        assert result.validated.abstained_feature_ids == (CURRENT,)

    def test_non_object_proposal_is_rejected(self, go):
        result, _ = go(features={CURRENT: "18 A"})
        assert result.validated.rejected[0].code is RejectionCode.MALFORMED_PROPOSAL

    def test_validation_is_order_independent(self, go, etim_class, demo_config, artifact):
        """Cassettes store sorted keys; output must not depend on payload key order."""
        from skutruth.extraction.models import ExtractionTarget, RawModelExtraction
        from skutruth.extraction.service import validate_raw_extraction

        schema = build_extraction_schema(etim_class, demo_config)
        target = ExtractionTarget(
            brand=BRAND,
            exact_mpn=EXACT_MPN,
            etim_class_id=CLASS_ID,
            artifact_sha256=artifact.sha256,
            page_count=artifact.page_count,
        )
        features = {
            CURRENT: current_proposal(),
            "EF001374": {"number": 3, "raw_text": "3 NO", "page": 1, "conditions": []},
        }
        forward = dict(features)
        backward = {k: features[k] for k in reversed(list(features))}

        def validated(p):
            raw = RawModelExtraction(
                model="m",
                prompt_version=PROMPT_VERSION,
                schema_fingerprint=schema.fingerprint(),
                payload=payload(p),
            )
            return validate_raw_extraction(
                raw,
                schema=schema,
                etim_class=etim_class,
                demo_config=demo_config,
                target=target,
            )

        assert validated(forward) == validated(backward)


class TestConditions:
    def test_conditions_are_preserved(self, go):
        result, _ = go(features={CURRENT: current_proposal()})
        candidate = result.validated.candidate(CURRENT)
        bound = {c.kind.value: c.value for c in candidate.conditions.conditions}
        assert bound["UTILIZATION_CATEGORY"] == "AC-3"
        assert bound["VOLTAGE"] == "440 V"

    def test_completeness_is_derived_not_taken_from_the_model(self, go):
        """Both qualifiers bound -> COMPLETE, decided by resolve_conditions."""
        result, _ = go(features={CURRENT: current_proposal()})
        assert result.validated.candidate(CURRENT).conditions.completeness is (
            ConditionCompleteness.COMPLETE
        )

    def test_missing_qualifier_yields_partial(self, go):
        proposal = current_proposal(conditions=[{"kind": "UTILIZATION_CATEGORY", "value": "AC-3"}])
        result, _ = go(features={CURRENT: proposal})
        conditions = result.validated.candidate(CURRENT).conditions
        assert conditions.completeness is ConditionCompleteness.PARTIAL
        assert "VOLTAGE" in [k.value for k in conditions.missing_kinds]

    def test_model_cannot_supply_completeness(self, go):
        """The schema has no such field, so offering one is a malformed proposal."""
        result, _ = go(features={CURRENT: current_proposal(completeness="COMPLETE")})
        assert result.validated.candidate_count == 0
        assert result.validated.rejected[0].code is RejectionCode.MALFORMED_PROPOSAL

    def test_ratings_under_different_operating_points_stay_distinct(self, go):
        ac1 = current_proposal(
            number=32,
            raw_text="32 A at <= 440 V AC AC-1",
            conditions=[
                {"kind": "UTILIZATION_CATEGORY", "value": "AC-1"},
                {"kind": "VOLTAGE", "value": "440 V"},
            ],
        )
        result, _ = go(
            features={CURRENT: current_proposal(), "EF001393": ac1},
            feature_ids=(CURRENT, "EF001393"),
        )
        by_id = {c.etim_feature_id: c for c in result.validated.candidates}
        assert by_id[CURRENT].value.number == 18.0
        assert by_id["EF001393"].value.number == 32.0
        assert by_id[CURRENT].conditions.get(ConditionKind.UTILIZATION_CATEGORY).value == "AC-3"
        assert by_id["EF001393"].conditions.get(ConditionKind.UTILIZATION_CATEGORY).value == "AC-1"


class TestNotAnAcceptedAttribute:
    def test_candidate_is_not_a_product_attribute(self, go):
        from skutruth.contracts import ProductAttribute

        result, _ = go(features={CURRENT: current_proposal()})
        assert not isinstance(result.validated.candidates[0], ProductAttribute)

    def test_no_support_grade_or_confidence_field_exists(self):
        """A model may not assert how well supported its own proposal is."""
        from skutruth.extraction import models as extraction_models

        forbidden = (
            "confidence",
            "probability",
            "support_grade",
            "grade",
            "verification",
            "accepted",
            "proves_family_scope",
        )
        checked = 0
        for name in dir(extraction_models):
            obj = getattr(extraction_models, name)
            fields = getattr(obj, "model_fields", None)
            # Only models defined here; imported contracts have their own rules.
            if not fields or getattr(obj, "__module__", "") != extraction_models.__name__:
                continue
            checked += 1
            for field_name in fields:
                assert not any(f in field_name.lower() for f in forbidden), f"{name}.{field_name}"
        assert checked >= 5, "expected to scan the extraction models"

    def test_candidate_carries_no_verification_status(self, go):
        result, _ = go(features={CURRENT: current_proposal()})
        dumped = result.validated.candidates[0].model_dump()
        assert "EXACT_SPAN" not in str(dumped)
        assert set(dumped) == set(ExtractionCandidate.model_fields)

    def test_source_fragment_is_a_claim_not_a_verified_span(self, go):
        """Nothing has looked for this text yet; it is only what the model said."""
        result, _ = go(features={CURRENT: current_proposal(raw_text="text not in the pdf")})
        assert result.validated.candidate(CURRENT).source_fragment == "text not in the pdf"


class TestRecordReplay:
    def test_live_invokes_the_provider_once_and_writes_a_cassette(self, go, tmp_path):
        result, provider = go(features={CURRENT: current_proposal()})
        assert provider.calls == 1
        assert result.mode is RunMode.LIVE
        assert result.replayed is False
        assert result.cassette_key

    def test_replay_never_invokes_the_provider(
        self, tmp_path, etim_class, demo_config, artifact, artifact_bytes
    ):
        store = CassetteStore(tmp_path, writable=True)
        provider = FakeProvider(payload({CURRENT: current_proposal()}))
        kw = dict(
            identity=exact_identity(),
            artifact=artifact,
            artifact_bytes=artifact_bytes,
            etim_class=etim_class,
            provider=provider,
            store=store,
            config=VertexConfig(project="p"),
            demo_config=demo_config,
            feature_ids=(CURRENT,),
        )
        live = extract_product_attributes(mode=RunMode.LIVE, **kw)
        assert provider.calls == 1
        replayed = extract_product_attributes(mode=RunMode.REPLAY, **kw)
        assert provider.calls == 1, "REPLAY must not reach the provider"
        assert replayed.replayed is True
        assert replayed.validated == live.validated

    def test_replay_miss_fails_closed(
        self, tmp_path, etim_class, demo_config, artifact, artifact_bytes
    ):
        provider = FakeProvider(payload({CURRENT: current_proposal()}))
        with pytest.raises(ReplayMissError):
            extract_product_attributes(
                identity=exact_identity(),
                artifact=artifact,
                artifact_bytes=artifact_bytes,
                etim_class=etim_class,
                provider=provider,
                store=CassetteStore(tmp_path, writable=True),
                config=VertexConfig(project="p"),
                mode=RunMode.REPLAY,
                demo_config=demo_config,
                feature_ids=(CURRENT,),
            )
        assert provider.calls == 0

    def test_provider_receives_the_document_bytes_and_schema(self, go, artifact_bytes):
        _, provider = go(features={CURRENT: current_proposal()})
        call = provider.last_call
        assert call.document_bytes == artifact_bytes
        assert call.document_media_type == "application/pdf"
        assert call.response_schema["properties"]["features"]["properties"]
        assert "untrusted" in call.system_instruction.lower()

    def test_prompt_binds_the_exact_target(self, go):
        _, provider = go(features={CURRENT: current_proposal()})
        prompt = provider.last_call.user_prompt
        assert EXACT_MPN in prompt
        assert CLASS_ID in prompt
        assert "null" in prompt


class TestArtifactBinding:
    def test_mismatched_bytes_are_refused(self, go):
        from skutruth.extraction import ArtifactMismatchError

        with pytest.raises(ArtifactMismatchError):
            go(features={}, artifact_bytes=b"%PDF-1.4 different bytes")


class TestConfig:
    def test_project_is_required(self, monkeypatch):
        monkeypatch.delenv("SKUTRUTH_GCP_PROJECT", raising=False)
        with pytest.raises(RuntimeError, match="SKUTRUTH_GCP_PROJECT"):
            VertexConfig.from_env()

    def test_model_is_configurable(self, monkeypatch):
        monkeypatch.setenv("SKUTRUTH_GCP_PROJECT", "proj")
        monkeypatch.setenv("SKUTRUTH_VERTEX_MODEL", "some-other-model")
        assert VertexConfig.from_env().model == "some-other-model"

    def test_defaults_apply_when_optional_vars_absent(self, monkeypatch):
        from skutruth.extraction import DEFAULT_LOCATION, DEFAULT_MODEL

        monkeypatch.setenv("SKUTRUTH_GCP_PROJECT", "proj")
        monkeypatch.delenv("SKUTRUTH_VERTEX_MODEL", raising=False)
        monkeypatch.delenv("SKUTRUTH_VERTEX_LOCATION", raising=False)
        config = VertexConfig.from_env()
        assert (config.model, config.location) == (DEFAULT_MODEL, DEFAULT_LOCATION)


class TestNoSearchGrounding:
    def test_no_tools_are_enabled(self, etim_class, demo_config, artifact):
        """Grounding and URL context are separate later capabilities."""
        from skutruth.extraction.models import ExtractionTarget

        schema = build_extraction_schema(etim_class, demo_config)
        request = build_interaction_request(
            ExtractionTarget(
                brand=BRAND,
                exact_mpn=EXACT_MPN,
                etim_class_id=CLASS_ID,
                artifact_sha256=artifact.sha256,
                page_count=artifact.page_count,
            ),
            schema,
            VertexConfig(project="p"),
        )
        assert request.tools == ()
        assert request.tool_config is None


class TestBusinessLogicHasNoSdkImport:
    def test_only_the_vertex_module_imports_google_genai(self):
        from pathlib import Path

        import skutruth.extraction as pkg

        for path in Path(pkg.__file__).parent.glob("*.py"):
            if path.name == "vertex.py":
                continue
            # Import statements only; prose about the SDK is not a dependency on it.
            imports = [
                line.strip()
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip().startswith(("import ", "from "))
            ]
            assert not [i for i in imports if "google" in i], f"{path.name}: {imports}"


class TestModelsRefuseBadShapes:
    def test_target_requires_a_real_sha(self):
        from skutruth.extraction.models import ExtractionTarget

        with pytest.raises(ValidationError):
            ExtractionTarget(
                brand=BRAND,
                exact_mpn=EXACT_MPN,
                etim_class_id=CLASS_ID,
                artifact_sha256="not-a-hash",
                page_count=1,
            )

    def test_candidate_requires_a_source_fragment(self, etim_class):
        from skutruth.contracts import ConditionSet, NumericValue

        with pytest.raises(ValidationError):
            ExtractionCandidate(
                etim_feature_id=CURRENT,
                feature_name="x",
                value=NumericValue(number=1.0, unit="A"),
                conditions=ConditionSet(),
                source_fragment="",
                page_number=1,
            )
