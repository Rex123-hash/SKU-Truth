"""The provider boundary.

Business logic never imports `google.genai`. It calls a `StructuredExtractionProvider`,
which is satisfied by the real Vertex client in production and by a deterministic fake in
tests — so the whole committed suite runs offline, and swapping providers cannot change
what a candidate means.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from skutruth.replay.models import Usage


@dataclass(frozen=True, slots=True)
class ExtractionCall:
    """Everything a provider needs to make one structured-output request.

    The document arrives as bytes. Provenance is the SHA-256 recorded on the request
    descriptor, never the transport: whether a provider sends inline bytes or a URI, the
    evidence identity is the hash of what SKUTruth ingested.
    """

    model: str
    system_instruction: str
    user_prompt: str
    document_bytes: bytes
    document_media_type: str
    response_schema: dict


@dataclass(frozen=True, slots=True)
class ProviderResult:
    """A provider's raw structured payload plus whatever usage it reported.

    `usage` stays `None` when the provider reports nothing. Cost is only ever what the
    provider itself returns — this layer has no pricing table and must not invent one.
    """

    payload: dict
    usage: Usage | None = None
    model_version: str | None = None


class StructuredExtractionProvider(Protocol):
    """One structured-output call. Deliberately the entire interface."""

    def generate(self, call: ExtractionCall) -> ProviderResult:  # pragma: no cover - protocol
        ...


__all__ = ["ExtractionCall", "ProviderResult", "StructuredExtractionProvider"]
