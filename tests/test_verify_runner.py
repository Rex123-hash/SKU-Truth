"""The reproducible verification runner.

Everything here is synthetic. The real Schneider run this script exists to reproduce
depends on a copyrighted document that is not in the repository and must never be, so
these tests build their own artifact, their own recording, and their own claims.

Two properties matter more than the happy path: the runner never touches a network, and
when a local input is missing it says so instead of improvising.
"""

from __future__ import annotations

import socket
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest_pdf import build_pdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from skutruth.contracts import (  # noqa: E402
    Condition,
    ConditionKind,
    ConditionSet,
    IdentityScope,
    NumericValue,
    RunMode,
)
from skutruth.etim import build_extraction_schema, load_demo_class, load_etim  # noqa: E402
from skutruth.extraction.models import (  # noqa: E402
    ExtractionCandidate,
    ExtractionRun,
    ExtractionTarget,
    RawModelExtraction,
    ValidatedExtraction,
)
from skutruth.ingest import ingest_pdf_bytes  # noqa: E402
from skutruth.ingest.models import SourceMetadata  # noqa: E402
from skutruth.ingest.storage import ArtifactStore  # noqa: E402
from skutruth.replay.models import Cassette, InteractionRequest  # noqa: E402
from skutruth.replay.store import CassetteStore  # noqa: E402
from verify_extraction_run import (  # noqa: E402
    RunnerError,
    main,
    reconstruct_from_cassette,
    verify_run,
)

MPN = "BASE100X1"
BRAND = "TestCo"
CLASS_ID = "EC000066"
RATING_LINE = "18 A (at <60 °C) at <= 440 V AC AC-3 for power circuit"
PAGES = ["TESTCO CONTACTOR DATA", RATING_LINE]


@pytest.fixture
def artifacts(tmp_path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "artifacts", writable=True)


@pytest.fixture
def artifact(artifacts):
    pdf = build_pdf(PAGES)
    record = ingest_pdf_bytes(
        pdf,
        source=SourceMetadata(
            publisher=BRAND,
            identity_scope=IdentityScope.EXACT_SKU,
            covers_mpn=MPN,
            final_artifact_url="https://example.invalid/datasheet.pdf",
        ),
    )
    artifacts.save(record, pdf)
    return record


