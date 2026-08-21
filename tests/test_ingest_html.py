"""Safe deterministic HTML snapshots, entirely synthetic and network-free."""

from __future__ import annotations

import json
import socket
from datetime import UTC, datetime

import pytest
from conftest_html import (
    CANONICAL_HTML,
    EMPTY_HTML,
    MALFORMED_JSONLD_HTML,
    MULTIPLE_JSONLD_HTML,
    NO_USEFUL_METADATA_HTML,
    NOISY_HTML,
    PRODUCT_JSONLD_HTML,
    SIMPLE_PRODUCT_HTML,
)
from conftest_pdf import datasheet_pdf
from skutruth.contracts import DiscoveryMethod
from skutruth.ingest import (
    ArtifactKind,
    ArtifactStore,
    CorruptArtifactError,
    DocumentTooLargeError,
    EmptyDocumentError,
    HtmlArtifact,
    HtmlIngestionLimits,
    IngestedArtifact,
    MalformedDocumentError,
    SourceFragmentKind,
    SourceMetadata,
    ingest_and_store,
    ingest_html_bytes,
    sha256_bytes,
)
from skutruth.ingest.storage import HTML_CONTENT_FILE, ORIGINAL_FILE, ORIGINAL_HTML_FILE

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def ingest(data: bytes = SIMPLE_PRODUCT_HTML, **kwargs) -> HtmlArtifact:
    return ingest_html_bytes(data, media_type="text/html", ingested_at=NOW, **kwargs)


def test_html_artifact_is_explicitly_not_a_pdf():
    artifact = ingest()
    assert artifact.artifact_kind is ArtifactKind.HTML
    assert artifact.media_type == "text/html"
    assert not isinstance(artifact, IngestedArtifact)
    assert not hasattr(artifact, "pages")


def test_raw_bytes_hash_and_identity_are_deterministic():
    first = ingest()
    second = ingest()
    assert first.sha256 == sha256_bytes(SIMPLE_PRODUCT_HTML) == second.sha256
    assert first.artifact_id == second.artifact_id
    assert first.content_sha256 == second.content_sha256
    assert first.model_dump() == second.model_dump()


def test_title_and_standard_metadata_are_extracted():
    content = ingest(CANONICAL_HTML).content
    assert content.title == "Canonical Fixture"
    assert content.canonical_url == "https://manufacturer.invalid/products/45297bk"
    assert content.metadata.description == "Fixture description"
    assert content.metadata.open_graph_title == "Fixture OG title"
    assert content.metadata.open_graph_description == "Fixture OG description"


def test_visible_text_preserves_deterministic_source_order_and_locators():
    content = ingest().content
    assert content.visible_text == "Fixture Vanity Light\nModel 45297BK"
    assert [fragment.text for fragment in content.text_fragments] == [
        "Fixture Vanity Light",
        "Model 45297BK",
    ]
    assert all(
        fragment.locator.kind is SourceFragmentKind.HTML_TEXT
        for fragment in content.text_fragments
    )


def test_scripts_styles_navigation_and_inert_content_are_not_visible(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *_args, **_kwargs: pytest.fail("HTML ingestion attempted network access"),
    )
    text = ingest(NOISY_HTML).content.visible_text
    assert text == "Visible heading\nVisible detail"
    for excluded in ("Account", "executed", "subresource", "noscript", "template", "frame"):
        assert excluded not in text


def test_product_jsonld_is_preserved_as_source_data():
    block = ingest(PRODUCT_JSONLD_HTML).content.jsonld_blocks[0]
    assert block.parsed["@type"] == "Product"
    assert block.parsed["mpn"] == "45297BK"
    assert block.locator.kind is SourceFragmentKind.HTML_JSONLD
    assert block.locator.jsonld_block_index == 0
    assert block.locator.json_pointer == ""


def test_multiple_jsonld_blocks_remain_independent_and_ordered():
    blocks = ingest(MULTIPLE_JSONLD_HTML).content.jsonld_blocks
    assert len(blocks) == 2
    assert blocks[0].parsed["@type"] == "WebSite"
    assert blocks[1].parsed[0]["@type"] == "Product"


def test_malformed_jsonld_does_not_destroy_valid_document_ingest():
    artifact = ingest(MALFORMED_JSONLD_HTML)
    malformed, valid = artifact.content.jsonld_blocks
    assert malformed.parsed is None
    assert malformed.parse_error == "JSONDecodeError: invalid JSON-LD"
    assert valid.parsed["@type"] == "BreadcrumbList"
    assert artifact.content.visible_text == "Usable document text"


def test_document_without_useful_metadata_is_still_a_truthful_snapshot():
    content = ingest(NO_USEFUL_METADATA_HTML).content
    assert content.title is None
    assert content.canonical_url is None
    assert content.visible_text == ""
    assert content.jsonld_blocks == ()


