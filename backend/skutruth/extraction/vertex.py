"""The production Vertex AI Gemini provider.

The only module that imports `google.genai`. It is imported lazily inside the client
factory so the rest of the package — and the whole committed test suite — works without
the SDK or any credentials present.

Verified against google-genai 2.18.1 on Vertex: `Client(vertexai=True, project=…,
location=…)`, `Part.from_bytes` for an inline PDF, `response_schema` for structured
output, and `usage_metadata` for token counts.

The PDF is sent as inline bytes. For a datasheet-sized document that is the smallest
mechanism that works, and it keeps the exact ingested bytes as the thing the model read —
no upload step, no second copy, no GCS bucket to drift from the artifact store.
"""

from __future__ import annotations

from skutruth.replay.models import Usage

from .config import VertexConfig
from .errors import MalformedModelResponseError
from .provider import ExtractionCall, ProviderResult


def _usage_from_response(response) -> Usage | None:
    """Map provider usage onto the neutral shape. Nothing is derived or summed."""
    meta = getattr(response, "usage_metadata", None)
    if meta is None:
        return None
    usage = Usage(
        input_tokens=getattr(meta, "prompt_token_count", None),
        output_tokens=getattr(meta, "candidates_token_count", None),
        total_tokens=getattr(meta, "total_token_count", None),
        cached_input_tokens=getattr(meta, "cached_content_token_count", None),
        reasoning_tokens=getattr(meta, "thoughts_token_count", None),
        # Vertex reports no per-call price. Leaving this None is the honest answer;
        # a pricing table belongs to a costing layer that can be reviewed.
        provider_reported_cost=None,
    )
    return None if usage.is_empty else usage


class VertexGeminiExtractionProvider:
    """One structured-output call against Vertex AI.

    Holds no business logic. It does not know what an ETIM feature is, and it never
    decides whether a response is a good extraction — only whether it is parseable.
    """

    def __init__(self, config: VertexConfig, client=None) -> None:
        self.config = config
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            from google import genai  # imported lazily; absent in offline test runs

            self._client = genai.Client(
                vertexai=True, project=self.config.project, location=self.config.location
            )
        return self._client

    def generate(self, call: ExtractionCall) -> ProviderResult:
        import json

        from google.genai import types

        client = self._ensure_client()
        response = client.models.generate_content(
            model=call.model,
            contents=[
                types.Part.from_bytes(data=call.document_bytes, mime_type=call.document_media_type),
                call.user_prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=call.response_schema,
                system_instruction=call.system_instruction,
                # Deterministic decoding. Extraction is a reading task, and sampling
                # would make the same document yield different facts between runs.
                temperature=0.0,
            ),
        )

        text = getattr(response, "text", None)
        if not text:
            raise MalformedModelResponseError(
                f"{call.model} returned no text content; "
                f"finish reason {getattr(response, 'candidates', None) and 'see candidates'}"
            )
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MalformedModelResponseError(
                f"{call.model} returned non-JSON despite a structured response schema: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise MalformedModelResponseError(
                f"{call.model} returned a {type(payload).__name__}, not an object"
            )

        return ProviderResult(
            payload=payload,
            usage=_usage_from_response(response),
            model_version=getattr(response, "model_version", None),
        )


__all__ = ["VertexGeminiExtractionProvider"]
