"""Stored-HTML identity resolution, using only synthetic network-free snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest
from conftest_pdf import datasheet_pdf
from skutruth.contracts import (
    DiscoveryMethod,
    IdentityDisposition,
    IdentityScope,
    ProductInput,
    SourceType,
)
from skutruth.identity import (
    HtmlIdentityDecision,
    HtmlIdentityObservationKind,
    HtmlIdentityReason,
    HtmlIdentityWarning,
    resolve_html_product_identity,
)
from skutruth.ingest import SourceMetadata, ingest_html_bytes, ingest_pdf_bytes

BRAND = "TestCo"
TARGET = "TEST100A"
SIBLING = "TEST100B"
NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def product(mpn: str = TARGET, brand: str = BRAND) -> ProductInput:
    return ProductInput(brand=brand, mpn=mpn, description="Synthetic product")


def artifact(
    *,
    blocks: tuple[object, ...] = (),
    raw_blocks: tuple[str, ...] = (),
    visible: str = "",
    title: str | None = None,
    canonical_url: str | None = None,
    authority: str | None = "APPROVED_MANUFACTURER",
    publisher: str | None = BRAND,
    discovery_url: str = "https://manufacturer.invalid/search-result",
):
    head = [f"<title>{title}</title>" if title else ""]
    if canonical_url:
        head.append(f'<link rel="canonical" href="{canonical_url}">')
    head.extend(
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
        for block in blocks
    )
    head.extend(
        f'<script type="application/ld+json">{raw}</script>' for raw in raw_blocks
    )
    data = (
        "<!doctype html><html><head>"
        + "".join(head)
        + "</head><body><main>"
        + visible
        + "</main></body></html>"
    ).encode()
    source = SourceMetadata(
        publisher=publisher,
        final_artifact_url="https://manufacturer.invalid/product",
        discovery_url=discovery_url,
        discovery_method=DiscoveryMethod.SITE_RESTRICTED_SEARCH,
        source_type=SourceType.MANUFACTURER_PAGE,
        retrieved_at=NOW,
    )
    return ingest_html_bytes(
        data,
        media_type="text/html",
        source=source,
        final_authority=authority,
        ingested_at=NOW,
    )


def product_node(mpn: object = TARGET, *, sku: object = TARGET, **extra):
    return {"@context": "https://schema.org", "@type": "Product", "mpn": mpn, "sku": sku} | extra


def kinds(result):
    return {observation.kind for observation in result.observations}


def test_primary_product_mpn_and_visible_text_resolve_exactly_without_mutating_artifact():
    stored = artifact(blocks=(product_node(),), visible=f"Model {TARGET}")
    before = stored.model_dump(mode="json")

    result = resolve_html_product_identity(stored, product())

    assert result.decision is HtmlIdentityDecision.EXACT
    assert result.reason is HtmlIdentityReason.EXACT_PRODUCT_MPN
    assert result.identity_scope is IdentityScope.EXACT_SKU
    assert result.covers_mpn == TARGET
    assert result.identity_resolution.disposition is IdentityDisposition.EXACT
    assert stored.model_dump(mode="json") == before

    mpn = next(
        observation
        for observation in result.observations
        if observation.kind is HtmlIdentityObservationKind.PRODUCT_MPN
    )
    assert mpn.locator is not None
    assert mpn.locator.jsonld_block_index == 0
    assert mpn.locator.json_pointer == "/mpn"
    visible = next(
        observation
        for observation in result.observations
        if observation.kind is HtmlIdentityObservationKind.VISIBLE_TEXT
    )
    assert visible.locator is not None
    assert visible.locator.element_index is not None
    assert stored.content.visible_text[
        visible.locator.char_start : visible.locator.char_end
    ] == TARGET


def test_different_primary_product_mpn_is_withheld():
    result = resolve_html_product_identity(
        artifact(blocks=(product_node(SIBLING, sku=SIBLING),)), product()
    )
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.PRODUCT_MPN_MISMATCH
    assert result.identity_scope is None
    assert result.covers_mpn is None


def test_different_direct_sku_is_reported_but_does_not_override_matching_mpn():
    result = resolve_html_product_identity(
        artifact(blocks=(product_node(TARGET, sku="INTERNAL-42"),)), product()
    )
    assert result.decision is HtmlIdentityDecision.EXACT
    assert result.warnings == (HtmlIdentityWarning.SKU_DOES_NOT_CORROBORATE_MPN,)


@pytest.mark.parametrize(
    ("kwargs", "reason"),
    [
        ({"visible": f"Model {TARGET}"}, HtmlIdentityReason.MPN_ONLY_IN_VISIBLE_TEXT),
        (
            {"canonical_url": f"https://manufacturer.invalid/products/{TARGET.lower()}"},
            HtmlIdentityReason.MPN_ONLY_IN_URL,
        ),
        ({"title": f"Fixture {TARGET}"}, HtmlIdentityReason.MPN_ONLY_IN_TITLE),
    ],
)
def test_unstructured_or_metadata_match_alone_never_grants_exact(kwargs, reason):
    result = resolve_html_product_identity(artifact(**kwargs), product())
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is reason
    assert result.identity_resolution.disposition is IdentityDisposition.UNKNOWN


def test_conflicting_primary_product_objects_require_review():
    result = resolve_html_product_identity(
        artifact(blocks=([product_node(TARGET), product_node(SIBLING)],)), product()
    )
    assert result.decision is HtmlIdentityDecision.REVIEW
    assert result.reason is HtmlIdentityReason.CONFLICTING_PRODUCT_MPN
    assert result.identity_scope is None


def test_primary_product_can_ignore_a_nested_recommendation_for_a_sibling():
    primary = product_node(
        TARGET,
        isRelatedTo={"@type": "Product", "mpn": SIBLING, "sku": SIBLING},
    )
    result = resolve_html_product_identity(artifact(blocks=(primary,)), product())
    assert result.decision is HtmlIdentityDecision.EXACT
    assert any(
        observation.kind is HtmlIdentityObservationKind.NONPRIMARY_PRODUCT_MPN
        and observation.observed == SIBLING
        for observation in result.observations
    )


def test_target_only_in_nested_recommendation_is_not_primary_identity():
    primary = product_node(
        SIBLING,
        isRelatedTo={"@type": "Product", "mpn": TARGET, "sku": TARGET},
    )
    result = resolve_html_product_identity(artifact(blocks=(primary,)), product())
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.TARGET_ONLY_IN_NONPRIMARY_PRODUCT


def test_malformed_jsonld_fails_closed_without_guessing():
    result = resolve_html_product_identity(
        artifact(
            blocks=(product_node(),),
            raw_blocks=('{"@type":"Product","mpn": broken}',),
        ),
        product(),
    )
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.MALFORMED_JSONLD
    assert HtmlIdentityObservationKind.MALFORMED_JSONLD in kinds(result)


def test_no_product_structure_is_insufficient_identity_evidence():
    result = resolve_html_product_identity(
        artifact(blocks=({"@type": "WebSite", "name": "Fixture"},)), product()
    )
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.NO_PRODUCT_IDENTITY_STRUCTURE


def test_case_and_whitespace_differences_use_frozen_canonical_mpn():
    result = resolve_html_product_identity(
        artifact(blocks=(product_node(" test 100 a ", sku="TEST100A"),)),
        product("test100a"),
    )
    assert result.decision is HtmlIdentityDecision.EXACT
    assert result.covers_mpn == TARGET


def test_punctuation_difference_is_not_fuzzy_matched():
    result = resolve_html_product_identity(
        artifact(blocks=(product_node("TEST-100A", sku="TEST-100A"),)), product()
    )
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.PRODUCT_MPN_MISMATCH


def test_sibling_mpn_is_not_the_target():
    result = resolve_html_product_identity(
        artifact(blocks=(product_node(SIBLING, sku=SIBLING),), visible=TARGET), product()
    )
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.PRODUCT_MPN_MISMATCH


def test_manufacturer_authority_is_required_even_for_an_identical_match():
    result = resolve_html_product_identity(
        artifact(blocks=(product_node(),), authority="UNKNOWN"), product()
    )
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.MANUFACTURER_AUTHORITY_REQUIRED
    assert result.identity_resolution.disposition is IdentityDisposition.UNKNOWN


def test_stored_publisher_must_match_the_requested_brand():
    result = resolve_html_product_identity(
        artifact(blocks=(product_node(),), publisher="OtherCo"), product()
    )
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.PUBLISHER_MISMATCH


def test_offer_sku_is_not_promoted_to_primary_product_mpn():
    result = resolve_html_product_identity(
        artifact(
            blocks=(
                product_node(
                    SIBLING,
                    sku=SIBLING,
                    offers={"@type": "Offer", "sku": TARGET},
                ),
            )
        ),
        product(),
    )
    assert result.decision is HtmlIdentityDecision.WITHHOLD
    assert result.reason is HtmlIdentityReason.PRODUCT_MPN_MISMATCH


def test_discovery_locator_is_never_artifact_identity_evidence():
    result = resolve_html_product_identity(
        artifact(discovery_url=f"https://search.invalid/result/{TARGET}"), product()
    )
    assert result.reason is HtmlIdentityReason.NO_PRODUCT_IDENTITY_STRUCTURE
    assert HtmlIdentityObservationKind.CANONICAL_URL not in kinds(result)


def test_pdf_artifact_stays_outside_the_additive_html_adapter():
    pdf = ingest_pdf_bytes(datasheet_pdf(), ingested_at=NOW)
    with pytest.raises(TypeError, match="HtmlArtifact"):
        resolve_html_product_identity(pdf, product())  # type: ignore[arg-type]
