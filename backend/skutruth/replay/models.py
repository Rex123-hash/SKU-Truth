"""Interaction descriptors, usage metadata, and the cassette itself."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .keys import KEY_VERSION, digest, is_valid_key
from .redaction import REDACTION_VERSION, redact

#: Bumped when the persisted cassette shape changes. A cassette written under a
#: different version is rejected rather than best-effort parsed.
CASSETTE_VERSION = "cassette@v1"


def _assert_json_serializable(value: Any, what: str) -> Any:
    try:
        json.dumps(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{what} must be JSON serializable: {exc}") from exc
    return value


class InteractionRequest(BaseModel):
    """A deterministic description of one external interaction.

    This is a *descriptor*, not the request body sent to the provider. The live
    callable owns the actual call, including its credentials; nothing here should
    ever hold one. Redaction is applied anyway, defensively, and applied *before*
    key derivation — so a rotated credential cannot invalidate a cassette, and a
    credential that slipped in cannot influence anything persisted.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    provider: str = Field(min_length=1, description="e.g. 'vertex-ai', 'test'")
    model: str = Field(min_length=1, description="Model or endpoint identifier")
    endpoint: str | None = Field(default=None, description="Operation, e.g. 'generateContent'")
    payload: dict = Field(
        default_factory=dict, description="Normalized request body. Must be JSON serializable."
    )

    prompt_version: str | None = Field(default=None, description="e.g. 'extract@v3'")
    schema_version: str | None = Field(default=None, description="e.g. 'etim-extraction@v1'")
    stage_version: str | None = Field(default=None, description="Pipeline stage version")

    tools: tuple[str, ...] = Field(
        default=(), description="Enabled provider tools, e.g. ('google_search',)"
    )
    tool_config: dict | None = Field(default=None, description="Tool settings affecting output")

    artifact_hashes: tuple[str, ...] = Field(
        default=(), description="SHA-256 of every document this call reads"
    )

    @model_validator(mode="after")
    def _payloads_are_serializable(self) -> InteractionRequest:
        _assert_json_serializable(self.payload, "payload")
        if self.tool_config is not None:
            _assert_json_serializable(self.tool_config, "tool_config")
        return self

    def key_material(self) -> dict:
        """Exactly what the key is derived from, and nothing else.

        Tools and artifact hashes are sorted: enabling search and URL context is the
        same configuration whichever order the caller listed them in. Payload key
        ordering is handled by canonical JSON.

        Deliberately absent: timestamps, run and trace ids, latency, retry counts,
        and credentials. None of them changes what the provider would return.
        """
        return {
            "key_version": KEY_VERSION,
            "provider": self.provider,
            "model": self.model,
            "endpoint": self.endpoint,
            "payload": redact(self.payload),
            "prompt_version": self.prompt_version,
            "schema_version": self.schema_version,
            "stage_version": self.stage_version,
            "tools": sorted(self.tools),
            "tool_config": redact(self.tool_config) if self.tool_config is not None else None,
            "artifact_hashes": sorted(self.artifact_hashes),
        }

    def cassette_key(self) -> str:
        return digest(self.key_material())

    def redacted(self) -> InteractionRequest:
        """A copy safe to persist. Same cassette key as the original."""
        return self.model_copy(
            update={
                "payload": redact(self.payload),
                "tool_config": redact(self.tool_config) if self.tool_config else self.tool_config,
            }
        )


class Usage(BaseModel):
    """Provider-neutral usage metadata.

    Every field is optional, and nothing is derived. If a provider reports input and
    output tokens but no total, the total stays `None` — summing them would be an
    assumption about whether the provider counts anything else, and a cassette must
    not claim more than the provider actually returned. Cost is likewise recorded
    only when the provider reports it; no pricing table lives here.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    cached_input_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    provider_reported_cost: float | None = Field(default=None, ge=0.0)
    currency: str | None = None

    @property
    def is_empty(self) -> bool:
        return all(v is None for v in self.model_dump().values())


class RecordedError(BaseModel):
    """A provider failure, captured so it can be replayed deterministically."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    error_type: str = Field(min_length=1, description="Exception class name")
    message: str = Field(default="", description="Redacted exception message")
    status_code: int | None = None
    retryable: bool | None = None


