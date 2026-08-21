"""Deterministic product-identity observations from one stored HTML artifact.

Search relevance is deliberately absent from this module.  A search result may license a
fetch, but only the stored artifact can establish what product the fetched bytes describe.
This adapter scopes primary Product JSON-LD conservatively, turns an admissible direct
``mpn`` observation into the existing typed identity evidence, and delegates the final
EXACT decision to the frozen resolver.

The returned record is derived and immutable.  Resolving identity never rewrites the
artifact or its ArtifactStore files.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import IdentityDisposition, IdentityScope, ProductInput
from skutruth.contracts.mpn import canonical_mpn, mpn_matches
from skutruth.discovery.models import SourceAuthority
from skutruth.ingest.html import HtmlArtifact, HtmlEvidenceLocator
from skutruth.ingest.models import ArtifactKind, SourceFragmentKind

from .evidence import (
    EvidenceAnchor,
    ExactReferenceFact,
    IdentityEvidence,
    brands_match,
)
from .models import IdentityResolution
from .resolver import resolve_identity


class HtmlIdentityDecision(StrEnum):
    """Fail-closed disposition at the HTML adapter boundary."""

    EXACT = "EXACT"
    REVIEW = "REVIEW"
    WITHHOLD = "WITHHOLD"


class HtmlIdentityReason(StrEnum):
    """The typed rule that determined an HTML identity decision."""

    EXACT_PRODUCT_MPN = "EXACT_PRODUCT_MPN"
    INVALID_TARGET_MPN = "INVALID_TARGET_MPN"
    MANUFACTURER_AUTHORITY_REQUIRED = "MANUFACTURER_AUTHORITY_REQUIRED"
    PUBLISHER_MISMATCH = "PUBLISHER_MISMATCH"
    MALFORMED_JSONLD = "MALFORMED_JSONLD"
    NO_PRODUCT_IDENTITY_STRUCTURE = "NO_PRODUCT_IDENTITY_STRUCTURE"
    CONFLICTING_PRODUCT_MPN = "CONFLICTING_PRODUCT_MPN"
    MULTIPLE_PRODUCTS_AMBIGUOUS = "MULTIPLE_PRODUCTS_AMBIGUOUS"
    PRODUCT_MPN_MISMATCH = "PRODUCT_MPN_MISMATCH"
    TARGET_ONLY_IN_NONPRIMARY_PRODUCT = "TARGET_ONLY_IN_NONPRIMARY_PRODUCT"
    MPN_ONLY_IN_VISIBLE_TEXT = "MPN_ONLY_IN_VISIBLE_TEXT"
    MPN_ONLY_IN_TITLE = "MPN_ONLY_IN_TITLE"
    MPN_ONLY_IN_URL = "MPN_ONLY_IN_URL"
    MPN_ABSENT = "MPN_ABSENT"


class HtmlIdentityObservationKind(StrEnum):
    """Mechanically inspectable source observations; none is model-generated."""

    PRODUCT_NODE = "PRODUCT_NODE"
    PRODUCT_MPN = "PRODUCT_MPN"
    PRODUCT_SKU = "PRODUCT_SKU"
    NONPRIMARY_PRODUCT_MPN = "NONPRIMARY_PRODUCT_MPN"
    VISIBLE_TEXT = "VISIBLE_TEXT"
    DOCUMENT_TITLE = "DOCUMENT_TITLE"
    CANONICAL_URL = "CANONICAL_URL"
    MALFORMED_JSONLD = "MALFORMED_JSONLD"


class HtmlIdentityWarning(StrEnum):
    """Non-blocking structured observations retained beside an exact decision."""

    SKU_DOES_NOT_CORROBORATE_MPN = "SKU_DOES_NOT_CORROBORATE_MPN"
    DUPLICATE_EQUIVALENT_PRODUCT_NODES = "DUPLICATE_EQUIVALENT_PRODUCT_NODES"


class HtmlIdentityObservation(BaseModel):
    """One artifact-local identity observation and its source address, where available."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: HtmlIdentityObservationKind
    observed: str = Field(min_length=1)
    canonical: str | None = None
    locator: HtmlEvidenceLocator | None = None
    primary_product: bool | None = None