def test_oversized_and_empty_html_are_refused_without_truncation():
    with pytest.raises(DocumentTooLargeError) as oversized:
        ingest_html_bytes(
            b"<p>123456789</p>",
            media_type="text/html",
            limits=HtmlIngestionLimits(max_html_bytes=8),
        )
    assert oversized.value.limit == "max_html_bytes"
    with pytest.raises(EmptyDocumentError):
        ingest_html_bytes(EMPTY_HTML, media_type="text/html")


@pytest.mark.parametrize("media_type", ["application/pdf", "text/plain", "image/png"])
def test_mime_mismatch_is_refused(media_type):
    with pytest.raises(MalformedDocumentError, match="not an accepted HTML media type"):
        ingest_html_bytes(SIMPLE_PRODUCT_HTML, media_type=media_type)
    with pytest.raises(MalformedDocumentError, match="PDF signature"):
        ingest_html_bytes(datasheet_pdf(), media_type="text/html")


def test_identity_scope_and_covered_mpn_are_never_inferred_from_locator():
    source = SourceMetadata(
        publisher="FixtureCo",
        final_artifact_url="https://manufacturer.invalid/products/45297bk",
        discovery_url="https://manufacturer.invalid/products/45297bk",
        discovery_method=DiscoveryMethod.SITE_RESTRICTED_SEARCH,
        retrieved_at=NOW,
    )
    artifact = ingest(source=source)
    assert artifact.source.identity_scope is None
    assert artifact.source.covers_mpn is None


def test_manual_and_agent_search_provenance_remain_distinguishable():
    manual = ingest(
        source=SourceMetadata(discovery_method=DiscoveryMethod.OPERATOR_SUPPLIED)
    )
    searched = ingest(
        PRODUCT_JSONLD_HTML,
        source=SourceMetadata(discovery_method=DiscoveryMethod.SITE_RESTRICTED_SEARCH),
    )
    assert manual.source.discovery_method is DiscoveryMethod.OPERATOR_SUPPLIED
    assert searched.source.discovery_method is DiscoveryMethod.SITE_RESTRICTED_SEARCH


def test_artifact_store_round_trips_raw_html_and_read_model(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = ingest()
    store.save(artifact, SIMPLE_PRODUCT_HTML)
    loaded = store.load(artifact.sha256)
    assert isinstance(loaded, HtmlArtifact)
    assert loaded == artifact
    assert store.load_original_bytes(artifact.sha256) == SIMPLE_PRODUCT_HTML
    directory = store.path_for(artifact.sha256)
    assert (directory / ORIGINAL_HTML_FILE).read_bytes() == SIMPLE_PRODUCT_HTML
    assert (directory / HTML_CONTENT_FILE).is_file()
    assert not (directory / ORIGINAL_FILE).exists()


def test_storing_identical_html_twice_keeps_one_content_address(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = ingest()
    store.save(artifact, SIMPLE_PRODUCT_HTML)
    store.save(artifact, SIMPLE_PRODUCT_HTML)
    assert store.hashes() == (artifact.sha256,)


def test_html_content_tampering_is_detected(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = ingest()
    store.save(artifact, SIMPLE_PRODUCT_HTML)
    path = store.path_for(artifact.sha256) / HTML_CONTENT_FILE
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["visible_text"] = "tampered"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(CorruptArtifactError, match="HTML artifact failed validation"):
        store.load(artifact.sha256)


def test_raw_html_tampering_is_detected(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    artifact = ingest()
    store.save(artifact, SIMPLE_PRODUCT_HTML)
    path = store.path_for(artifact.sha256) / ORIGINAL_HTML_FILE
    path.write_bytes(SIMPLE_PRODUCT_HTML + b"<!-- tampered -->")
    with pytest.raises(CorruptArtifactError, match="stored bytes have changed"):
        store.load(artifact.sha256)


def test_pdf_and_html_coexist_without_changing_pdf_layout(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    pdf = ingest_and_store(datasheet_pdf(), store, ingested_at=NOW)
    html = ingest()
    store.save(html, SIMPLE_PRODUCT_HTML)
    assert set(store.hashes()) == {pdf.sha256, html.sha256}
    assert isinstance(store.load(pdf.sha256), IngestedArtifact)
    assert isinstance(store.load(html.sha256), HtmlArtifact)
    assert (store.path_for(pdf.sha256) / ORIGINAL_FILE).is_file()


def test_store_refuses_same_hash_cross_kind_overwrite(tmp_path):
    store = ArtifactStore(tmp_path / "artifacts")
    pdf_bytes = datasheet_pdf()
    pdf = ingest_and_store(pdf_bytes, store, ingested_at=NOW)
    forged = ingest().model_copy(update={"sha256": pdf.sha256, "byte_size": len(pdf_bytes)})
    with pytest.raises(CorruptArtifactError, match="refusing HTML overwrite"):
        store.save(forged, pdf_bytes)
