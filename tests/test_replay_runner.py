"""LIVE recording, REPLAY, and the guarantee that replay never reaches a provider.

Providers here are obviously fake — `provider="test"`, `model="fake-model-v1"`. No
fixture in this file pretends to be a real Vertex or Gemini response.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from skutruth.contracts import RunMode
from skutruth.replay import (
    CASSETTE_VERSION,
    KEY_VERSION,
    Cassette,
    CassetteStore,
    InteractionRequest,
    InvalidCassetteError,
    LiveResponse,
    ModeNotRequestableError,
    RecordedProviderError,
    ReplayMissError,
    Usage,
    fixture_store,
    is_mode_requestable,
    is_public_demo_safe,
    require_public_demo_safe,
    run_interaction,
    runtime_store,
)

SECRET = "sk-live-DO-NOT-LEAK-0123456789"


@pytest.fixture
def store(tmp_path) -> CassetteStore:
    return CassetteStore(tmp_path / "runtime")


def request(**overrides) -> InteractionRequest:
    kwargs = {
        "provider": "test",
        "model": "fake-model-v1",
        "endpoint": "generate",
        "payload": {"prompt": "extract EF001392"},
        "prompt_version": "extract@v1",
        "schema_version": "etim-extraction@v1",
        "artifact_hashes": ("a" * 64,),
    }
    kwargs.update(overrides)
    return InteractionRequest(**kwargs)


def should_never_run():
    raise AssertionError("network/provider call attempted during replay")


class TestLiveRecording:
    def test_the_live_callable_runs_exactly_once(self, store):
        calls = []

        def provider():
            calls.append(1)
            return {"value": 18, "unit": "A"}

        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=provider
        )
        assert len(calls) == 1

    def test_a_cassette_is_written(self, store):
        req = request()
        result = run_interaction(
            mode=RunMode.LIVE, request=req, store=store, live_callable=lambda: {"ok": True}
        )
        assert store.exists(req.cassette_key())
        assert result.key == req.cassette_key()
        assert result.replayed is False
        assert result.mode is RunMode.LIVE

    def test_the_raw_response_is_preserved_unparsed(self, store):
        """Parsing happens after retrieval, so parser changes stay testable."""
        raw = {"candidates": [{"content": {"parts": [{"text": "18 A"}]}}], "extra": [1, 2]}
        result = run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: raw
        )
        assert result.response == raw

    def test_usage_metadata_is_preserved(self, store):
        usage = Usage(input_tokens=1200, output_tokens=64, cached_input_tokens=800)
        result = run_interaction(
            mode=RunMode.LIVE,
            request=request(),
            store=store,
            live_callable=lambda: LiveResponse(response={"ok": True}, usage=usage),
        )
        assert result.usage.input_tokens == 1200
        assert result.usage.cached_input_tokens == 800

    def test_usage_is_never_derived(self, store):
        """input + output is not asserted to be the total; the provider decides that."""
        usage = Usage(input_tokens=10, output_tokens=5)
        result = run_interaction(
            mode=RunMode.LIVE,
            request=request(),
            store=store,
            live_callable=lambda: LiveResponse(response={}, usage=usage),
        )
        assert result.usage.total_tokens is None
        assert result.usage.provider_reported_cost is None

    def test_captured_at_is_timezone_aware_utc(self, store):
        result = run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        assert result.captured_at.tzinfo is not None
        assert result.captured_at.utcoffset().total_seconds() == 0

    def test_latency_is_recorded_and_nonnegative(self, store):
        result = run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        assert result.latency_seconds >= 0.0

    def test_live_requires_a_callable(self, store):
        with pytest.raises(ValueError, match="requires a live_callable"):
            run_interaction(mode=RunMode.LIVE, request=request(), store=store)


class TestReplay:
    def _record(self, store, response=None, req=None):
        return run_interaction(
            mode=RunMode.LIVE,
            request=req or request(),
            store=store,
            live_callable=lambda: response if response is not None else {"value": 18},
        )

    def test_replay_never_invokes_the_live_callable(self, store):
        self._record(store)
        result = run_interaction(
            mode=RunMode.REPLAY,
            request=request(),
            store=store,
            live_callable=should_never_run,
        )
        assert result.replayed is True

    def test_the_replayed_response_equals_the_captured_response(self, store):
        raw = {"candidates": [{"text": "18 A"}], "n": 3}
        self._record(store, response=raw)
        result = run_interaction(mode=RunMode.REPLAY, request=request(), store=store)
        assert result.response == raw

    def test_the_original_capture_time_is_preserved(self, store):
        """A replay reports when it was recorded, not now."""
        recorded = self._record(store)
        replayed = run_interaction(mode=RunMode.REPLAY, request=request(), store=store)
        assert replayed.captured_at == recorded.captured_at

    def test_usage_survives_the_round_trip(self, store):
        run_interaction(
            mode=RunMode.LIVE,
            request=request(),
            store=store,
            live_callable=lambda: LiveResponse(
                response={}, usage=Usage(input_tokens=7, output_tokens=2)
            ),
        )
        result = run_interaction(mode=RunMode.REPLAY, request=request(), store=store)
        assert (result.usage.input_tokens, result.usage.output_tokens) == (7, 2)

    def test_a_different_request_does_not_replay_the_wrong_cassette(self, store):
        self._record(store)
        other = request(prompt_version="extract@v2")
        with pytest.raises(ReplayMissError):
            run_interaction(
                mode=RunMode.REPLAY,
                request=other,
                store=store,
                live_callable=should_never_run,
            )


class TestFailClosed:
    def test_a_missing_cassette_raises_replay_miss(self, store):
        with pytest.raises(ReplayMissError) as exc:
            run_interaction(
                mode=RunMode.REPLAY,
                request=request(),
                store=store,
                live_callable=should_never_run,
            )
        assert exc.value.key == request().cassette_key()
        assert exc.value.provider == "test"

    def test_the_miss_message_names_what_is_missing_but_no_secret(self, store):
        req = request(payload={"prompt": "x", "api_key": SECRET})
        with pytest.raises(ReplayMissError) as exc:
            run_interaction(mode=RunMode.REPLAY, request=req, store=store)
        text = str(exc.value)
        assert "fake-model-v1" in text and "extract@v1" in text
        assert SECRET not in text

    def test_there_is_no_live_fallback_on_a_miss(self, store):
        calls = []
        with pytest.raises(ReplayMissError):
            run_interaction(
                mode=RunMode.REPLAY,
                request=request(),
                store=store,
                live_callable=lambda: calls.append(1),
            )
        assert calls == []

    def test_unreadable_json_raises_invalid_cassette(self, store):
        key = request().cassette_key()
        store.root.mkdir(parents=True, exist_ok=True)
        store.path_for(key).write_text("{not json", encoding="utf-8")
        with pytest.raises(InvalidCassetteError, match="unreadable JSON"):
            run_interaction(
                mode=RunMode.REPLAY,
                request=request(),
                store=store,
                live_callable=should_never_run,
            )

    def test_an_unknown_format_version_raises_invalid_cassette(self, store):
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        path = store.path_for(request().cassette_key())
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["cassette_version"] = "cassette@v99"
        path.write_text(json.dumps(blob), encoding="utf-8")
        with pytest.raises(InvalidCassetteError, match="format version"):
            run_interaction(mode=RunMode.REPLAY, request=request(), store=store)

    def test_a_key_that_disagrees_with_its_filename_is_rejected(self, store):
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        path = store.path_for(request().cassette_key())
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["key"] = "f" * 64
        path.write_text(json.dumps(blob), encoding="utf-8")
        with pytest.raises(InvalidCassetteError):
            run_interaction(mode=RunMode.REPLAY, request=request(), store=store)

    def test_a_tampered_request_descriptor_is_rejected(self, store):
        """The stored key must be derivable from the stored descriptor."""
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        path = store.path_for(request().cassette_key())
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["request"]["model"] = "some-other-model"
        path.write_text(json.dumps(blob), encoding="utf-8")
        with pytest.raises(InvalidCassetteError):
            run_interaction(mode=RunMode.REPLAY, request=request(), store=store)

    def test_a_malformed_key_never_becomes_a_path(self, store):
        with pytest.raises(InvalidCassetteError, match="not a valid cassette key"):
            store.path_for("../../etc/passwd")


class TestMetadataAgreesWithTheRequest:
    """The request descriptor is authoritative; the top-level copies must not diverge."""

    def _record_then_tamper(self, store, **changes):
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        path = store.path_for(request().cassette_key())
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob.update(changes)
        path.write_text(json.dumps(blob), encoding="utf-8")
        return path

    def test_a_provider_that_disagrees_with_the_request_is_rejected(self, store):
        self._record_then_tamper(store, provider="other-provider")
        with pytest.raises(InvalidCassetteError, match="disagrees with its request descriptor"):
            run_interaction(
                mode=RunMode.REPLAY,
                request=request(),
                store=store,
                live_callable=should_never_run,
            )

    def test_a_model_that_disagrees_with_the_request_is_rejected(self, store):
        self._record_then_tamper(store, model="fake-model-v2")
        with pytest.raises(InvalidCassetteError, match="disagrees with its request descriptor"):
            run_interaction(
                mode=RunMode.REPLAY,
                request=request(),
                store=store,
                live_callable=should_never_run,
            )

    def test_matching_provider_and_model_load_normally(self, store):
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {"ok": 1}
        )
        cassette = store.load_for(request())
        assert cassette.provider == cassette.request.provider == "test"
        assert cassette.model == cassette.request.model == "fake-model-v1"

    def test_the_mismatch_is_reported_not_repaired(self, store):
        """Rewriting one field to match the other would invent a fact."""
        req = request()
        with pytest.raises(ValueError, match="disagrees with its request descriptor"):
            Cassette(
                key=req.cassette_key(),
                request=req,
                provider="other-provider",
                model=req.model,
                outcome="success",
                response={},
                captured_at=datetime.now(UTC),
                latency_seconds=0.0,
            )

    def test_a_recorded_cassette_always_agrees_with_its_request(self, store):
        result = run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        assert result.cassette.provider == result.cassette.request.provider
        assert result.cassette.model == result.cassette.request.model


class TestKeyVersionIntegrity:
    """`key_version` names the rule the key was derived under, so it must be true."""

    def test_an_unsupported_key_version_is_rejected_on_load(self, store):
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        path = store.path_for(request().cassette_key())
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["key_version"] = "record-replay-key@v99"
        path.write_text(json.dumps(blob), encoding="utf-8")
        with pytest.raises(InvalidCassetteError, match="key version"):
            run_interaction(
                mode=RunMode.REPLAY,
                request=request(),
                store=store,
                live_callable=should_never_run,
            )

    def test_an_unsupported_key_version_cannot_be_constructed(self):
        req = request()
        with pytest.raises(ValueError, match="does not name the rule"):
            Cassette(
                key=req.cassette_key(),
                key_version="record-replay-key@v99",
                request=req,
                provider=req.provider,
                model=req.model,
                outcome="success",
                response={},
                captured_at=datetime.now(UTC),
                latency_seconds=0.0,
            )

    def test_recorded_cassettes_carry_the_current_key_version(self, store):
        result = run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        assert result.cassette.key_version == KEY_VERSION

    def test_redaction_version_is_historical_and_not_re_validated(self, store):
        """Deliberate asymmetry: it records which rules scrubbed the file, not how to read it.

        Redaction runs at capture time and only ever gets stricter, so a recording made
        under older rules is still a truthful account containing no secret. Rejecting it
        would discard good history for no safety gain.
        """
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        path = store.path_for(request().cassette_key())
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["redaction_version"] = "redaction@v0"
        path.write_text(json.dumps(blob), encoding="utf-8")
        cassette = store.load_for(request())
        assert cassette.redaction_version == "redaction@v0"


class TestFailureRecording:
    def test_a_provider_failure_is_recorded_and_re_raised(self, store):
        def failing():
            raise TimeoutError("provider timed out")

        with pytest.raises(TimeoutError, match="provider timed out"):
            run_interaction(
                mode=RunMode.LIVE, request=request(), store=store, live_callable=failing
            )
        cassette = store.load_for(request())
        assert cassette.is_error
        assert cassette.error.error_type == "TimeoutError"

    def test_replaying_a_recorded_failure_never_calls_the_provider(self, store):
        def failing():
            raise RuntimeError("provider exploded")

        with pytest.raises(RuntimeError):
            run_interaction(
                mode=RunMode.LIVE, request=request(), store=store, live_callable=failing
            )
        with pytest.raises(RecordedProviderError, match="provider exploded"):
            run_interaction(
                mode=RunMode.REPLAY,
                request=request(),
                store=store,
                live_callable=should_never_run,
            )

    def test_a_secret_in_the_failure_message_is_scrubbed(self, store):
        def failing():
            raise RuntimeError(f"403 from https://api.example/v1?api_key={SECRET}")

        with pytest.raises(RuntimeError):
            run_interaction(
                mode=RunMode.LIVE, request=request(), store=store, live_callable=failing
            )
        assert SECRET not in store.path_for(request().cassette_key()).read_text(encoding="utf-8")

    def test_a_missing_callable_is_not_recorded_as_a_provider_failure(self, store):
        """Programmer errors before invocation are not the provider's failure."""
        with pytest.raises(ValueError):
            run_interaction(mode=RunMode.LIVE, request=request(), store=store)
        assert store.keys() == ()