def build_run(artifact, *, page: int = 2, fragment: str = "18 A") -> ExtractionRun:
    """A run with one candidate that the synthetic artifact genuinely supports."""
    target = ExtractionTarget(
        brand=BRAND,
        exact_mpn=MPN,
        etim_class_id=CLASS_ID,
        artifact_sha256=artifact.sha256,
        page_count=artifact.page_count,
    )
    candidate = ExtractionCandidate(
        etim_feature_id="EF001392",
        feature_name="Rated operation current Ie at AC-3, 400 V",
        value=NumericValue(number=18.0, unit="A", raw="18 A"),
        conditions=ConditionSet(
            conditions=(Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3"),)
        ),
        source_fragment=fragment,
        page_number=page,
    )
    return ExtractionRun(
        target=target,
        raw=RawModelExtraction(
            model="fake-model-v1",
            prompt_version="product-extraction@v1",
            schema_fingerprint="a" * 64,
            payload={"features": {"EF001392": {"number": 18.0}}},
        ),
        validated=ValidatedExtraction(
            candidates=(candidate,), requested_feature_ids=("EF001392",)
        ),
        mode=RunMode.REPLAY,
        replayed=True,
        cassette_key="b" * 64,
    )


def write_cassette(root: Path, artifact, payload: dict, *, schema_version: str | None = None):
    """A recording the runner can re-derive, keyed exactly as the real store keys them."""
    schema = build_extraction_schema(
        load_etim().classes[CLASS_ID], load_demo_class(CLASS_ID)
    )
    request = InteractionRequest(
        provider="vertex-ai",
        model="fake-model-v1",
        endpoint="generateContent",
        payload={
            "location": "us-central1",
            "brand": BRAND,
            "exact_mpn": MPN,
            "etim_class_id": CLASS_ID,
            "page_count": artifact.page_count,
            "media_type": "application/pdf",
        },
        prompt_version="product-extraction@v1",
        schema_version=schema_version or schema.fingerprint(),
        artifact_hashes=(artifact.sha256,),
    )
    cassette = Cassette(
        key=request.cassette_key(),
        request=request,
        provider=request.provider,
        model=request.model,
        outcome="success",
        response=payload,
        captured_at=datetime.now(UTC),
        latency_seconds=0.5,
    )
    return CassetteStore(root, writable=True).save(cassette)


class TestSerialisedRun:
    def test_a_supported_claim_verifies(self, artifacts, artifact):
        report = verify_run(build_run(artifact), artifacts=artifacts)
        assert report["candidates"] == 1
        assert report["verified"] == 1
        assert report["unverified"] == 0
        assert report["failure_counts"] == {}

    def test_an_unsupported_claim_is_counted_with_its_reason(self, artifacts, artifact):
        run = build_run(artifact, fragment="not in the document")
        report = verify_run(run, artifacts=artifacts)
        assert report["verified"] == 0
        assert report["failure_counts"] == {"SOURCE_FRAGMENT_NOT_FOUND": 1}

    def test_main_round_trips_a_run_file(self, tmp_path, artifacts, artifact, capsys):
        run_file = tmp_path / "run.json"
        run_file.write_text(build_run(artifact).model_dump_json(), encoding="utf-8")
        code = main(["--run", str(run_file), "--artifacts", str(artifacts.root), "--json"])
        assert code == 0
        import json

        assert json.loads(capsys.readouterr().out)["verified"] == 1


class TestCassetteReconstruction:
    def test_a_recording_is_re_derived_and_verified(self, tmp_path, artifacts, artifact):
        payload = {
            "etim_class_id": CLASS_ID,
            "features": {
                "EF001392": {
                    "number": 18.0,
                    "unit": "A",
                    "raw_text": "18 A",
                    "page": 2,
                    "conditions": [
                        {"kind": "UTILIZATION_CATEGORY", "value": "AC-3"},
                        {"kind": "VOLTAGE", "value": "400 V"},
                    ],
                }
            },
        }
        path = write_cassette(tmp_path / "cassettes", artifact, payload)
        run = reconstruct_from_cassette(path)
        assert run.target.exact_mpn == MPN
        assert run.replayed is True
        # 400 V is not on the line; the rating is stated at <= 440 V. The point of
        # re-derivation is that this stays visible rather than being asserted away.
        report = verify_run(run, artifacts=artifacts)
        assert report["candidates"] == 1
        assert report["verified"] + report["unverified"] == 1

    def test_a_schema_that_cannot_be_rebuilt_is_refused(self, tmp_path, artifacts, artifact):
        """A run cannot be re-derived under a schema it was not produced with."""
        path = write_cassette(
            tmp_path / "cassettes", artifact, {"features": {}}, schema_version="c" * 64
        )
        with pytest.raises(RunnerError, match="does not match the recording"):
            reconstruct_from_cassette(path)

    def test_a_missing_cassette_is_reported(self, tmp_path):
        with pytest.raises(RunnerError, match="no cassette at"):
            reconstruct_from_cassette(tmp_path / "absent.json")


class TestMissingLocalInputs:
    def test_a_missing_artifact_names_what_is_needed(self, tmp_path, artifacts, artifact):
        """Q. The fresh-clone case: the document is deliberately not committed."""
        empty = ArtifactStore(tmp_path / "empty", writable=False)
        with pytest.raises(RunnerError, match=artifact.sha256):
            verify_run(build_run(artifact), artifacts=empty)

    def test_main_exits_non_zero_and_explains(self, tmp_path, artifacts, artifact, capsys):
        run_file = tmp_path / "run.json"
        run_file.write_text(build_run(artifact).model_dump_json(), encoding="utf-8")
        code = main(["--run", str(run_file), "--artifacts", str(tmp_path / "empty")])
        assert code == 2
        assert "cannot verify" in capsys.readouterr().err

    def test_a_non_extraction_cassette_is_rejected(self, tmp_path, artifact):
        request = InteractionRequest(
            provider="test", model="m", endpoint="e", payload={"unrelated": True}
        )
        cassette = Cassette(
            key=request.cassette_key(),
            request=request,
            provider="test",
            model="m",
            outcome="success",
            response={},
            captured_at=datetime.now(UTC),
            latency_seconds=0.0,
        )
        path = CassetteStore(tmp_path / "cassettes", writable=True).save(cassette)
        with pytest.raises(RunnerError, match="not an extraction cassette"):
            reconstruct_from_cassette(path)


class TestNoProviderCall:
    def test_the_runner_opens_no_socket(self, monkeypatch, tmp_path, artifacts, artifact, capsys):
        """R. Replay is a recording, so verifying one must never reach a provider."""

        def refuse(*args, **kwargs):
            raise AssertionError("the verification runner attempted a network connection")

        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)

        payload = {
            "etim_class_id": CLASS_ID,
            "features": {
                "EF001392": {"number": 18.0, "unit": "A", "raw_text": "18 A", "page": 2}
            },
        }
        path = write_cassette(tmp_path / "cassettes", artifact, payload)
        assert main(["--cassette", str(path), "--artifacts", str(artifacts.root)]) == 0
        assert "claims verified mechanically" in capsys.readouterr().out

    def test_the_runner_imports_no_provider_module(self):
        """The Vertex client is never even loaded, so no credential can be read.

        Checked against the parsed import graph rather than the file's text: prose about
        providers is fine, and a substring scan would forbid documenting the property it
        is trying to enforce.
        """
        import ast

        source = (
            Path(__file__).resolve().parents[1] / "scripts" / "verify_extraction_run.py"
        ).read_text(encoding="utf-8")

        imported: set[str] = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Import):
                imported.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)

        assert not [m for m in imported if m.split(".")[0] in {"google", "vertexai"}]
        assert "skutruth.extraction.vertex" not in imported
        assert "skutruth.extraction.provider" not in imported
