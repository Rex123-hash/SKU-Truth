"""Conservative factual verification for source-bound HTML attribute proposals.

This adapter is deliberately separate from the frozen PDF verifier.  Locator binding has
already shown that a model pointed at stored content; this module asks the different
question: does that exact structured property or text fragment establish the configured
attribute/value relationship?
"""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import EvidenceVerification, IdentityScope
from skutruth.contracts.mpn import mpn_matches
from skutruth.discovery.models import SourceAuthority
from skutruth.extraction.html_attribute_models import (
    HTML_ATTRIBUTE_PROFILE,
    HtmlAttributeKey,
    SourceBoundHtmlAttributeCandidate,
)
from skutruth.identity.html import (
    HtmlIdentityDecision,
    HtmlIdentityObservationKind,
    HtmlIdentityResolution,
)
from skutruth.ingest.html import HtmlArtifact, HtmlEvidenceLocator
from skutruth.ingest.models import SourceFragmentKind
from skutruth.unilog.attributes import (
    AttributeAuthority,
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


class HtmlVerificationProfileAuthority(StrEnum):
    LOCAL_DEMO_INTERNAL = "LOCAL_DEMO_INTERNAL"


class HtmlPropertyIdRule(StrEnum):
    NONE = "NONE"
    TARGET_MPN = "TARGET_MPN"


class HtmlAttributeVerificationRule(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: HtmlAttributeKey
    jsonld_property_names: tuple[str, ...] = ()
    jsonld_property_id_rule: HtmlPropertyIdRule = HtmlPropertyIdRule.NONE
    html_text_labels: tuple[str, ...] = ()


class HtmlAttributeVerificationProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    authority: HtmlVerificationProfileAuthority
    official_unilog_authority: bool = False
    rules: tuple[HtmlAttributeVerificationRule, ...]

    def rule(self, source_key: str) -> HtmlAttributeVerificationRule | None:
        return next((item for item in self.rules if item.source_key.value == source_key), None)


HTML_ATTRIBUTE_VERIFICATION_PROFILE = HtmlAttributeVerificationProfile(
    profile_id="lighting-html-verification-local-demo",
    version="lighting-html-verification-local-demo@v1",
    authority=HtmlVerificationProfileAuthority.LOCAL_DEMO_INTERNAL,
    official_unilog_authority=False,
    rules=(
        # Kichler exposes both of these only as generic name="Attribute" entries.  A
        # generic bucket does not establish which internal concept the value belongs to,
        # so the reviewed rule intentionally licenses no structured property alias.
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.LIGHT_COUNT_DESCRIPTOR,
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.DIFFUSER_DESCRIPTION,
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.OVERALL_DEPTH,
            jsonld_property_names=("Depth",),
            html_text_labels=("Depth",),
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.OVERALL_HEIGHT,
            jsonld_property_names=("Height",),
            html_text_labels=("Height",),
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.OVERALL_WIDTH,
            jsonld_property_names=("Width",),
            html_text_labels=("Width",),
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.FINISH_NAME,
            jsonld_property_names=("finish",),
            jsonld_property_id_rule=HtmlPropertyIdRule.TARGET_MPN,
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.INSTALLATION_ORIENTATION,
            html_text_labels=("Install Glass up or Down",),
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.SHADE_DIMENSIONS,
            html_text_labels=("Shade Dimensions",),
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.SOCKET_CONFIGURATION,
            html_text_labels=("Socket",),
        ),
        HtmlAttributeVerificationRule(
            source_key=HtmlAttributeKey.LAMP_WATTAGE,
            html_text_labels=("Wattage",),
        ),
    ),
)


class HtmlAttributeVerificationStatus(StrEnum):
    VERIFIED = "VERIFIED"
    REVIEW = "REVIEW"
    UNVERIFIED = "UNVERIFIED"


class HtmlAttributeVerificationReason(StrEnum):
    FACT_VERIFIED = "FACT_VERIFIED"
    IDENTITY_NOT_EXACT = "IDENTITY_NOT_EXACT"
    MANUFACTURER_AUTHORITY_REQUIRED = "MANUFACTURER_AUTHORITY_REQUIRED"
    ARTIFACT_MISMATCH = "ARTIFACT_MISMATCH"
    UNKNOWN_SOURCE_KEY = "UNKNOWN_SOURCE_KEY"
    LOCATOR_INVALID = "LOCATOR_INVALID"
    OUTSIDE_TARGET_PRODUCT = "OUTSIDE_TARGET_PRODUCT"
    MALFORMED_STRUCTURED_PROPERTY = "MALFORMED_STRUCTURED_PROPERTY"
    SOURCE_PROPERTY_NOT_AUTHORIZED = "SOURCE_PROPERTY_NOT_AUTHORIZED"
    PROPERTY_ID_MISMATCH = "PROPERTY_ID_MISMATCH"
    VALUE_NOT_SUPPORTED = "VALUE_NOT_SUPPORTED"
    UOM_NOT_SUPPORTED = "UOM_NOT_SUPPORTED"
    CONFLICTING_PROPERTY_VALUES = "CONFLICTING_PROPERTY_VALUES"
    EXPECTED_LABEL_MISSING = "EXPECTED_LABEL_MISSING"
    AMBIGUOUS_TEXT_FRAGMENT = "AMBIGUOUS_TEXT_FRAGMENT"
    UNSUPPORTED_EVIDENCE_KIND = "UNSUPPORTED_EVIDENCE_KIND"


class HtmlUnilogMappingStatus(StrEnum):
    UNAUTHORIZED = "UNAUTHORIZED"


class VerifiedHtmlAttributeFact(BaseModel):
    """An internal manufacturer fact, not an AttributeCandidate or delivery mapping."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_mpn: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    raw_value: str = Field(min_length=1)
    raw_uom: str
    normalized_value: str = Field(min_length=1)
    normalized_uom: str | None = None
    locator: HtmlEvidenceLocator
    source_label: str = Field(min_length=1)
    source_raw_value: str = Field(min_length=1)
    source_raw_uom: str
    authority: AttributeAuthority = AttributeAuthority.MANUFACTURER_EVIDENCE
    decision: ClassificationDecision = ClassificationDecision.COMMIT
    delivery_eligible: bool = False
    unilog_mapping_status: HtmlUnilogMappingStatus = HtmlUnilogMappingStatus.UNAUTHORIZED

    @model_validator(mode="after")
    def _is_internal_manufacturer_fact_only(self) -> VerifiedHtmlAttributeFact:
        if self.authority is not AttributeAuthority.MANUFACTURER_EVIDENCE:
            raise ValueError("verified HTML fact authority must be MANUFACTURER_EVIDENCE")
        if self.decision is not ClassificationDecision.COMMIT:
            raise ValueError("verified HTML fact decision must be internal COMMIT")
        if self.delivery_eligible or self.unilog_mapping_status is not (
            HtmlUnilogMappingStatus.UNAUTHORIZED
        ):
            raise ValueError("verified HTML facts cannot claim Unilog delivery authority")
        return self


class HtmlAttributeVerificationOutcome(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    target_mpn: str = Field(min_length=1)
    source_key: str = Field(min_length=1)
    candidate_raw_value: str
    candidate_raw_uom: str
    candidate_value_kind: AttributeValueKind | None = None
    candidate_uom_resolution: UomResolution | None = None
    locator: HtmlEvidenceLocator
    source_label: str = ""
    source_raw_value: str = ""
    source_raw_uom: str = ""
    status: HtmlAttributeVerificationStatus
    reason: HtmlAttributeVerificationReason
    detail: str = ""
    value_verified: bool = False
    uom_claimed: bool = False
    uom_verified: bool = False
    span_verification: EvidenceVerification | None = None
    post_authority: AttributeAuthority = AttributeAuthority.MODEL_PROPOSAL
    post_decision: ClassificationDecision = ClassificationDecision.WITHHOLD
    promoted_fact: VerifiedHtmlAttributeFact | None = None

    @property
    def verified(self) -> bool:
        return self.status is HtmlAttributeVerificationStatus.VERIFIED


def _decode_pointer_token(token: str) -> str:
    if re.search(r"~(?:[^01]|$)", token):
        raise ValueError("invalid JSON pointer escape")
    return token.replace("~1", "/").replace("~0", "~")


def _resolve_pointer(value: Any, pointer: str | None) -> Any:
    if pointer is None or (pointer and not pointer.startswith("/")):
        raise ValueError("JSON pointer is missing or malformed")
    current = value
    if pointer == "":
        return current
    assert pointer is not None
    for raw in pointer[1:].split("/"):
        token = _decode_pointer_token(raw)
        if isinstance(current, dict):
            if token not in current:
                raise ValueError(f"JSON object has no {token!r} member")
            current = current[token]
        elif isinstance(current, list):
            if not token.isdigit() or (len(token) > 1 and token.startswith("0")):
                raise ValueError(f"{token!r} is not a canonical array index")
            index = int(token)
            if index >= len(current):
                raise ValueError(f"array index {index} is out of range")
            current = current[index]
        else:
            raise ValueError("JSON pointer continues beyond a scalar")
    return current


def _source_scalar(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _parse_value(
    kind: AttributeValueKind, raw_value: str, raw_uom: str
) -> UnilogAttributeValue:
    if kind is AttributeValueKind.TEXT:
        return parse_text(raw_value, raw_uom=raw_uom)
    if kind is AttributeValueKind.NUMBER:
        return parse_number(raw_value, raw_uom=raw_uom)
    if kind is AttributeValueKind.RANGE:
        return parse_simple_range(raw_value, raw_uom=raw_uom)
    if kind is AttributeValueKind.ENUM:
        return parse_controlled_value(raw_value, raw_uom=raw_uom)
    if raw_uom:
        raise ValueError("a BOOLEAN source value cannot carry a UOM")
    return parse_boolean(raw_value)


def _candidate_fields(
    bound: SourceBoundHtmlAttributeCandidate,
) -> tuple[str, str, AttributeValueKind | None, UomResolution | None]:
    value = bound.candidate.value
    if value is None:
        return "", "", None, None
    return value.raw_value, value.raw_uom, value.value_kind, value.uom_resolution


def _outcome(
    bound: SourceBoundHtmlAttributeCandidate,
    artifact: HtmlArtifact,
    identity: HtmlIdentityResolution,
    status: HtmlAttributeVerificationStatus,
    reason: HtmlAttributeVerificationReason,
    *,
    detail: str,
    source_label: str = "",
    source_raw_value: str = "",
    source_raw_uom: str = "",
    value_verified: bool = False,
    uom_verified: bool = False,
    span_verification: EvidenceVerification | None = None,
    promoted_fact: VerifiedHtmlAttributeFact | None = None,
) -> HtmlAttributeVerificationOutcome:
    raw_value, raw_uom, kind, resolution = _candidate_fields(bound)
    if status is HtmlAttributeVerificationStatus.VERIFIED:
        authority = AttributeAuthority.MANUFACTURER_EVIDENCE
        decision = ClassificationDecision.COMMIT
    elif status is HtmlAttributeVerificationStatus.REVIEW:
        authority = AttributeAuthority.MODEL_PROPOSAL
        decision = ClassificationDecision.REVIEW
    else:
        authority = AttributeAuthority.MODEL_PROPOSAL
        decision = ClassificationDecision.WITHHOLD
    return HtmlAttributeVerificationOutcome(
        artifact_sha256=artifact.sha256,
        target_mpn=identity.target_mpn,
        source_key=bound.candidate.source_key,
        candidate_raw_value=raw_value,
        candidate_raw_uom=raw_uom,
        candidate_value_kind=kind,
        candidate_uom_resolution=resolution,
        locator=bound.locator,
        source_label=source_label,
        source_raw_value=source_raw_value,
        source_raw_uom=source_raw_uom,
        status=status,
        reason=reason,
        detail=detail,
        value_verified=value_verified,
        uom_claimed=bool(raw_uom),
        uom_verified=uom_verified,
        span_verification=span_verification,
        post_authority=authority,
        post_decision=decision,
        promoted_fact=promoted_fact,
    )


def _primary_product_roots(
    identity: HtmlIdentityResolution,
) -> dict[int, tuple[str, ...]]:
    roots: dict[int, list[str]] = {}
    for observation in identity.observations:
        locator = observation.locator
        if (
            observation.kind is HtmlIdentityObservationKind.PRODUCT_NODE
            and observation.primary_product is True
            and locator is not None
            and locator.kind is SourceFragmentKind.HTML_JSONLD
            and locator.jsonld_block_index is not None
        ):
            roots.setdefault(locator.jsonld_block_index, []).append(locator.json_pointer or "")
    return {block: tuple(values) for block, values in roots.items()}


def _property_address(
    pointer: str | None, roots: tuple[str, ...]
) -> tuple[str, int] | None:
    if pointer is None:
        return None
    for root in roots:
        prefix = f"{root}/additionalProperty/"
        if not pointer.startswith(prefix) or not pointer.endswith("/value"):
            continue
        index_text = pointer[len(prefix) : -len("/value")]
        if index_text.isdigit() and "/" not in index_text:
            return root, int(index_text)
    return None


def _structured_uoms(entry: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        value.strip()
        for key in ("unitText", "unitCode")
        if isinstance((value := entry.get(key)), str) and value.strip()
    )


def _entry_matches_rule(
    entry: dict[str, Any], rule: HtmlAttributeVerificationRule, target_mpn: str
) -> bool:
    if entry.get("name") not in rule.jsonld_property_names:
        return False
    if rule.jsonld_property_id_rule is HtmlPropertyIdRule.TARGET_MPN:
        return mpn_matches(str(entry.get("propertyID", "")), target_mpn)
    return True


def _verify_jsonld(
    bound: SourceBoundHtmlAttributeCandidate,
    artifact: HtmlArtifact,
    identity: HtmlIdentityResolution,
    rule: HtmlAttributeVerificationRule,
) -> HtmlAttributeVerificationOutcome:
    locator = bound.locator
    block_index = locator.jsonld_block_index
    assert block_index is not None
    if block_index >= len(artifact.content.jsonld_blocks):
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.LOCATOR_INVALID,
            detail=f"JSON-LD block {block_index} does not exist",
        )
    block = artifact.content.jsonld_blocks[block_index]
    if block.parsed is None or block.parse_error is not None:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.LOCATOR_INVALID,
            detail="candidate points to an unparsed JSON-LD block",
        )
    address = _property_address(
        locator.json_pointer, _primary_product_roots(identity).get(block_index, ())
    )
    if address is None:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.OUTSIDE_TARGET_PRODUCT,
            detail="locator is not a direct additionalProperty value of the primary Product",
        )
    root_pointer, property_index = address
    try:
        product = _resolve_pointer(block.parsed, root_pointer)
        properties = product["additionalProperty"]
        entry = properties[property_index]
        resolved = _resolve_pointer(block.parsed, locator.json_pointer)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.LOCATOR_INVALID,
            detail=str(exc),
        )
    if (
        not isinstance(product, dict)
        or not isinstance(properties, list)
        or not isinstance(entry, dict)
        or entry.get("@type") != "PropertyValue"
        or not isinstance(entry.get("name"), str)
        or "value" not in entry
    ):
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.MALFORMED_STRUCTURED_PROPERTY,
            detail="enclosing entry is not a complete schema.org PropertyValue",
        )

    source_label = entry["name"]
    source_value = _source_scalar(resolved)
    if source_value != bound.source_excerpt:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.LOCATOR_INVALID,
            detail="source excerpt does not equal the resolved JSON-LD value",
            source_label=source_label,
            source_raw_value=source_value,
        )
    units = _structured_uoms(entry)
    if len(set(units)) > 1:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.MALFORMED_STRUCTURED_PROPERTY,
            detail="unitText and unitCode disagree",
            source_label=source_label,
            source_raw_value=source_value,
        )
    source_uom = units[0] if units else ""

    if source_label not in rule.jsonld_property_names:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.SOURCE_PROPERTY_NOT_AUTHORIZED,
            detail=f"{source_label!r} is not an exact reviewed property alias for this key",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )
    if rule.jsonld_property_id_rule is HtmlPropertyIdRule.TARGET_MPN and not mpn_matches(
        str(entry.get("propertyID", "")), identity.target_mpn
    ):
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.PROPERTY_ID_MISMATCH,
            detail="structured propertyID does not match the exact target MPN",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )

    matching = [
        item
        for item in properties
        if isinstance(item, dict) and _entry_matches_rule(item, rule, identity.target_mpn)
    ]
    distinct = {
        (_source_scalar(item.get("value")), _structured_uoms(item))
        for item in matching
        if "value" in item
    }
    if len(distinct) > 1:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.REVIEW,
            HtmlAttributeVerificationReason.CONFLICTING_PROPERTY_VALUES,
            detail=f"primary Product carries {len(distinct)} conflicting values",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )

    candidate_value = bound.candidate.value
    if candidate_value is None:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.VALUE_NOT_SUPPORTED,
            detail="candidate has no value",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )
    if source_uom and not candidate_value.raw_uom:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.UOM_NOT_SUPPORTED,
            detail="candidate omitted the structured property's explicit UOM",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )
    if candidate_value.raw_uom:
        if source_uom:
            if candidate_value.raw_uom != source_uom:
                return _outcome(
                    bound,
                    artifact,
                    identity,
                    HtmlAttributeVerificationStatus.UNVERIFIED,
                    HtmlAttributeVerificationReason.UOM_NOT_SUPPORTED,
                    detail="candidate UOM is not the structured property UOM",
                    source_label=source_label,
                    source_raw_value=source_value,
                    source_raw_uom=source_uom,
                )
        else:
            combined = re.fullmatch(
                re.escape(candidate_value.raw_value)
                + r"\s+"
                + re.escape(candidate_value.raw_uom),
                source_value,
            )
            if combined is None:
                return _outcome(
                    bound,
                    artifact,
                    identity,
                    HtmlAttributeVerificationStatus.UNVERIFIED,
                    HtmlAttributeVerificationReason.UOM_NOT_SUPPORTED,
                    detail="candidate UOM is absent from the structured property",
                    source_label=source_label,
                    source_raw_value=source_value,
                )
            source_value = candidate_value.raw_value
            source_uom = candidate_value.raw_uom

    try:
        parsed_source = _parse_value(candidate_value.value_kind, source_value, source_uom)
    except ValueError as exc:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.VALUE_NOT_SUPPORTED,
            detail=f"structured source value does not parse deterministically: {exc}",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )
    if parsed_source.semantic_key() != candidate_value.semantic_key():
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.VALUE_NOT_SUPPORTED,
            detail="candidate normalized value differs from the structured source value",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )
    return _verified(
        bound,
        artifact,
        identity,
        source_label=source_label,
        source_raw_value=source_value,
        source_raw_uom=source_uom,
        span_verification=None,
    )


def _verify_text(
    bound: SourceBoundHtmlAttributeCandidate,
    artifact: HtmlArtifact,
    identity: HtmlIdentityResolution,
    rule: HtmlAttributeVerificationRule,
) -> HtmlAttributeVerificationOutcome:
    fragment = next(
        (
            item
            for item in artifact.content.text_fragments
            if item.locator == bound.locator
        ),
        None,
    )
    if fragment is None or fragment.text != bound.source_excerpt:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.LOCATOR_INVALID,
            detail="text locator/excerpt does not name one exact stored fragment",
        )
    matches = [
        label
        for label in rule.html_text_labels
        if fragment.text.startswith(f"{label}:")
    ]
    occurrence_count = sum(fragment.text.count(f"{label}:") for label in rule.html_text_labels)
    if occurrence_count > 1 or len(matches) > 1:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.AMBIGUOUS_TEXT_FRAGMENT,
            detail="fragment contains more than one configured label/value structure",
        )
    if len(matches) != 1:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.EXPECTED_LABEL_MISSING,
            detail="fragment does not begin with an exact reviewed label and colon",
        )
    source_label = matches[0]
    remainder = fragment.text[len(source_label) + 1 :].strip()
    candidate_value = bound.candidate.value
    if candidate_value is None:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.VALUE_NOT_SUPPORTED,
            detail="candidate has no value",
            source_label=source_label,
            source_raw_value=remainder,
        )
    source_value = remainder
    source_uom = ""
    if candidate_value.raw_uom:
        if re.fullmatch(
            re.escape(candidate_value.raw_value)
            + r"\s+"
            + re.escape(candidate_value.raw_uom),
            remainder,
        ) is None:
            return _outcome(
                bound,
                artifact,
                identity,
                HtmlAttributeVerificationStatus.UNVERIFIED,
                HtmlAttributeVerificationReason.UOM_NOT_SUPPORTED,
                detail="candidate value/UOM pair is not the complete labeled source value",
                source_label=source_label,
                source_raw_value=remainder,
            )
        source_value = candidate_value.raw_value
        source_uom = candidate_value.raw_uom
    try:
        parsed_source = _parse_value(candidate_value.value_kind, source_value, source_uom)
    except ValueError as exc:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.VALUE_NOT_SUPPORTED,
            detail=f"labeled source value does not parse deterministically: {exc}",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )
    if parsed_source.semantic_key() != candidate_value.semantic_key():
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.VALUE_NOT_SUPPORTED,
            detail="candidate normalized value differs from the labeled source value",
            source_label=source_label,
            source_raw_value=source_value,
            source_raw_uom=source_uom,
        )
    return _verified(
        bound,
        artifact,
        identity,
        source_label=source_label,
        source_raw_value=source_value,
        source_raw_uom=source_uom,
        span_verification=EvidenceVerification.EXACT_SPAN,
    )


def _verified(
    bound: SourceBoundHtmlAttributeCandidate,
    artifact: HtmlArtifact,
    identity: HtmlIdentityResolution,
    *,
    source_label: str,
    source_raw_value: str,
    source_raw_uom: str,
    span_verification: EvidenceVerification | None,
) -> HtmlAttributeVerificationOutcome:
    candidate = bound.candidate
    assert candidate.value is not None
    fact = VerifiedHtmlAttributeFact(
        artifact_sha256=artifact.sha256,
        target_mpn=identity.target_mpn,
        source_key=candidate.source_key,
        label=candidate.label,
        raw_value=candidate.value.raw_value,
        raw_uom=candidate.value.raw_uom,
        normalized_value=candidate.value.delivery_value(),
        normalized_uom=candidate.value.normalized_uom,
        locator=bound.locator,
        source_label=source_label,
        source_raw_value=source_raw_value,
        source_raw_uom=source_raw_uom,
    )
    return _outcome(
        bound,
        artifact,
        identity,
        HtmlAttributeVerificationStatus.VERIFIED,
        HtmlAttributeVerificationReason.FACT_VERIFIED,
        detail="exact configured attribute/value relationship is supported",
        source_label=source_label,
        source_raw_value=source_raw_value,
        source_raw_uom=source_raw_uom,
        value_verified=True,
        uom_verified=bool(candidate.value.raw_uom),
        span_verification=span_verification,
        promoted_fact=fact,
    )


def verify_html_attribute_candidate(
    bound: SourceBoundHtmlAttributeCandidate,
    *,
    artifact: HtmlArtifact,
    identity: HtmlIdentityResolution,
    profile: HtmlAttributeVerificationProfile = HTML_ATTRIBUTE_VERIFICATION_PROFILE,
) -> HtmlAttributeVerificationOutcome:
    """Verify one HTML attribute relationship without any model or network access."""
    if (
        identity.decision is not HtmlIdentityDecision.EXACT
        or identity.identity_scope is not IdentityScope.EXACT_SKU
        or not mpn_matches(identity.covers_mpn, identity.target_mpn)
    ):
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.IDENTITY_NOT_EXACT,
            detail="verification requires EXACT / EXACT_SKU identity and covers_mpn",
        )
    if identity.artifact_sha256 != artifact.sha256:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.ARTIFACT_MISMATCH,
            detail="identity and supplied artifact SHA-256 differ",
        )
    if artifact.final_authority != SourceAuthority.APPROVED_MANUFACTURER.value:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.MANUFACTURER_AUTHORITY_REQUIRED,
            detail="stored source lacks APPROVED_MANUFACTURER authority",
        )
    rule = profile.rule(bound.candidate.source_key)
    if rule is None:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.UNKNOWN_SOURCE_KEY,
            detail="source_key is not in the local HTML verification profile",
        )
    candidate_value = bound.candidate.value
    concept = HTML_ATTRIBUTE_PROFILE.concept(rule.source_key)
    if candidate_value is None or candidate_value.value_kind is not concept.value_kind:
        return _outcome(
            bound,
            artifact,
            identity,
            HtmlAttributeVerificationStatus.UNVERIFIED,
            HtmlAttributeVerificationReason.VALUE_NOT_SUPPORTED,
            detail="candidate value kind does not match the fixed extraction concept",
        )
    if bound.locator.kind is SourceFragmentKind.HTML_JSONLD:
        return _verify_jsonld(bound, artifact, identity, rule)
    if bound.locator.kind is SourceFragmentKind.HTML_TEXT:
        return _verify_text(bound, artifact, identity, rule)
    return _outcome(
        bound,
        artifact,
        identity,
        HtmlAttributeVerificationStatus.UNVERIFIED,
        HtmlAttributeVerificationReason.UNSUPPORTED_EVIDENCE_KIND,
        detail="HTML verification accepts only HTML_JSONLD and HTML_TEXT",
    )


__all__ = [
    "HTML_ATTRIBUTE_VERIFICATION_PROFILE",
    "HtmlAttributeVerificationOutcome",
    "HtmlAttributeVerificationProfile",
    "HtmlAttributeVerificationReason",
    "HtmlAttributeVerificationRule",
    "HtmlAttributeVerificationStatus",
    "HtmlPropertyIdRule",
    "HtmlUnilogMappingStatus",
    "HtmlVerificationProfileAuthority",
    "VerifiedHtmlAttributeFact",
    "verify_html_attribute_candidate",
]