class TestRunModes:
    def test_mixed_cannot_be_requested(self, store):
        with pytest.raises(ModeNotRequestableError, match="mixed"):
            run_interaction(
                mode=RunMode.MIXED,
                request=request(),
                store=store,
                live_callable=should_never_run,
            )

    def test_live_and_replay_are_requestable(self):
        assert is_mode_requestable(RunMode.LIVE)
        assert is_mode_requestable(RunMode.REPLAY)
        assert not is_mode_requestable(RunMode.MIXED)

    def test_only_replay_is_public_demo_safe(self):
        assert is_public_demo_safe(RunMode.REPLAY)
        assert not is_public_demo_safe(RunMode.LIVE)
        assert not is_public_demo_safe(RunMode.MIXED)

    def test_the_public_demo_guard_rejects_live_and_mixed(self):
        require_public_demo_safe(RunMode.REPLAY)
        for mode in (RunMode.LIVE, RunMode.MIXED):
            with pytest.raises(ModeNotRequestableError):
                require_public_demo_safe(mode)


class TestProvenanceAdapter:
    def test_a_replayed_result_reports_its_capture_date(self, store):
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        result = run_interaction(mode=RunMode.REPLAY, request=request(), store=store)
        prov = result.to_run_provenance(provider_surface="test:local")
        assert prov.mode is RunMode.REPLAY
        assert prov.captured_at == result.captured_at
        assert prov.banner().startswith("RECORDED REPLAY — captured")
        assert prov.is_public_demo_safe

    def test_a_live_result_carries_no_capture_date(self, store):
        result = run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        prov = result.to_run_provenance()
        assert prov.mode is RunMode.LIVE
        assert prov.captured_at is None
        assert prov.banner() == "LIVE RUN"

    def test_the_cassette_key_reaches_provenance(self, store):
        result = run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        assert result.to_run_provenance().cassette_id == result.key