class Cassette(BaseModel):
    """One recorded interaction, as it actually happened."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cassette_version: str = CASSETTE_VERSION

    #: Identifies the rule used to derive `key`. Validated against the current
    #: KEY_VERSION on construction and on load — see `_versions_describe_this_rule`.
    key_version: str = KEY_VERSION

    #: Historical metadata, deliberately *not* validated against the current rules.
    #: Redaction is applied at capture time and only ever gets stricter, so a
    #: recording made under older rules is still a truthful account of what happened
    #: and still contains no secret. It records which rules scrubbed this file, which
    #: is exactly what you want when auditing an old recording. `key_version` and
    #: `cassette_version` are different in kind: they say how to *interpret the file
    #: now*, so a mismatch there means the file cannot be trusted.
    redaction_version: str = REDACTION_VERSION

    key: str = Field(pattern=r"^[0-9a-f]{64}$")

    request: InteractionRequest
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)

    outcome: Literal["success", "error"]
    response: Any = Field(
        default=None,
        description="The provider's raw response, unparsed. Parsing happens after "
        "retrieval so a parser change can be tested against an unchanged recording.",
    )
    error: RecordedError | None = None

    captured_at: datetime = Field(description="Timezone-aware UTC capture time")
    latency_seconds: float = Field(ge=0.0)
    usage: Usage | None = None
    response_metadata: dict = Field(
        default_factory=dict, description="Safe, redacted provider metadata"
    )
    notes: str | None = None

    @model_validator(mode="after")
    def _outcome_matches_payload(self) -> Cassette:
        if self.outcome == "error" and self.error is None:
            raise ValueError("an error cassette must record a RecordedError")
        if self.outcome == "success" and self.error is not None:
            raise ValueError("a success cassette must not record an error")
        return self

    @model_validator(mode="after")
    def _captured_at_is_utc_aware(self) -> Cassette:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError(
                "captured_at must be timezone-aware; a naive local timestamp cannot "
                "honestly tell a viewer how old a recording is"
            )
        return self

    @model_validator(mode="after")
    def _response_is_serializable(self) -> Cassette:
        _assert_json_serializable(self.response, "response")
        _assert_json_serializable(self.response_metadata, "response_metadata")
        return self

    @model_validator(mode="after")
    def _top_level_metadata_matches_the_request(self) -> Cassette:
        """`provider` and `model` are duplicated for convenience, not as a second truth.

        The request descriptor is what the key is derived from, so it is authoritative.
        The top-level copies exist so a listing or an error message can name the
        provider without unpacking the request — but a copy that disagrees with its
        source is worse than no copy, because callers reading `cassette.provider`
        would be told something the key does not reflect.

        The disagreement is reported rather than repaired. Silently rewriting one
        field to match the other would decide, without evidence, which of the two the
        recording actually came from.
        """
        mismatches = []
        if self.provider != self.request.provider:
            mismatches.append(
                f"provider {self.provider!r} != request.provider {self.request.provider!r}"
            )
        if self.model != self.request.model:
            mismatches.append(f"model {self.model!r} != request.model {self.request.model!r}")
        if mismatches:
            raise ValueError(
                "cassette metadata disagrees with its request descriptor, which is "
                f"authoritative: {'; '.join(mismatches)}"
            )
        return self

    @model_validator(mode="after")
    def _versions_describe_this_rule(self) -> Cassette:
        """`key_version` must name the rule that `key` was actually derived under.

        `_key_matches_the_request` recomputes the key using the *current* KEY_VERSION,
        so a cassette claiming a different one is asserting something the recomputation
        never checked. Since KEY_VERSION participates in the digest, the two can only
        be reconciled by rejecting the file.

        This is not version migration. A future migration would rewrite cassettes
        under the new rule; it would not teach the loader to trust a version string it
        cannot verify.
        """
        if self.key_version != KEY_VERSION:
            raise ValueError(
                f"key_version {self.key_version!r} does not name the rule this key was "
                f"validated under ({KEY_VERSION!r}); the metadata cannot be trusted"
            )
        return self

    @model_validator(mode="after")
    def _key_matches_the_request(self) -> Cassette:
        """The stored key must be derivable from the stored descriptor.

        This is what catches a hand-edited or stale cassette: the two can only agree
        if the recording really is of the request it claims to be of.
        """
        expected = self.request.cassette_key()
        if self.key != expected:
            raise ValueError(
                f"cassette key {self.key} does not match its request descriptor "
                f"(which derives {expected})"
            )
        return self

    @property
    def is_error(self) -> bool:
        return self.outcome == "error"

    def summary(self) -> str:
        return (
            f"{self.provider}/{self.model} {self.outcome} "
            f"captured {self.captured_at.date().isoformat()} key {self.key[:12]}"
        )


def new_cassette_key(request: InteractionRequest) -> str:
    key = request.cassette_key()
    if not is_valid_key(key):  # pragma: no cover - sha256 always matches
        raise ValueError(f"derived key {key!r} is not a valid cassette key")
    return key
