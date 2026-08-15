"""Cassette key derivation: what changes it, and what must not."""

from __future__ import annotations

import pytest
from skutruth.replay import KEY_VERSION, InteractionRequest, canonical_json, is_valid_key


def request(**overrides) -> InteractionRequest:
    kwargs = {
        "provider": "test",
        "model": "fake-model-v1",
        "endpoint": "generate",
        "payload": {"prompt": "extract", "temperature": 0},
        "prompt_version": "extract@v1",
        "schema_version": "etim-extraction@v1",
        "tools": ("google_search",),
        "artifact_hashes": ("a" * 64,),
    }
    kwargs.update(overrides)
    return InteractionRequest(**kwargs)


class TestStability:
    def test_the_same_logical_request_yields_the_same_key(self):
        assert request().cassette_key() == request().cassette_key()

    def test_the_key_is_a_well_formed_digest(self):
        assert is_valid_key(request().cassette_key())

    def test_payload_key_ordering_does_not_change_the_key(self):
        a = request(payload={"prompt": "extract", "temperature": 0})
        b = request(payload={"temperature": 0, "prompt": "extract"})
        assert a.cassette_key() == b.cassette_key()

    def test_nested_payload_ordering_does_not_change_the_key(self):
        a = request(payload={"cfg": {"a": 1, "b": [{"x": 1, "y": 2}]}})
        b = request(payload={"cfg": {"b": [{"y": 2, "x": 1}], "a": 1}})
        assert a.cassette_key() == b.cassette_key()

    def test_tool_ordering_does_not_change_the_key(self):
        """Enabling the same two tools is one configuration, however it is listed."""
        a = request(tools=("google_search", "url_context"))
        b = request(tools=("url_context", "google_search"))
        assert a.cassette_key() == b.cassette_key()

    def test_artifact_hash_ordering_does_not_change_the_key(self):
        a = request(artifact_hashes=("a" * 64, "b" * 64))
        b = request(artifact_hashes=("b" * 64, "a" * 64))
        assert a.cassette_key() == b.cassette_key()

    def test_canonical_json_is_byte_stable(self):
        assert canonical_json({"b": 1, "a": 2}) == '{"a":2,"b":1}'


class TestSeparation:
    @pytest.mark.parametrize(
        "change",
        [
            {"provider": "other"},
            {"model": "fake-model-v2"},
            {"endpoint": "countTokens"},
            {"payload": {"prompt": "extract", "temperature": 1}},
            {"prompt_version": "extract@v2"},
            {"schema_version": "etim-extraction@v2"},
            {"stage_version": "identify@v1"},
            {"tools": ("google_search", "url_context")},
            {"tool_config": {"max_urls": 5}},
            {"artifact_hashes": ("b" * 64,)},
        ],
        ids=lambda c: next(iter(c)),
    )
    def test_a_meaningful_change_changes_the_key(self, change):
        assert request().cassette_key() != request(**change).cassette_key()

    def test_dropping_a_tool_changes_the_key(self):
        assert request().cassette_key() != request(tools=()).cassette_key()

    def test_dropping_an_artifact_changes_the_key(self):
        assert request().cassette_key() != request(artifact_hashes=()).cassette_key()


class TestVolatileFieldsAreExcluded:
    def test_the_descriptor_has_no_timestamp_or_run_id_field(self):
        """A timestamp in the key would give every interaction a fresh key."""
        fields = set(InteractionRequest.model_fields)
        assert not fields & {"timestamp", "captured_at", "run_id", "trace_id", "attempt"}

    def test_key_material_lists_exactly_the_intended_inputs(self):
        assert set(request().key_material()) == {
            "key_version",
            "provider",
            "model",
            "endpoint",
            "payload",
            "prompt_version",
            "schema_version",
            "stage_version",
            "tools",
            "tool_config",
            "artifact_hashes",
        }

    def test_the_key_version_participates_in_the_digest(self):
        assert request().key_material()["key_version"] == KEY_VERSION


class TestCredentialsDoNotAffectTheKey:
    def test_a_rotated_credential_leaves_the_key_unchanged(self):
        """Redaction happens before key derivation, so rotation is not a cache bust."""
        a = request(payload={"prompt": "x", "api_key": "secret-one"})
        b = request(payload={"prompt": "x", "api_key": "secret-two"})
        assert a.cassette_key() == b.cassette_key()

    def test_no_secret_value_reaches_the_key_material(self):
        material = request(payload={"prompt": "x", "authorization": "Bearer abc"}).key_material()
        assert "abc" not in canonical_json(material)


class TestPayloadValidation:
    def test_a_non_serializable_payload_is_rejected(self):
        with pytest.raises(ValueError, match="JSON serializable"):
            request(payload={"fn": object()})