class TestPersistenceSafety:
    def test_no_secret_reaches_the_cassette_file(self, store):
        req = request(payload={"prompt": "x", "authorization": f"Bearer {SECRET}"})
        run_interaction(
            mode=RunMode.LIVE,
            request=req,
            store=store,
            live_callable=lambda: LiveResponse(
                response={"echo": {"x-api-key": SECRET}},
                metadata={"set-cookie": SECRET},
            ),
        )
        text = store.path_for(req.cassette_key()).read_text(encoding="utf-8")
        assert SECRET not in text
        assert "[REDACTED]" in text

    def test_the_written_file_is_valid_json_with_the_expected_version(self, store):
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {"a": 1}
        )
        blob = json.loads(store.path_for(request().cassette_key()).read_text(encoding="utf-8"))
        assert blob["cassette_version"] == CASSETTE_VERSION
        assert blob["outcome"] == "success"

    def test_writing_leaves_no_temporary_files_behind(self, store):
        run_interaction(
            mode=RunMode.LIVE, request=request(), store=store, live_callable=lambda: {}
        )
        assert list(store.root.glob("*.tmp")) == []
        assert len(list(store.root.glob("*.json"))) == 1

    def test_a_rewrite_replaces_atomically(self, store):
        for i in range(3):
            run_interaction(
                mode=RunMode.LIVE,
                request=request(),
                store=store,
                live_callable=lambda i=i: {"attempt": i},
            )
        assert len(store.keys()) == 1
        assert store.load_for(request()).response == {"attempt": 2}

    def test_the_fixture_store_is_read_only(self):
        """A live run must not be able to write into curated fixtures."""
        assert fixture_store().writable is False
        assert runtime_store().writable is True

    def test_a_read_only_store_refuses_to_record(self, tmp_path):
        ro = CassetteStore(tmp_path / "fixtures", writable=False)
        with pytest.raises(InvalidCassetteError, match="read-only"):
            run_interaction(
                mode=RunMode.LIVE, request=request(), store=ro, live_callable=lambda: {}
            )

    def test_a_non_serializable_response_is_rejected_before_writing(self, store):
        with pytest.raises(ValueError, match="JSON serializable"):
            run_interaction(
                mode=RunMode.LIVE,
                request=request(),
                store=store,
                live_callable=lambda: {"fn": object()},
            )