class HtmlIdentityResolution(BaseModel):
    """Derived HTML identity annotation; the stored artifact remains unchanged."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target_mpn: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_kind: ArtifactKind = ArtifactKind.HTML
    decision: HtmlIdentityDecision
    identity_scope: IdentityScope | None = None
    covers_mpn: str | None = None
    reason: HtmlIdentityReason
    observations: tuple[HtmlIdentityObservation, ...] = ()
    warnings: tuple[HtmlIdentityWarning, ...] = ()
    identity_resolution: IdentityResolution

    @model_validator(mode="after")
    def _exact_fields_move_together(self) -> HtmlIdentityResolution:
        if self.artifact_kind is not ArtifactKind.HTML:
            raise ValueError("HtmlIdentityResolution can annotate only an HTML artifact")
        if self.decision is HtmlIdentityDecision.EXACT:
            if self.identity_scope is not IdentityScope.EXACT_SKU:
                raise ValueError("an EXACT HTML identity requires EXACT_SKU scope")
            if not mpn_matches(self.covers_mpn, self.target_mpn):
                raise ValueError("an EXACT HTML identity must cover the target MPN")
            if self.identity_resolution.disposition is not IdentityDisposition.EXACT:
                raise ValueError("an EXACT HTML decision requires an EXACT frozen resolution")
            if not mpn_matches(self.identity_resolution.exact_mpn, self.target_mpn):
                raise ValueError("the frozen exact resolution must name the HTML target MPN")
        else:
            if self.identity_scope is not None or self.covers_mpn is not None:
                raise ValueError("a non-exact HTML identity cannot claim artifact scope")
            if self.identity_resolution.disposition is IdentityDisposition.EXACT:
                raise ValueError("a non-exact HTML decision cannot carry an EXACT resolution")
        return self


@dataclass(frozen=True, slots=True)
class _ProductNode:
    block_index: int
    pointer: str
    value: dict[str, Any]
    primary: bool


def _pointer_token(value: object) -> str:
    return str(value).replace("~", "~0").replace("/", "~1")


def _child_pointer(pointer: str, child: object) -> str:
    return f"{pointer}/{_pointer_token(child)}"


def _is_product(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    declared = value.get("@type")
    types = declared if isinstance(declared, list) else [declared]
    return any(str(item).casefold() == "product" for item in types if item is not None)


def _direct_products(value: object, pointer: str) -> list[tuple[str, dict[str, Any]]]:
    """Product objects at exactly this structural level, never recursive descendants."""
    if _is_product(value):
        return [(pointer, value)]  # type: ignore[list-item]
    if isinstance(value, list):
        return [
            (_child_pointer(pointer, index), item)
            for index, item in enumerate(value)
            if _is_product(item)
        ]
    return []


def _main_entity_ids(value: object) -> set[str]:
    entities = value if isinstance(value, list) else [value]
    return {
        item["@id"]
        for item in entities
        if isinstance(item, dict) and isinstance(item.get("@id"), str)
    }


def _primary_products(value: object) -> list[tuple[str, dict[str, Any]]]:
    """Find only roots that the document structure can defend as page-level products.

    A root Product is primary.  A WebPage's embedded ``mainEntity`` is primary.  A
    ``mainEntity`` @id may select a direct Product in ``@graph``.  Without that explicit
    selection, direct graph Products are peers and ambiguity is preserved.  Recursive
    Product descendants such as recommendations and accessories are never promoted.
    """
    roots = _direct_products(value, "")
    if roots or not isinstance(value, dict):
        return roots

    main_entity = value.get("mainEntity")
    embedded = _direct_products(main_entity, "/mainEntity")
    if embedded:
        return embedded

    graph = value.get("@graph")
    graph_products = _direct_products(graph, "/@graph")
    ids = _main_entity_ids(main_entity)
    if ids:
        selected = [
            (pointer, product)
            for pointer, product in graph_products
            if isinstance(product.get("@id"), str) and product["@id"] in ids
        ]
        if selected:
            return selected
    return graph_products


def _walk_products(value: object, pointer: str = "") -> list[tuple[str, dict[str, Any]]]:
    found: list[tuple[str, dict[str, Any]]] = []
    if _is_product(value):
        found.append((pointer, value))  # type: ignore[arg-type]
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(_walk_products(child, _child_pointer(pointer, key)))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_walk_products(child, _child_pointer(pointer, index)))
    return found


def _jsonld_locator(block_index: int, pointer: str) -> HtmlEvidenceLocator:
    return HtmlEvidenceLocator(
        kind=SourceFragmentKind.HTML_JSONLD,
        jsonld_block_index=block_index,
        json_pointer=pointer,
    )


def _scalar_identity_values(value: object) -> tuple[tuple[str, str], ...]:
    """Return source string plus JSON-pointer suffix; numeric identifiers stay unsafe."""
    if isinstance(value, str) and value.strip():
        return ((value, ""),)
    if isinstance(value, list):
        return tuple(
            (item, f"/{index}")
            for index, item in enumerate(value)
            if isinstance(item, str) and item.strip()
        )
    return ()


def _target_pattern(target: str) -> re.Pattern[str]:
    # canonical_mpn removes whitespace only, so the source may contain whitespace between
    # any two canonical characters.  Punctuation is escaped and therefore never folded.
    body = r"\s*".join(re.escape(character) for character in target)
    return re.compile(rf"(?<![A-Za-z0-9])({body})(?![A-Za-z0-9])", re.IGNORECASE)


def _signal_observations(
    artifact: HtmlArtifact, target: str
) -> tuple[HtmlIdentityObservation, ...]:
    observations: list[HtmlIdentityObservation] = []
    pattern = _target_pattern(target)
    for fragment in artifact.content.text_fragments:
        match = pattern.search(fragment.text)
        if match is None:
            continue
        base = fragment.locator.char_start or 0
        observations.append(
            HtmlIdentityObservation(
                kind=HtmlIdentityObservationKind.VISIBLE_TEXT,
                observed=match.group(1),
                canonical=canonical_mpn(match.group(1)),
                locator=HtmlEvidenceLocator(
                    kind=SourceFragmentKind.HTML_TEXT,
                    element_index=fragment.locator.element_index,
                    char_start=base + match.start(1),
                    char_end=base + match.end(1),
                ),
            )
        )

    for kind, text in (
        (HtmlIdentityObservationKind.DOCUMENT_TITLE, artifact.content.title),
        (HtmlIdentityObservationKind.CANONICAL_URL, artifact.content.canonical_url),
    ):
        if not text:
            continue
        match = pattern.search(text)
        if match is not None:
            observations.append(
                HtmlIdentityObservation(
                    kind=kind,
                    observed=match.group(1),
                    canonical=canonical_mpn(match.group(1)),
                )
            )
    return tuple(observations)


def _structured_observations(
    artifact: HtmlArtifact,
) -> tuple[
    tuple[_ProductNode, ...],
    tuple[HtmlIdentityObservation, ...],
    bool,
]:
    nodes: list[_ProductNode] = []
    observations: list[HtmlIdentityObservation] = []
    malformed = False

    for block_index, block in enumerate(artifact.content.jsonld_blocks):
        if block.parse_error is not None:
            malformed = True
            observations.append(
                HtmlIdentityObservation(
                    kind=HtmlIdentityObservationKind.MALFORMED_JSONLD,
                    observed=block.parse_error,
                    locator=block.locator,
                )
            )
            continue

        primary = _primary_products(block.parsed)
        primary_keys = {(block_index, pointer) for pointer, _value in primary}
        for pointer, value in _walk_products(block.parsed):
            node = _ProductNode(
                block_index=block_index,
                pointer=pointer,
                value=value,
                primary=(block_index, pointer) in primary_keys,
            )
            nodes.append(node)
            observations.append(
                HtmlIdentityObservation(
                    kind=HtmlIdentityObservationKind.PRODUCT_NODE,
                    observed="Product",
                    locator=_jsonld_locator(block_index, pointer),
                    primary_product=node.primary,
                )
            )
            for field, kind in (
                ("mpn", HtmlIdentityObservationKind.PRODUCT_MPN),
                ("sku", HtmlIdentityObservationKind.PRODUCT_SKU),
            ):
                for observed, suffix in _scalar_identity_values(value.get(field)):
                    observation_kind = kind
                    if field == "mpn" and not node.primary:
                        observation_kind = HtmlIdentityObservationKind.NONPRIMARY_PRODUCT_MPN
                    observations.append(
                        HtmlIdentityObservation(
                            kind=observation_kind,
                            observed=observed,
                            canonical=canonical_mpn(observed),
                            locator=_jsonld_locator(
                                block_index, f"{pointer}/{field}{suffix}"
                            ),
                            primary_product=node.primary,
                        )
                    )
    return tuple(nodes), tuple(observations), malformed


def _empty_resolution(product: ProductInput) -> IdentityResolution:
    return resolve_identity(product, IdentityEvidence())


def _withhold(
    *,
    artifact: HtmlArtifact,
    product: ProductInput,
    target: str,
    reason: HtmlIdentityReason,
    observations: tuple[HtmlIdentityObservation, ...],
    decision: HtmlIdentityDecision = HtmlIdentityDecision.WITHHOLD,
) -> HtmlIdentityResolution:
    return HtmlIdentityResolution(
        target_mpn=target,
        artifact_sha256=artifact.sha256,
        decision=decision,
        reason=reason,
        observations=observations,
        identity_resolution=_empty_resolution(product),
    )


def _fallback_reason(observations: tuple[HtmlIdentityObservation, ...]) -> HtmlIdentityReason:
    kinds = {observation.kind for observation in observations}
    if HtmlIdentityObservationKind.VISIBLE_TEXT in kinds:
        return HtmlIdentityReason.MPN_ONLY_IN_VISIBLE_TEXT
    if HtmlIdentityObservationKind.DOCUMENT_TITLE in kinds:
        return HtmlIdentityReason.MPN_ONLY_IN_TITLE
    if HtmlIdentityObservationKind.CANONICAL_URL in kinds:
        return HtmlIdentityReason.MPN_ONLY_IN_URL
    return HtmlIdentityReason.MPN_ABSENT


def resolve_html_product_identity(
    artifact: HtmlArtifact,
    product: ProductInput,
) -> HtmlIdentityResolution:
    """Resolve one target against the stored HTML representation, without mutation.

    Exactness requires a direct ``mpn`` on a deterministically primary Product JSON-LD
    node.  A matching ``sku``, visible-text fragment, document title, or canonical URL is
    retained as corroboration only.  Search-result fields are structurally impossible to
    pass to this function.
    """
    if not isinstance(artifact, HtmlArtifact):
        raise TypeError("HTML identity resolution requires a HtmlArtifact")

    target = canonical_mpn(product.mpn)
    if target is None:
        return _withhold(
            artifact=artifact,
            product=product,
            target=product.mpn,
            reason=HtmlIdentityReason.INVALID_TARGET_MPN,
            observations=(),
        )

    nodes, structured, malformed = _structured_observations(artifact)
    signals = _signal_observations(artifact, target)
    observations = (*structured, *signals)

    if artifact.final_authority != SourceAuthority.APPROVED_MANUFACTURER.value:
        return _withhold(
            artifact=artifact,
            product=product,
            target=target,
            reason=HtmlIdentityReason.MANUFACTURER_AUTHORITY_REQUIRED,
            observations=observations,
        )
    if not brands_match(product.brand, artifact.source.publisher):
        return _withhold(
            artifact=artifact,
            product=product,
            target=target,
            reason=HtmlIdentityReason.PUBLISHER_MISMATCH,
            observations=observations,
        )
    if malformed:
        return _withhold(
            artifact=artifact,
            product=product,
            target=target,
            reason=HtmlIdentityReason.MALFORMED_JSONLD,
            observations=observations,
        )

    primary_nodes = tuple(node for node in nodes if node.primary)
    nonprimary_target = any(
        observation.kind is HtmlIdentityObservationKind.NONPRIMARY_PRODUCT_MPN
        and mpn_matches(observation.observed, target)
        for observation in observations
    )
    if not primary_nodes:
        reason = (
            HtmlIdentityReason.TARGET_ONLY_IN_NONPRIMARY_PRODUCT
            if nonprimary_target
            else (
                _fallback_reason(observations)
                if signals
                else HtmlIdentityReason.NO_PRODUCT_IDENTITY_STRUCTURE
            )
        )
        return _withhold(
            artifact=artifact,
            product=product,
            target=target,
            reason=reason,
            observations=observations,
        )

    primary_mpn = tuple(
        observation
        for observation in observations
        if observation.kind is HtmlIdentityObservationKind.PRODUCT_MPN
        and observation.primary_product
    )
    primary_by_node = {
        (node.block_index, node.pointer): tuple(
            observation
            for observation in primary_mpn
            if observation.locator is not None
            and observation.locator.jsonld_block_index == node.block_index
            and (observation.locator.json_pointer or "").startswith(f"{node.pointer}/mpn")
        )
        for node in primary_nodes
    }
    canonical_values = {
        observation.canonical for observation in primary_mpn if observation.canonical is not None
    }

    if len(canonical_values) > 1:
        return _withhold(
            artifact=artifact,
            product=product,
            target=target,
            reason=HtmlIdentityReason.CONFLICTING_PRODUCT_MPN,
            observations=observations,
            decision=HtmlIdentityDecision.REVIEW,
        )
    if len(primary_nodes) > 1 and any(not values for values in primary_by_node.values()):
        return _withhold(
            artifact=artifact,
            product=product,
            target=target,
            reason=HtmlIdentityReason.MULTIPLE_PRODUCTS_AMBIGUOUS,
            observations=observations,
            decision=HtmlIdentityDecision.REVIEW,
        )
    if target not in canonical_values:
        reason = (
            HtmlIdentityReason.TARGET_ONLY_IN_NONPRIMARY_PRODUCT
            if nonprimary_target
            else (
                HtmlIdentityReason.PRODUCT_MPN_MISMATCH
                if canonical_values
                else _fallback_reason(observations)
            )
        )
        return _withhold(
            artifact=artifact,
            product=product,
            target=target,
            reason=reason,
            observations=observations,
        )

    exact_observation = next(
        observation for observation in primary_mpn if observation.canonical == target
    )
    anchor = EvidenceAnchor(
        artifact_sha256=artifact.sha256,
        publisher=artifact.source.publisher,
        identity_scope=IdentityScope.EXACT_SKU,
        observed_statement=f"Primary Product JSON-LD mpn is {exact_observation.observed}",
    )
    fact = ExactReferenceFact(
        brand=product.brand,
        exact_mpn=exact_observation.observed,
        anchor=anchor,
    )
    frozen = resolve_identity(product, IdentityEvidence(exact_facts=(fact,)))

    warnings: list[HtmlIdentityWarning] = []
    sku_values = {
        observation.canonical
        for observation in observations
        if observation.kind is HtmlIdentityObservationKind.PRODUCT_SKU
        and observation.primary_product
        and observation.canonical is not None
    }
    if sku_values and target not in sku_values:
        warnings.append(HtmlIdentityWarning.SKU_DOES_NOT_CORROBORATE_MPN)
    if len(primary_nodes) > 1:
        warnings.append(HtmlIdentityWarning.DUPLICATE_EQUIVALENT_PRODUCT_NODES)

    return HtmlIdentityResolution(
        target_mpn=target,
        artifact_sha256=artifact.sha256,
        decision=HtmlIdentityDecision.EXACT,
        identity_scope=IdentityScope.EXACT_SKU,
        covers_mpn=frozen.exact_mpn,
        reason=HtmlIdentityReason.EXACT_PRODUCT_MPN,
        observations=observations,
        warnings=tuple(warnings),
        identity_resolution=frozen,
    )


__all__ = [
    "HtmlIdentityDecision",
    "HtmlIdentityObservation",
    "HtmlIdentityObservationKind",
    "HtmlIdentityReason",
    "HtmlIdentityResolution",
    "HtmlIdentityWarning",
    "resolve_html_product_identity",
]
