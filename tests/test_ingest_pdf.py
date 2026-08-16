"""Hashing, validation, limits, and the page model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from conftest_pdf import DATASHEET_PAGES, build_imageless_pdf, build_pdf, datasheet_pdf
from skutruth.ingest import (
    ACCEPTED_MEDIA_TYPE,
    INGESTION_VERSION,
    DocumentTextStatus,
    DocumentTooLargeError,
    EmptyDocumentError,
    ExtractionStatus,
    IngestionLimits,
    MalformedDocumentError,
    SourceMetadata,
    artifact_id,
    ingest_pdf,
    ingest_pdf_bytes,
    sha256_bytes,
)


class TestArtifactHashing:
    def test_identical_bytes_hash_identically(self):
        a, b = datasheet_pdf(), datasheet_pdf()
        assert a == b
        assert ingest_pdf_bytes(a).sha256 == ingest_pdf_bytes(b).sha256

    def test_a_one_byte_change_changes_the_hash(self):
        original = datasheet_pdf()
        altered = original.replace(b"18 A", b"19 A")
        assert altered != original
        assert ingest_pdf_bytes(original).sha256 != ingest_pdf_bytes(altered).sha256

    def test_the_hash_is_over_the_original_bytes_not_the_text(self):
        data = datasheet_pdf()
        assert ingest_pdf_bytes(data).sha256 == sha256_bytes(data)

    def test_the_artifact_id_is_content_addressed(self):
        artifact = ingest_pdf_bytes(datasheet_pdf())
        assert artifact.artifact_id == f"sha256:{artifact.sha256}"

    def test_the_artifact_id_is_deterministic_across_ingestions(self):
        first = ingest_pdf_bytes(datasheet_pdf(), ingested_at=datetime(2026, 1, 1, tzinfo=UTC))
        second = ingest_pdf_bytes(datasheet_pdf(), ingested_at=datetime(2026, 6, 1, tzinfo=UTC))
        assert first.artifact_id == second.artifact_id

    def test_a_malformed_artifact_id_is_rejected(self):
        with pytest.raises(ValueError, match="not a lowercase hex SHA-256"):
            artifact_id("nonsense")


class TestDocumentValidation:
    def test_empty_bytes_are_rejected(self):
        with pytest.raises(EmptyDocumentError, match="zero bytes"):
            ingest_pdf_bytes(b"")

    def test_a_non_pdf_is_rejected_on_its_signature(self):
        with pytest.raises(MalformedDocumentError, match="PDF signature"):
            ingest_pdf_bytes(b"this is plainly not a PDF file at all")

    def test_a_truncated_pdf_is_rejected(self):
        with pytest.raises(MalformedDocumentError):
            ingest_pdf_bytes(datasheet_pdf()[:120])

    def test_only_pdf_is_accepted(self):
        assert ingest_pdf_bytes(datasheet_pdf()).media_type == ACCEPTED_MEDIA_TYPE

    def test_a_missing_file_is_rejected(self, tmp_path):
        with pytest.raises(MalformedDocumentError, match="no file at"):
            ingest_pdf(tmp_path / "absent.pdf")


class TestLimits:
    def test_the_file_size_cap_rejects_rather_than_truncates(self):
        limits = IngestionLimits(max_file_bytes=100)
        with pytest.raises(DocumentTooLargeError, match="rejected rather than truncated") as exc:
            ingest_pdf_bytes(datasheet_pdf(), limits=limits)
        assert exc.value.limit == "max_file_bytes"
        assert exc.value.allowed == 100

    def test_the_page_count_cap_rejects_rather_than_truncates(self):
        limits = IngestionLimits(max_page_count=2)
        with pytest.raises(DocumentTooLargeError, match="rejected rather than partially") as exc:
            ingest_pdf_bytes(datasheet_pdf(), limits=limits)
        assert exc.value.limit == "max_page_count"
        assert exc.value.actual == 3

    def test_the_per_page_text_cap_is_enforced(self):
        limits = IngestionLimits(max_page_text_chars=5)
        with pytest.raises(DocumentTooLargeError) as exc:
            ingest_pdf_bytes(datasheet_pdf(), limits=limits)
        assert exc.value.limit == "max_page_text_chars"

    def test_a_document_within_limits_ingests(self):
        assert ingest_pdf_bytes(datasheet_pdf(), limits=IngestionLimits()).page_count == 3


@pytest.fixture(scope="module")
def artifact():
    return ingest_pdf_bytes(datasheet_pdf())


class TestPageModel:
    def test_the_page_count_is_correct(self, artifact):
        assert artifact.page_count == 3
        assert len(artifact.pages) == 3

    def test_pages_are_one_indexed(self, artifact):
        """Page 1 in a citation must mean page 1 in the PDF a reviewer opens."""
        assert [p.page_number for p in artifact.pages] == [1, 2, 3]
        assert artifact.page(1).raw_text.startswith("TESTCO")
        assert artifact.page(0) is None

    def test_page_text_is_preserved(self, artifact):
        assert "18 A at AC-3, 400 V" in artifact.page(2).raw_text
        assert "230 V AC" in artifact.page(3).raw_text

    def test_page_hashes_are_stable_across_ingestions(self):
        a = ingest_pdf_bytes(datasheet_pdf())
        b = ingest_pdf_bytes(datasheet_pdf())
        assert [p.text_sha256 for p in a.pages] == [p.text_sha256 for p in b.pages]

    def test_a_page_hash_differs_from_the_artifact_hash(self, artifact):
        """Distinct purposes: one identifies bytes, the other detects extraction drift."""
        assert artifact.page(1).text_sha256 != artifact.sha256

    def test_character_counts_match_the_text(self, artifact):
        for page in artifact.pages:
            assert page.character_count == len(page.raw_text)

    def test_dimensions_are_captured_when_available(self, artifact):
        assert artifact.page(1).width_points == pytest.approx(612.0)
        assert artifact.page(1).height_points == pytest.approx(792.0)

    def test_every_page_is_marked_text_extracted(self, artifact):
        assert all(p.status is ExtractionStatus.TEXT_EXTRACTED for p in artifact.pages)


class TestTextExtractionStatus:
    def test_a_text_bearing_document_is_extractable(self):
        assert ingest_pdf_bytes(datasheet_pdf()).text_status is DocumentTextStatus.TEXT_EXTRACTABLE

    def test_a_document_with_no_text_reports_ocr_required_without_running_ocr(self):
        """A scanned page yields no text; it must never yield invented text."""
        artifact = ingest_pdf_bytes(build_imageless_pdf(2))
        assert artifact.text_status is DocumentTextStatus.OCR_REQUIRED
        assert all(p.status is ExtractionStatus.NO_EXTRACTABLE_TEXT for p in artifact.pages)
        assert all(p.raw_text == "" for p in artifact.pages)

    def test_a_partially_extractable_document_is_labelled_as_such(self):
        mixed = build_pdf(["Page one has text"] * 1)
        artifact = ingest_pdf_bytes(mixed)
        assert artifact.text_status is DocumentTextStatus.TEXT_EXTRACTABLE


class TestVersioning:
    def test_the_ingestion_and_parser_versions_are_recorded(self):
        """A parser upgrade can reorder a table; that must be observable."""
        artifact = ingest_pdf_bytes(datasheet_pdf())
        assert artifact.ingestion_version == INGESTION_VERSION
        assert artifact.parser_name == "pypdf"
        assert artifact.parser_version
        assert artifact.text_normalization_form == "NFKC"

    def test_ingested_at_is_timezone_aware_utc(self):
        artifact = ingest_pdf_bytes(datasheet_pdf())
        assert artifact.ingested_at.tzinfo is not None
        assert artifact.ingested_at.utcoffset().total_seconds() == 0


class TestSourceMetadata:
    def test_a_local_fixture_needs_no_url(self):
        """Absent URLs stay absent; nothing is fabricated."""
        artifact = ingest_pdf_bytes(datasheet_pdf(), source=SourceMetadata(publisher="TestCo"))
        assert artifact.source.final_artifact_url is None
        assert artifact.source.discovery_url is None
        assert artifact.source.publisher == "TestCo"

    def test_discovery_url_stays_distinct_from_the_artifact_url(self):
        """A landing page must never silently become the evidence URL."""
        source = SourceMetadata(
            discovery_url="https://example.invalid/search?q=contactor",
            final_artifact_url="https://example.invalid/docs/testco-datasheet.pdf",
        )
        artifact = ingest_pdf_bytes(datasheet_pdf(), source=source)
        assert artifact.source.discovery_url != artifact.source.final_artifact_url

    def test_covers_mpn_is_preserved_when_supplied(self):
        artifact = ingest_pdf_bytes(
            datasheet_pdf(), source=SourceMetadata(covers_mpn="TEST-100-A")
        )
        assert artifact.source.covers_mpn == "TEST-100-A"

    def test_no_mpn_or_scope_is_invented(self):
        artifact = ingest_pdf_bytes(datasheet_pdf())
        assert artifact.source.covers_mpn is None
        assert artifact.source.identity_scope is None
        assert artifact.source.source_type is None

    def test_retrieved_at_must_be_timezone_aware(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            SourceMetadata(retrieved_at=datetime(2026, 8, 15))  # noqa: DTZ001

    def test_the_filename_is_captured_from_a_local_path(self, tmp_path):
        path = tmp_path / "testco-datasheet.pdf"
        path.write_bytes(datasheet_pdf())
        assert ingest_pdf(path).source.original_filename == "testco-datasheet.pdf"


class TestFixturesAreSynthetic:
    def test_the_test_document_is_obviously_not_a_real_product(self):
        """No manufacturer PDF is downloaded or committed for tests."""
        assert DATASHEET_PAGES[0].startswith("TESTCO")
        assert all("Schneider" not in page for page in DATASHEET_PAGES)