class TestRepositoryHygiene:
    def test_the_runtime_cassette_directory_is_gitignored(self):
        """Recordings must not reach the repository without a human reviewing them."""
        from pathlib import Path

        from skutruth.replay import DEFAULT_RUNTIME_DIR

        repo_root = Path(__file__).resolve().parents[1]
        ignored = (repo_root / ".gitignore").read_text(encoding="utf-8")
        assert "data/replay/runtime/" in ignored
        assert DEFAULT_RUNTIME_DIR.name == "runtime"
        assert DEFAULT_RUNTIME_DIR.parent.name == "replay"

    def test_runtime_and_fixture_directories_are_distinct(self):
        from skutruth.replay import DEFAULT_FIXTURE_DIR, DEFAULT_RUNTIME_DIR

        assert DEFAULT_FIXTURE_DIR != DEFAULT_RUNTIME_DIR


class TestCassetteModel:
    def test_a_naive_timestamp_is_rejected(self):
        req = request()
        with pytest.raises(ValueError, match="timezone-aware"):
            Cassette(
                key=req.cassette_key(),
                request=req,
                provider="test",
                model="fake-model-v1",
                outcome="success",
                response={},
                captured_at=datetime(2026, 8, 15),  # noqa: DTZ001 - deliberately naive
                latency_seconds=0.1,
            )

    def test_an_error_outcome_requires_error_detail(self):
        req = request()
        with pytest.raises(ValueError, match="must record a RecordedError"):
            Cassette(
                key=req.cassette_key(),
                request=req,
                provider="test",
                model="fake-model-v1",
                outcome="error",
                captured_at=datetime.now(UTC),
                latency_seconds=0.1,
            )

    def test_a_key_that_does_not_derive_from_the_request_is_rejected(self):
        with pytest.raises(ValueError, match="does not match its request descriptor"):
            Cassette(
                key="0" * 64,
                request=request(),
                provider="test",
                model="fake-model-v1",
                outcome="success",
                response={},
                captured_at=datetime.now(UTC),
                latency_seconds=0.1,
            )
