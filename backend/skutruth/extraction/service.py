"""The extraction stage: gate, call, validate.

    EXACT identity + versioned artifact + ETIM class schema
            ↓
    Gemini proposes candidate observations   (through record/replay, always)
            ↓
    deterministic parsing and validation
            ↓
    ValidatedExtraction

Three properties this module exists to hold:

**Identity is a precondition, not a question for the model.** Extraction runs only for a
resolved `EXACT` reference. Handing a family stem to a model and asking it to work out
which variant is meant would relocate the exact-identity decision from the deterministic
resolver into a guess.

**Every call goes through record/replay.** There is no path from here to Vertex that
skips the runner. A REPLAY run cannot reach the network, which is the only reason a
measurement taken from one means anything.

**The model proposes; this module decides.** Feature ids, value types, units, page
bounds, and the source-fragment requirement are all checked here against the frozen ETIM
work. Condition *completeness* is derived by `resolve_conditions` and never read from the
response, because completeness is what a support grade will turn on.
"""

from __future__ import annotations

from collections.abc import Callable

from pydantic import ValidationError

from skutruth.contracts import (
    Condition,
    ConditionSet,
    IdentityDisposition,
    RunMode,
)
from skutruth.etim.demo_classes import DemoClassConfig
from skutruth.etim.loader import EtimClass
from skutruth.etim.schema_gen import ClassExtractionSchema, build_extraction_schema
from skutruth.etim.validators import (
    RawFeatureValue,
    build_value,
    resolve_conditions,
    validate_feature_value,
)
from skutruth.identity.models import IdentityResolution
from skutruth.ingest.hashing import sha256_bytes
from skutruth.ingest.models import IngestedArtifact
from skutruth.replay.models import InteractionRequest
from skutruth.replay.runner import LiveResponse, run_interaction
from skutruth.replay.store import CassetteStore

from .config import ENDPOINT, PROVIDER_NAME, VertexConfig
from .errors import ArtifactMismatchError, IdentityNotExactError, MalformedModelResponseError
from .models import (
    ExtractionCandidate,
    ExtractionRun,
    ExtractionTarget,
    RawModelExtraction,
    RejectedProposal,
    RejectionCode,
    ValidatedExtraction,
)
from .prompt import PROMPT_VERSION, SYSTEM_INSTRUCTION, build_user_prompt
from .provider import ExtractionCall, ProviderResult, StructuredExtractionProvider

MEDIA_TYPE = "application/pdf"


def require_exact_identity(identity: IdentityResolution) -> str:
    """Return the resolved reference, or refuse. The gate, in one place."""
    if identity.disposition is not IdentityDisposition.EXACT or not identity.exact_mpn:
        raise IdentityNotExactError(
            f"extraction requires an EXACT identity; {identity.mpn_normalized} resolved to "
            f"{identity.disposition.value}. Resolve the reference first — the model is not "
            f"asked to work out which product was meant."
        )
    return identity.exact_mpn


def build_interaction_request(
    target: ExtractionTarget, schema: ClassExtractionSchema, config: VertexConfig
) -> InteractionRequest:
    """The replay descriptor.

    Carries provider, model, and location, plus the prompt and schema versions and the
    artifact hash. Changing any of them yields a different key, so a new model or a
    reworded prompt cannot silently reuse an old recording.
    """
    return InteractionRequest(
        provider=PROVIDER_NAME,
        model=config.model,
        endpoint=ENDPOINT,
        payload={
            "location": config.location,
            "brand": target.brand,
            "exact_mpn": target.exact_mpn,
            "etim_class_id": target.etim_class_id,
            "page_count": target.page_count,
            "media_type": MEDIA_TYPE,
        },
        prompt_version=PROMPT_VERSION,
        schema_version=schema.fingerprint(),
        artifact_hashes=(target.artifact_sha256,),
    )


def extract_product_attributes(
    *,
    identity: IdentityResolution,
    artifact: IngestedArtifact,
    artifact_bytes: bytes,
    etim_class: EtimClass,
    provider: StructuredExtractionProvider,
    store: CassetteStore,
    config: VertexConfig,
    mode: RunMode = RunMode.REPLAY,
    demo_config: DemoClassConfig | None = None,
    feature_ids: tuple[str, ...] | None = None,
) -> ExtractionRun:
    """Run one extraction for one exact reference against one artifact."""
    exact_mpn = require_exact_identity(identity)

    actual = sha256_bytes(artifact_bytes)
    if actual != artifact.sha256:
        raise ArtifactMismatchError(
            f"supplied bytes hash to {actual}, but the artifact is {artifact.sha256}"
        )

    schema = build_extraction_schema(etim_class, demo_config, feature_ids=feature_ids)
    target = ExtractionTarget(
        brand=identity.brand_normalized,
        exact_mpn=exact_mpn,
        etim_class_id=schema.etim_class_id,
        artifact_sha256=artifact.sha256,
        page_count=artifact.page_count,
    )
    request = build_interaction_request(target, schema, config)

    call = ExtractionCall(
        model=config.model,
        system_instruction=SYSTEM_INSTRUCTION,
        user_prompt=build_user_prompt(target, schema),
        document_bytes=artifact_bytes,
        document_media_type=MEDIA_TYPE,
        response_schema=schema.json_schema(),
    )

    live: Callable[[], LiveResponse] | None = None
    if mode is RunMode.LIVE:

        def live() -> LiveResponse:
            result: ProviderResult = provider.generate(call)
            return LiveResponse(
                response=result.payload,
                usage=result.usage,
                metadata=(
                    {"model_version": result.model_version} if result.model_version else None
                ),
            )

    outcome = run_interaction(mode=mode, request=request, store=store, live_callable=live)

    payload = outcome.cassette.response
    if not isinstance(payload, dict):
        raise MalformedModelResponseError(
            f"expected an object from {config.model}, got {type(payload).__name__}"
        )

    raw = RawModelExtraction(
        model=config.model,
        prompt_version=PROMPT_VERSION,
        schema_fingerprint=schema.fingerprint(),
        payload=payload,
    )
    validated = validate_raw_extraction(
        raw, schema=schema, etim_class=etim_class, demo_config=demo_config, target=target
    )

    return ExtractionRun(
        target=target,
        raw=raw,
        validated=validated,
        mode=outcome.mode,
        replayed=outcome.replayed,
        cassette_key=outcome.key,
        usage=outcome.cassette.usage,
        latency_seconds=outcome.cassette.latency_seconds,
    )


