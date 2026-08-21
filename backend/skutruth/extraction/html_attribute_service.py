"""Stored HTML -> one Gemini call -> source-bound generic attribute candidates."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from skutruth.contracts import IdentityScope, RunMode
from skutruth.contracts.mpn import canonical_mpn, mpn_matches
from skutruth.identity.html import HtmlIdentityDecision, HtmlIdentityResolution
from skutruth.ingest.html import HtmlArtifact
from skutruth.ingest.models import SourceFragmentKind
from skutruth.replay.models import InteractionRequest
from skutruth.replay.runner import LiveResponse, run_interaction
from skutruth.replay.store import CassetteStore
from skutruth.unilog.attributes import (
    AttributeAuthority,
    AttributeCandidate,
    AttributeEvidence,
    AttributeReason,
    AttributeValueKind,
    UnilogAttributeValue,
    UomResolution,
    parse_boolean,
    parse_controlled_value,
    parse_number,
    parse_simple_range,
    parse_text,
)
from skutruth.unilog.classification import ClassificationDecision

from .config import ENDPOINT, PROVIDER_NAME, VertexConfig
from .errors import (
    ArtifactMismatchError,
    HtmlSourcePayloadTooLargeError,
    IdentityNotExactError,
    MalformedModelResponseError,
)
from .html_attribute_models import (
    HTML_ATTRIBUTE_PROFILE,
    HtmlAttributeExtractionRun,
    HtmlAttributeKey,
    HtmlAttributeProfile,
    HtmlAttributeRejectedProposal,
    HtmlAttributeRejectionCode,
    HtmlAttributeTarget,
    HtmlLocatorBinding,
    RawHtmlAttributeProposal,
    RawHtmlAttributeResponse,
    SourceBoundHtmlAttributeCandidate,
    ValidatedHtmlAttributeExtraction,
)
from .html_attribute_prompt import (
    HTML_ATTRIBUTE_PROMPT_VERSION,
    HTML_ATTRIBUTE_SYSTEM_INSTRUCTION,
    build_html_attribute_user_prompt,
)
from .provider import ExtractionCall, ProviderResult, StructuredExtractionProvider

HTML_ATTRIBUTE_SCHEMA_VERSION = "html-attribute-response@v1"
HTML_SOURCE_PAYLOAD_VERSION = "html-parsed-source@v1"
# Vertex Gemini accepts JSON structured output, but does not accept application/json as
# an inline input Part MIME.  The payload remains canonical JSON bytes, declared as the
# supported textual transport type.
HTML_SOURCE_MEDIA_TYPE = "text/plain"
MAX_HTML_SOURCE_PAYLOAD_BYTES = 64 * 1024

_RELEVANT_TEXT = re.compile(
    r"(?i)model|collection|size|finish|color|colour|glass|shade|width|height|depth|"
    r"extension|light source|socket|wattage|watt|install|orientation|material"
)
_TEXT_NEIGHBOR_WINDOW = 12
_MAX_SELECTED_TEXT_FRAGMENTS = 160
_PRODUCT_SOURCE_FIELDS = frozenset(
    {
        "name",
        "mpn",
        "sku",
        "category",
        "description",
        "color",
        "material",
        "width",
        "height",
        "depth",
    }
)


def _schema_fingerprint(profile: HtmlAttributeProfile) -> str:
    material = {
        "schema_version": HTML_ATTRIBUTE_SCHEMA_VERSION,
        "profile": profile.model_dump(mode="json"),
        "response_schema": RawHtmlAttributeResponse.model_json_schema(),
    }
    encoded = json.dumps(
        material, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def _require_html_exact_identity(
    identity: HtmlIdentityResolution, artifact: HtmlArtifact
) -> str:
    if not isinstance(identity, HtmlIdentityResolution):
        raise IdentityNotExactError("HTML extraction requires HtmlIdentityResolution")
    target = canonical_mpn(identity.target_mpn)
    if (
        identity.decision is not HtmlIdentityDecision.EXACT
        or identity.identity_scope is not IdentityScope.EXACT_SKU
        or target is None
        or not mpn_matches(identity.covers_mpn, target)
        or not mpn_matches(identity.identity_resolution.exact_mpn, target)
    ):
        raise IdentityNotExactError(
            "HTML extraction requires derived EXACT identity, EXACT_SKU scope, and "
            "canonical covers_mpn agreement"
        )
    if identity.artifact_sha256 != artifact.sha256:
        raise ArtifactMismatchError(
            f"identity covers artifact {identity.artifact_sha256}, not {artifact.sha256}"
        )
    return target


def _target(
    identity: HtmlIdentityResolution,
    artifact: HtmlArtifact,
    profile: HtmlAttributeProfile,
) -> HtmlAttributeTarget:
    exact_mpn = _require_html_exact_identity(identity, artifact)
    return HtmlAttributeTarget(
        brand=identity.identity_resolution.brand_normalized,
        exact_mpn=exact_mpn,
        artifact_sha256=artifact.sha256,
        content_sha256=artifact.content_sha256,
        profile_id=profile.profile_id,
        profile_version=profile.version,
    )


def build_html_source_payload(
    artifact: HtmlArtifact,
    *,
    max_bytes: int = MAX_HTML_SOURCE_PAYLOAD_BYTES,
) -> dict[str, Any]:
    """Build one bounded projection of stored parsed content; raw HTML is impossible."""
    fragments = artifact.content.text_fragments
    # Gallery/carousel markup commonly repeats the same caption many times.  Keep the
    # first exact text occurrence so repetition cannot consume the bounded projection.
    seen_relevant_text: set[str] = set()
    matched: set[int] = set()
    for index, fragment in enumerate(fragments):
        text_key = fragment.text.casefold()
        if _RELEVANT_TEXT.search(fragment.text) and text_key not in seen_relevant_text:
            seen_relevant_text.add(text_key)
            matched.add(index)
    selected_indices = sorted(
        {
            neighbor
            for index in matched
            for neighbor in range(
                max(0, index - _TEXT_NEIGHBOR_WINDOW),
                min(len(fragments), index + _TEXT_NEIGHBOR_WINDOW + 1),
            )
        }
    )
    if len(selected_indices) > _MAX_SELECTED_TEXT_FRAGMENTS:
        raise HtmlSourcePayloadTooLargeError(
            f"HTML relevance projection selected {len(selected_indices)} text fragments, "
            f"above the {_MAX_SELECTED_TEXT_FRAGMENTS}-fragment bound; nothing was sent"
        )

    jsonld_values: list[dict[str, Any]] = []

    def pointer_token(value: object) -> str:
        return str(value).replace("~", "~0").replace("/", "~1")

    def add_leaves(value: Any, block_index: int, pointer: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                add_leaves(child, block_index, f"{pointer}/{pointer_token(key)}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                add_leaves(child, block_index, f"{pointer}/{index}")
        else:
            jsonld_values.append(
                {
                    "locator": {
                        "kind": SourceFragmentKind.HTML_JSONLD.value,
                        "jsonld_block_index": block_index,
                        "json_pointer": pointer,
                    },
                    "value": value,
                }
            )

    def add_product(product: dict[str, Any], block_index: int, pointer: str) -> None:
        for key in _PRODUCT_SOURCE_FIELDS:
            if key in product:
                add_leaves(
                    product[key], block_index, f"{pointer}/{pointer_token(key)}"
                )
        if "additionalProperty" in product:
            add_leaves(
                product["additionalProperty"],
                block_index,
                f"{pointer}/additionalProperty",
            )

    for block_index, block in enumerate(artifact.content.jsonld_blocks):
        parsed = block.parsed
        if isinstance(parsed, dict) and str(parsed.get("@type", "")).casefold() == "product":
            add_product(parsed, block_index, "")
        elif isinstance(parsed, list):
            for index, item in enumerate(parsed):
                if isinstance(item, dict) and str(item.get("@type", "")).casefold() == (
                    "product"
                ):
                    add_product(item, block_index, f"/{index}")

    payload: dict[str, Any] = {
        "source_payload_version": HTML_SOURCE_PAYLOAD_VERSION,
        "artifact_sha256": artifact.sha256,
        "content_sha256": artifact.content_sha256,
        "visible_text_fragments": [
            {
                "text": fragments[index].text,
                "locator": fragments[index].locator.model_dump(mode="json"),
            }
            for index in selected_indices
        ],
        "jsonld_values": jsonld_values,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if len(encoded) > max_bytes:
        raise HtmlSourcePayloadTooLargeError(
            f"parsed HTML source payload is {len(encoded):,} bytes, above the "
            f"{max_bytes:,}-byte bound; it was not truncated or sent"
        )
    return payload


def build_html_interaction_request(
    identity: HtmlIdentityResolution,
    artifact: HtmlArtifact,
    *,
    config: VertexConfig,
    profile: HtmlAttributeProfile = HTML_ATTRIBUTE_PROFILE,
) -> InteractionRequest:
    target = _target(identity, artifact, profile)
    return InteractionRequest(
        provider=PROVIDER_NAME,
        model=config.model,
        endpoint=ENDPOINT,
        payload={
            "location": config.location,
            "exact_mpn": target.exact_mpn,
            "content_sha256": target.content_sha256,
            "profile_id": profile.profile_id,
            "profile_version": profile.version,
            "schema_version": HTML_ATTRIBUTE_SCHEMA_VERSION,
            "source_payload_version": HTML_SOURCE_PAYLOAD_VERSION,
            "media_type": HTML_SOURCE_MEDIA_TYPE,
        },
        prompt_version=HTML_ATTRIBUTE_PROMPT_VERSION,
        schema_version=_schema_fingerprint(profile),
        stage_version=HTML_ATTRIBUTE_SCHEMA_VERSION,
        tools=(),
        artifact_hashes=(artifact.sha256,),
    )


def _decode_pointer_token(token: str) -> str:
    if re.search(r"~(?:[^01]|$)", token):
        raise ValueError("JSON pointer contains an invalid tilde escape")
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_json_pointer(value: Any, pointer: str | None) -> Any:
    if pointer is None:
        raise ValueError("JSON-LD locator needs an RFC 6901 pointer")
    if pointer == "":
        return value
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must be empty or begin with /")
    current = value
    for encoded in pointer[1:].split("/"):
        token = _decode_pointer_token(encoded)
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"object has no key {token!r}")
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise ValueError(f"{token!r} is not a canonical array index")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"array index {index} is out of range")
            current = current[index]
        else:
            raise ValueError("pointer continues beyond a scalar value")
    return current


def _source_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _bind_locator(
    proposal: RawHtmlAttributeProposal, artifact: HtmlArtifact
) -> tuple[str, Any]:
    locator = proposal.locator
    if locator is None:
        raise LookupError("missing")
    if locator.kind is SourceFragmentKind.HTML_TEXT:
        fragment = next(
            (
                item
                for item in artifact.content.text_fragments
                if item.locator == locator
            ),
            None,
        )
        if fragment is None:
            raise ValueError("visible-text offsets do not name an exact stored fragment")
        return fragment.text, fragment.text
    if locator.kind is SourceFragmentKind.HTML_JSONLD:
        index = locator.jsonld_block_index
        assert index is not None
        if index >= len(artifact.content.jsonld_blocks):
            raise ValueError(f"JSON-LD block {index} does not exist")
        block = artifact.content.jsonld_blocks[index]
        if block.parse_error is not None or block.parsed is None:
            raise ValueError(f"JSON-LD block {index} is not parsed content")
        value = _resolve_json_pointer(block.parsed, locator.json_pointer)
        return _source_text(value), value
    raise ValueError("HTML candidate locator cannot address a PDF page")


def _finish_is_exact_variant(
    proposal: RawHtmlAttributeProposal, artifact: HtmlArtifact, exact_mpn: str | None
) -> bool:
    locator = proposal.locator
    if (
        exact_mpn is None
        or locator is None
        or locator.kind is not SourceFragmentKind.HTML_JSONLD
        or locator.json_pointer is None
        or not locator.json_pointer.endswith("/value")
    ):
        return False
    index = locator.jsonld_block_index
    assert index is not None
    if index >= len(artifact.content.jsonld_blocks):
        return False
    parent_pointer = locator.json_pointer[: -len("/value")]
    try:
        parent = _resolve_json_pointer(
            artifact.content.jsonld_blocks[index].parsed, parent_pointer
        )
    except ValueError:
        return False
    return bool(
        isinstance(parent, dict)
        and str(parent.get("name", "")).casefold() == "finish"
        and mpn_matches(str(parent.get("propertyID", "")), exact_mpn)
    )


def _parse_value(proposal: RawHtmlAttributeProposal) -> UnilogAttributeValue:
    if proposal.value_kind is AttributeValueKind.TEXT:
        return parse_text(proposal.raw_value, raw_uom=proposal.raw_uom)
    if proposal.value_kind is AttributeValueKind.NUMBER:
        return parse_number(proposal.raw_value, raw_uom=proposal.raw_uom)
    if proposal.value_kind is AttributeValueKind.RANGE:
        return parse_simple_range(proposal.raw_value, raw_uom=proposal.raw_uom)
    if proposal.value_kind is AttributeValueKind.ENUM:
        return parse_controlled_value(proposal.raw_value, raw_uom=proposal.raw_uom)
    if proposal.raw_uom:
        raise ValueError("BOOLEAN values cannot carry a UOM")
    return parse_boolean(proposal.raw_value)


def _value_is_present(proposal: RawHtmlAttributeProposal, bound_text: str) -> bool:
    if (
        proposal.locator
        and proposal.locator.kind is SourceFragmentKind.HTML_JSONLD
        and not proposal.raw_uom
    ):
        return proposal.raw_value == bound_text
    if proposal.raw_value not in bound_text:
        return False
    if not proposal.raw_uom:
        return True
    pattern = re.escape(proposal.raw_value) + r"\s+" + re.escape(proposal.raw_uom)
    return re.search(pattern, bound_text) is not None


def _validate_one(
    proposal: RawHtmlAttributeProposal,
    *,
    artifact: HtmlArtifact,
    profile: HtmlAttributeProfile,
    exact_mpn: str | None,
) -> SourceBoundHtmlAttributeCandidate | HtmlAttributeRejectedProposal:
    def reject(
        code: HtmlAttributeRejectionCode, detail: str
    ) -> HtmlAttributeRejectedProposal:
        return HtmlAttributeRejectedProposal(
            source_key=proposal.source_key, code=code, detail=detail
        )

    concept = profile.concept(proposal.source_key)
    if proposal.value_kind is not concept.value_kind:
        return reject(
            HtmlAttributeRejectionCode.VALUE_KIND_MISMATCH,
            f"{proposal.value_kind.value} does not match the fixed "
            f"{concept.value_kind.value} profile kind",
        )
    if proposal.locator is None:
        return reject(
            HtmlAttributeRejectionCode.MISSING_LOCATOR,
            "a non-null proposal requires an HTML_TEXT or HTML_JSONLD locator",
        )
    try:
        bound_text, _bound_value = _bind_locator(proposal, artifact)
    except ValueError as exc:
        return reject(HtmlAttributeRejectionCode.LOCATOR_INVALID, str(exc))
    if proposal.source_excerpt != bound_text:
        return reject(
            HtmlAttributeRejectionCode.SOURCE_MISMATCH,
            "source_excerpt does not exactly equal the stored locator value",
        )
    if not _value_is_present(proposal, bound_text):
        return reject(
            HtmlAttributeRejectionCode.SOURCE_MISMATCH,
            "raw_value/raw_uom are not copied exactly from the bound source excerpt",
        )
    if proposal.source_key is HtmlAttributeKey.FINISH_NAME and not _finish_is_exact_variant(
        proposal, artifact, exact_mpn
    ):
        return reject(
            HtmlAttributeRejectionCode.SOURCE_MISMATCH,
            "finish is not JSON-LD-bound by propertyID to the exact target MPN",
        )
    try:
        value = _parse_value(proposal)
    except ValueError as exc:
        return reject(HtmlAttributeRejectionCode.INVALID_VALUE, str(exc))

    reason = (
        AttributeReason.UNKNOWN_UOM
        if value.uom_resolution is UomResolution.UNRESOLVED
        else AttributeReason.CANDIDATE_REQUIRES_REVIEW
    )
    locator_json = json.dumps(
        proposal.locator.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    candidate = AttributeCandidate(
        source_key=concept.source_key.value,
        label=concept.label,
        value=value,
        decision=ClassificationDecision.REVIEW,
        reason=reason,
        authority=AttributeAuthority.MODEL_PROPOSAL,
        evidence=(
            AttributeEvidence(
                artifact_id=artifact.artifact_id,
                source_locator=locator_json,
                source_fragment=proposal.source_excerpt,
                span_start=(
                    proposal.locator.char_start
                    if proposal.locator.kind is SourceFragmentKind.HTML_TEXT
                    else None
                ),
                span_end=(
                    proposal.locator.char_end
                    if proposal.locator.kind is SourceFragmentKind.HTML_TEXT
                    else None
                ),
                verification=None,
            ),
        ),
    )
    return SourceBoundHtmlAttributeCandidate(
        candidate=candidate,
        locator=proposal.locator,
        source_excerpt=proposal.source_excerpt,
        binding=HtmlLocatorBinding.EXACT,
    )


def validate_html_attribute_response(
    payload: dict[str, Any],
    *,
    artifact: HtmlArtifact,
    profile: HtmlAttributeProfile = HTML_ATTRIBUTE_PROFILE,
    exact_mpn: str | None = None,
) -> ValidatedHtmlAttributeExtraction:
    """Strict parse followed by deterministic binding and value parsing, with no repair."""
    try:
        raw = RawHtmlAttributeResponse.model_validate(payload)
    except ValidationError as exc:
        raise MalformedModelResponseError(
            "response failed the strict HTML attribute schema: "
            + str(exc).replace("\n", " ")[:500]
        ) from exc

    if exact_mpn is None:
        for block in artifact.content.jsonld_blocks:
            if isinstance(block.parsed, dict) and str(block.parsed.get("@type", "")).casefold() == (
                "product"
            ):
                candidate_mpn = block.parsed.get("mpn")
                if isinstance(candidate_mpn, str):
                    exact_mpn = canonical_mpn(candidate_mpn)
                    break

    counts = Counter(item.source_key for item in raw.proposals)
    by_key: dict[HtmlAttributeKey, list[RawHtmlAttributeProposal]] = {}
    for proposal in raw.proposals:
        by_key.setdefault(proposal.source_key, []).append(proposal)

    candidates: list[SourceBoundHtmlAttributeCandidate] = []
    rejected: list[HtmlAttributeRejectedProposal] = []
    abstained: list[HtmlAttributeKey] = []
    for concept in profile.concepts:
        proposals = by_key.get(concept.source_key, [])
        if not proposals:
            abstained.append(concept.source_key)
            continue
        if counts[concept.source_key] > 1:
            rejected.extend(
                HtmlAttributeRejectedProposal(
                    source_key=concept.source_key,
                    code=HtmlAttributeRejectionCode.DUPLICATE_SOURCE_KEY,
                    detail="multiple proposals for one source_key are all rejected",
                )
                for _proposal in proposals
            )
            continue
        outcome = _validate_one(
            proposals[0], artifact=artifact, profile=profile, exact_mpn=exact_mpn
        )
        (candidates if isinstance(outcome, SourceBoundHtmlAttributeCandidate) else rejected).append(
            outcome
        )

    return ValidatedHtmlAttributeExtraction(
        candidates=tuple(candidates),
        rejected=tuple(rejected),
        requested_source_keys=tuple(item.source_key for item in profile.concepts),
        abstained_source_keys=tuple(abstained),
    )


def extract_html_attribute_candidates(
    *,
    identity: HtmlIdentityResolution,
    artifact: HtmlArtifact,
    provider: StructuredExtractionProvider,
    store: CassetteStore,
    config: VertexConfig,
    mode: RunMode = RunMode.REPLAY,
    profile: HtmlAttributeProfile = HTML_ATTRIBUTE_PROFILE,
) -> HtmlAttributeExtractionRun:
    """Run at most one model interaction over a bounded stored HTML read model."""
    target = _target(identity, artifact, profile)
    source_payload = build_html_source_payload(artifact)
    source_bytes = json.dumps(
        source_payload, sort_keys=True, separators=(",", ":")
    ).encode()
    request = build_html_interaction_request(
        identity, artifact, config=config, profile=profile
    )
    call = ExtractionCall(
        model=config.model,
        system_instruction=HTML_ATTRIBUTE_SYSTEM_INSTRUCTION,
        user_prompt=build_html_attribute_user_prompt(target, profile),
        document_bytes=source_bytes,
        document_media_type=HTML_SOURCE_MEDIA_TYPE,
        response_schema=RawHtmlAttributeResponse.model_json_schema(),
    )

    live: Callable[[], LiveResponse] | None = None
    if mode is RunMode.LIVE:

        def live() -> LiveResponse:
            result: ProviderResult = provider.generate(call)
            return LiveResponse(
                response=result.payload,
                usage=result.usage,
                metadata=(
                    {"model_version": result.model_version}
                    if result.model_version
                    else None
                ),
            )

    outcome = run_interaction(
        mode=mode, request=request, store=store, live_callable=live
    )
    payload = outcome.cassette.response
    if not isinstance(payload, dict):
        raise MalformedModelResponseError(
            f"expected an object from {config.model}, got {type(payload).__name__}"
        )
    try:
        raw = RawHtmlAttributeResponse.model_validate(payload)
    except ValidationError as exc:
        raise MalformedModelResponseError(
            "response failed the strict HTML attribute schema: "
            + str(exc).replace("\n", " ")[:500]
        ) from exc
    validated = validate_html_attribute_response(
        payload, artifact=artifact, profile=profile, exact_mpn=target.exact_mpn
    )
    return HtmlAttributeExtractionRun(
        target=target,
        raw=raw,
        validated=validated,
        mode=outcome.mode,
        replayed=outcome.replayed,
        cassette_key=outcome.key,
        usage=outcome.cassette.usage,
        latency_seconds=outcome.cassette.latency_seconds,
    )


__all__ = [
    "HTML_ATTRIBUTE_SCHEMA_VERSION",
    "HTML_SOURCE_MEDIA_TYPE",
    "HTML_SOURCE_PAYLOAD_VERSION",
    "MAX_HTML_SOURCE_PAYLOAD_BYTES",
    "build_html_interaction_request",
    "build_html_source_payload",
    "extract_html_attribute_candidates",
    "validate_html_attribute_response",
]
