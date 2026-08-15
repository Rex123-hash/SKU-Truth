"""Redaction. Leaking a credential is the failure this module exists to prevent."""

from __future__ import annotations

import pytest
from skutruth.replay import PLACEHOLDER, is_sensitive_key, redact, redact_text

SECRET = "sk-live-DO-NOT-LEAK-0123456789"


class TestKeyMatching:
    @pytest.mark.parametrize(
        "key",
        [
            "authorization",
            "Authorization",
            "AUTHORIZATION",
            "api_key",
            "api-key",
            "apiKey",
            "x-api-key",
            "X-API-Key",
            "access_token",
            "refresh_token",
            "token",
            "secret",
            "client_secret",
            "password",
            "cookie",
            "set-cookie",
            "Set-Cookie",
            "private_key",
            "openai_api_key",
            "GOOGLE_API_KEY",
        ],
    )
    def test_sensitive_keys_are_recognised(self, key):
        assert is_sensitive_key(key)

    @pytest.mark.parametrize(
        "key",
        [
            "prompt",
            "model",
            "input_tokens",
            "output_tokens",
            "total_tokens",
            "promptTokenCount",
            "cachedContentTokenCount",
            "tokenizer",
            "temperature",
            "artifact_hashes",
        ],
    )
    def test_ordinary_keys_survive(self, key):
        """A naive 'contains token' rule would destroy exactly this usage data."""
        assert not is_sensitive_key(key)


class TestRedaction:
    def test_a_top_level_credential_is_replaced(self):
        assert redact({"Authorization": f"Bearer {SECRET}"}) == {"Authorization": PLACEHOLDER}

    def test_nested_credentials_are_replaced(self):
        out = redact({"request": {"headers": {"authorization": f"Bearer {SECRET}"}}})
        assert out["request"]["headers"]["authorization"] == PLACEHOLDER

    def test_credentials_inside_lists_are_replaced(self):
        out = redact({"calls": [{"api_key": SECRET}, {"api_key": SECRET}]})
        assert [c["api_key"] for c in out["calls"]] == [PLACEHOLDER, PLACEHOLDER]

    def test_deeply_nested_list_and_dict_mixtures(self):
        out = redact({"a": [{"b": [{"x-api-key": SECRET}]}]})
        assert out["a"][0]["b"][0]["x-api-key"] == PLACEHOLDER

    def test_an_entire_object_under_a_sensitive_key_is_replaced(self):
        """A credential must not survive by hiding inside a nested object."""
        out = redact({"credentials": {"user": "u", "password": SECRET}})
        assert out["credentials"] == PLACEHOLDER

    def test_ordinary_values_are_preserved(self):
        payload = {"prompt": "extract", "temperature": 0, "usage": {"input_tokens": 42}}
        assert redact(payload) == payload

    def test_the_input_object_is_not_mutated(self):
        original = {"authorization": f"Bearer {SECRET}", "nested": {"token": SECRET}}
        snapshot = {"authorization": f"Bearer {SECRET}", "nested": {"token": SECRET}}
        redact(original)
        assert original == snapshot

    def test_the_secret_string_appears_nowhere_in_the_output(self):
        out = redact(
            {
                "authorization": f"Bearer {SECRET}",
                "nested": [{"access_token": SECRET}],
                "url": f"https://api.example/v1?api_key={SECRET}&model=x",
            }
        )
        assert SECRET not in str(out)

    def test_non_string_keys_do_not_break_traversal(self):
        assert redact({1: "one", "token": SECRET})[1] == "one"


class TestUrlAndTextRedaction:
    def test_query_credentials_are_scrubbed(self):
        out = redact_text(f"https://api.example/v1?api_key={SECRET}&model=fake")
        assert SECRET not in out
        assert "model=fake" in out

    def test_an_error_message_echoing_the_url_is_scrubbed(self):
        """Providers routinely echo the request URL back in error text."""
        out = redact_text(f"403 calling https://api.example/v1?access_token={SECRET}")
        assert SECRET not in out
        assert "403 calling" in out

    def test_ordinary_text_is_untouched(self):
        assert redact_text("no credentials here") == "no credentials here"

    def test_string_values_are_scrubbed_during_recursion(self):
        out = redact({"url": f"https://x/y?token={SECRET}"})
        assert SECRET not in out["url"]