def validate_raw_extraction(
    raw: RawModelExtraction,
    *,
    schema: ClassExtractionSchema,
    etim_class: EtimClass,
    target: ExtractionTarget,
    demo_config: DemoClassConfig | None = None,
) -> ValidatedExtraction:
    """Turn proposals into candidates, or into rejections with reasons.

    Pure and deterministic: the same payload always produces the same outcome. Nothing
    is silently repaired — a page number outside the document is rejected rather than
    clamped, because a clamped citation points somewhere nobody chose.
    """
    candidates: list[ExtractionCandidate] = []
    rejected: list[RejectedProposal] = []
    abstained: list[str] = []
    requested = schema.feature_ids
    proposed = raw.proposed_features

    # Schema order first, then any unrecognised ids sorted. Iterating the payload's own
    # key order would make the result depend on how the model happened to serialise it —
    # and cassettes are stored with sorted keys, so a LIVE run and its own REPLAY would
    # disagree on ordering alone.
    ordered_ids = [f for f in requested if f in proposed]
    ordered_ids += sorted(k for k in proposed if k not in set(requested))

    for feature_id in ordered_ids:
        proposal = proposed[feature_id]
        if schema.feature(feature_id) is None:
            rejected.append(
                RejectedProposal(
                    etim_feature_id=feature_id,
                    code=RejectionCode.UNKNOWN_FEATURE,
                    detail=f"{feature_id} was not requested for {schema.etim_class_id}",
                )
            )
            continue
        if proposal is None:
            abstained.append(feature_id)
            continue
        if not isinstance(proposal, dict):
            rejected.append(
                RejectedProposal(
                    etim_feature_id=feature_id,
                    code=RejectionCode.MALFORMED_PROPOSAL,
                    detail=f"expected an object, got {type(proposal).__name__}",
                )
            )
            continue

        outcome = _validate_one(
            feature_id,
            proposal,
            schema=schema,
            etim_class=etim_class,
            demo_config=demo_config,
            target=target,
        )
        (candidates if isinstance(outcome, ExtractionCandidate) else rejected).append(outcome)

    return ValidatedExtraction(
        candidates=tuple(candidates),
        rejected=tuple(rejected),
        abstained_feature_ids=tuple(abstained),
        requested_feature_ids=requested,
    )


def _validate_one(
    feature_id: str,
    proposal: dict,
    *,
    schema: ClassExtractionSchema,
    etim_class: EtimClass,
    target: ExtractionTarget,
    demo_config: DemoClassConfig | None,
) -> ExtractionCandidate | RejectedProposal:
    def reject(code: RejectionCode, detail: str) -> RejectedProposal:
        return RejectedProposal(etim_feature_id=feature_id, code=code, detail=detail)

    # `RawFeatureValue` already requires a non-empty raw_text and a page >= 1, so a
    # value offered without locatable support cannot get past construction.
    try:
        candidate_raw = RawFeatureValue.model_validate(proposal)
    except ValidationError as exc:
        missing = {tuple(e["loc"]) for e in exc.errors()}
        if ("raw_text",) in missing or ("page",) in missing:
            return reject(
                RejectionCode.MISSING_SOURCE_FRAGMENT,
                "a non-null value must carry verbatim source wording and a page number; "
                f"{exc.error_count()} field problem(s)",
            )
        return reject(RejectionCode.MALFORMED_PROPOSAL, str(exc).replace("\n", " ")[:300])

    if candidate_raw.page > target.page_count:
        return reject(
            RejectionCode.PAGE_OUT_OF_RANGE,
            f"page {candidate_raw.page} does not exist; the artifact has "
            f"{target.page_count}. Not clamped — a citation must point where the model "
            f"actually claimed.",
        )

    value, result = build_value(etim_class, feature_id, candidate_raw)
    if value is None:
        return reject(
            RejectionCode.INVALID_VALUE,
            "; ".join(i.message for i in result.issues) or "value failed ETIM validation",
        )
    type_result = validate_feature_value(etim_class, feature_id, value)
    if not type_result.ok:
        return reject(
            RejectionCode.INVALID_VALUE,
            "; ".join(i.message for i in type_result.issues),
        )

    conditions = ConditionSet(
        conditions=tuple(
            Condition(kind=c.kind, value=c.value, raw=c.raw) for c in candidate_raw.conditions
        )
    )
    # Completeness is derived, never accepted from the model.
    conditions = resolve_conditions(demo_config, feature_id, conditions)

    feature_schema = schema.feature(feature_id)
    return ExtractionCandidate(
        etim_feature_id=feature_id,
        feature_name=feature_schema.name,
        value=value,
        conditions=conditions,
        source_fragment=candidate_raw.raw_text,
        page_number=candidate_raw.page,
        buyer_critical=feature_schema.buyer_critical,
    )


__all__ = [
    "build_interaction_request",
    "extract_product_attributes",
    "require_exact_identity",
    "validate_raw_extraction",
]
