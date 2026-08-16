"""Persistence, idempotence, tamper detection, and the contract adapter."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest_pdf import build_pdf, datasheet_pdf
from skutruth.contracts import DiscoveryMethod, IdentityScope, SourceArtifact, SourceType
from skutruth.ingest import (
    ArtifactCheckOutcome,
    ArtifactNotFoundError,
    ArtifactStore,
    CorruptArtifactError,
    SourceMetadata,
    check_citation_artifact,
    find_text,
    fixture_store,
    ingest_and_store,
    ingest_pdf_bytes,
    page_contains,
    runtime_store,
    sha256_bytes,
    to_source_artifact,
)
from skutruth.ingest.storage import METADATA_FILE, ORIGINAL_FILE, PAGE_MAP_FILE, PAGES_DIR


@pytest.fixture
def store(tmp_path) -> ArtifactStore:
    return ArtifactStore(tmp_path / "runtime")


@pytest.fixture
def stored(store):
    data = datasheet_pdf()
    artifact = ingest_and_store(data, store)
    return store, artifact, data


class TestPersistence:
    def test_the_artifact_is_stored_under_its_content_hash(self, stored):
        store, artifact, _ = stored
        assert (store.root / artifact.sha256 / METADATA_FILE).is_file()
        assert store.hashes() == (artifact.sha256,)

    def test_the_original_bytes_are_preserved_exactly(self, stored):
        store, artifact, data = stored
        assert (store.root / artifact.sha256 / ORIGINAL_FILE).read_bytes() == data

    def test_the_stored_original_hashes_to_the_artifact_digest(self, stored):
        store, artifact, _ = stored
        assert sha256_bytes(store.load_original_bytes(artifact.sha256)) == artifact.sha256

    def test_page_files_are_written_one_per_page(self, stored):
        store, artifact, _ = stored
        pages = sorted((store.root / artifact.sha256 / PAGES_DIR).glob("*.txt"))
        assert [p.name for p in pages] == ["0001.txt", "0002.txt", "0003.txt"]

    def test_metadata_round_trips(self, stored):
        store, artifact, _ = stored
        loaded = store.load(artifact.sha256)
        assert loaded.sha256 == artifact.sha256
        assert loaded.page_count == artifact.page_count
        assert loaded.parser_name == artifact.parser_name
        assert loaded.source.publisher == artifact.source.publisher

    def test_the_page_map_round_trips(self, stored):
        store, artifact, _ = stored
        loaded = store.load(artifact.sha256)
        assert [p.text_sha256 for p in loaded.pages] == [p.text_sha256 for p in artifact.pages]
        assert [p.raw_text for p in loaded.pages] == [p.raw_text for p in artifact.pages]

    def test_no_temporary_files_survive_a_write(self, stored):
        store, artifact, _ = stored
        assert list((store.root / artifact.sha256).glob("*.tmp")) == []

    def test_a_missing_artifact_raises_not_found(self, store):
        with pytest.raises(ArtifactNotFoundError):
            store.load("a" * 64)


class TestIdempotence:
    def test_ingesting_the_same_bytes_twice_yields_one_artifact(self, store):
        data = datasheet_pdf()
        first = ingest_and_store(data, store)
        second = ingest_and_store(data, store)
        assert first.sha256 == second.sha256
        assert len(store.hashes()) == 1

    def test_no_duplicate_directory_is_created(self, store):
        data = datasheet_pdf()
        ingest_and_store(data, store)
        ingest_and_store(data, store)
        assert len([p for p in store.root.iterdir() if p.is_dir()]) == 1

    def test_different_documents_get_different_directories(self, store):
        ingest_and_store(datasheet_pdf(), store)
        ingest_and_store(build_pdf(["A different synthetic document"]), store)
        assert len(store.hashes()) == 2

    def test_saving_bytes_that_do_not_match_the_artifact_is_refused(self, store):
        artifact = ingest_pdf_bytes(datasheet_pdf())
        with pytest.raises(CorruptArtifactError, match="supplied bytes hash to"):
            store.save(artifact, b"%PDF-1.4 different bytes entirely")


class TestTamperDetection:
    """Loading validates. It never repairs, because a read that rebuilt its own
    evidence would defeat the point of hashing it."""

    def test_an_altered_original_is_detected(self, stored):
        store, artifact, data = stored
        (store.root / artifact.sha256 / ORIGINAL_FILE).write_bytes(data + b"\n% tampered\n")
        with pytest.raises(CorruptArtifactError, match="stored bytes have changed"):
            store.load(artifact.sha256)

    def test_altered_page_text_is_detected(self, stored):
        store, artifact, _ = stored
        page = store.root / artifact.sha256 / PAGES_DIR / "0002.txt"
        page.write_text("Rated operation current: 32 A at AC-3, 400 V", encoding="utf-8")
        with pytest.raises(CorruptArtifactError, match="stored text has changed"):
            store.load(artifact.sha256)

    def test_a_missing_page_file_is_detected(self, stored):
        store, artifact, _ = stored
        (store.root / artifact.sha256 / PAGES_DIR / "0003.txt").unlink()
        with pytest.raises(CorruptArtifactError, match="page file 0003.txt is missing"):
            store.load(artifact.sha256)

    def test_a_missing_original_is_detected(self, stored):
        store, artifact, _ = stored
        (store.root / artifact.sha256 / ORIGINAL_FILE).unlink()
        with pytest.raises(CorruptArtifactError, match="original.pdf is missing"):
            store.load(artifact.sha256)

    def test_a_metadata_hash_mismatch_is_detected(self, stored):
        store, artifact, _ = stored
        path = store.root / artifact.sha256 / METADATA_FILE
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["sha256"] = "b" * 64
        path.write_text(json.dumps(blob), encoding="utf-8")
        with pytest.raises(CorruptArtifactError, match="metadata records sha256"):
            store.load(artifact.sha256)

    def test_a_wrong_page_count_is_detected(self, stored):
        store, artifact, _ = stored
        path = store.root / artifact.sha256 / METADATA_FILE
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["page_count"] = 2
        path.write_text(json.dumps(blob), encoding="utf-8")
        with pytest.raises(CorruptArtifactError, match="page map has"):
            store.load(artifact.sha256)

    def test_malformed_metadata_json_is_detected(self, stored):
        store, artifact, _ = stored
        (store.root / artifact.sha256 / METADATA_FILE).write_text("{broken", encoding="utf-8")
        with pytest.raises(CorruptArtifactError, match="unreadable JSON"):
            store.load(artifact.sha256)

    def test_a_gap_in_the_page_map_is_detected(self, stored):
        store, artifact, _ = stored
        path = store.root / artifact.sha256 / PAGE_MAP_FILE
        blob = json.loads(path.read_text(encoding="utf-8"))
        blob["pages"] = [e for e in blob["pages"] if e["page_number"] != 2]
        path.write_text(json.dumps(blob), encoding="utf-8")
        with pytest.raises(CorruptArtifactError):
            store.load(artifact.sha256)

    def test_a_malformed_hash_never_becomes_a_path(self, store):
        with pytest.raises(CorruptArtifactError, match="not a valid lowercase hex"):
            store.path_for("../../etc/passwd")

    def test_nothing_is_repaired_during_a_failed_load(self, stored):
        store, artifact, _ = stored
        page = store.root / artifact.sha256 / PAGES_DIR / "0002.txt"
        page.write_text("tampered", encoding="utf-8")
        with pytest.raises(CorruptArtifactError):
            store.load(artifact.sha256)
        assert page.read_text(encoding="utf-8") == "tampered"


class TestStoreSeparation:
    def test_the_fixture_store_is_read_only(self):
        """Ingestion must not be able to write into curated, committed fixtures."""
        assert fixture_store().writable is False
        assert runtime_store().writable is True

    def test_runtime_and_fixture_directories_are_distinct(self):
        assert runtime_store().root != fixture_store().root
        assert runtime_store().root.name == "runtime"
        assert fixture_store().root.name == "fixtures"

    def test_a_read_only_store_refuses_to_save(self, tmp_path):
        ro = ArtifactStore(tmp_path / "fixtures", writable=False)
        with pytest.raises(CorruptArtifactError, match="read-only"):
            ingest_and_store(datasheet_pdf(), ro)

    def test_the_runtime_artifact_directory_is_gitignored(self):
        """Third-party manufacturer PDFs must not enter Git history automatically."""
        repo_root = Path(__file__).resolve().parents[1]
        ignored = (repo_root / ".gitignore").read_text(encoding="utf-8")
        assert "data/artifacts/runtime/" in ignored


class TestSourceArtifactAdapter:
    def _artifact(self, **source_kwargs):
        source = SourceMetadata(
            publisher="TestCo",
            final_artifact_url="https://example.invalid/docs/testco.pdf",
            discovery_url="https://example.invalid/search?q=contactor",
            discovery_method=DiscoveryMethod.OPERATOR_SUPPLIED,
            retrieved_at=datetime(2026, 8, 15, tzinfo=UTC),
            **source_kwargs,
        )
        return ingest_pdf_bytes(datasheet_pdf(), source=source)

    def test_it_maps_hash_pages_and_urls(self):
        artifact = self._artifact(
            source_type=SourceType.MANUFACTURER_DATASHEET,
            identity_scope=IdentityScope.EXACT_SKU,
            covers_mpn="TEST-100-A",
        )
        contract = to_source_artifact(artifact)
        assert isinstance(contract, SourceArtifact)
        assert contract.sha256 == artifact.sha256
        assert contract.page_count == 3
        assert contract.final_url == "https://example.invalid/docs/testco.pdf"
        assert contract.discovery_url == "https://example.invalid/search?q=contactor"
        assert contract.publisher == "TestCo"
        assert contract.covers_mpn == "TEST-100-A"
        assert contract.identity_scope is IdentityScope.EXACT_SKU

    def test_source_type_is_never_invented(self):
        """Whether a document is a datasheet is a provenance judgement, not a fact in it."""
        artifact = self._artifact(identity_scope=IdentityScope.EXACT_SKU)
        with pytest.raises(ValueError, match="source_type is not derivable"):
            to_source_artifact(artifact)

    def test_identity_scope_is_never_invented(self):
        artifact = self._artifact(source_type=SourceType.MANUFACTURER_DATASHEET)
        with pytest.raises(ValueError, match="identity_scope is not derivable"):
            to_source_artifact(artifact)

    def test_they_may_be_supplied_by_the_caller_instead(self):
        artifact = self._artifact()
        contract = to_source_artifact(
            artifact,
            source_type=SourceType.MANUFACTURER_DATASHEET,
            identity_scope=IdentityScope.FAMILY,
        )
        assert contract.identity_scope is IdentityScope.FAMILY

    def test_a_local_fixture_without_a_url_cannot_become_a_source_artifact(self):
        artifact = ingest_pdf_bytes(datasheet_pdf())
        with pytest.raises(ValueError, match="requires a final_artifact_url"):
            to_source_artifact(
                artifact,
                source_type=SourceType.MANUFACTURER_DATASHEET,
                identity_scope=IdentityScope.EXACT_SKU,
            )

    def test_no_span_verification_is_fabricated(self):
        """Ingestion proves where text came from, not what it supports."""
        artifact = self._artifact(
            source_type=SourceType.MANUFACTURER_DATASHEET,
            identity_scope=IdentityScope.EXACT_SKU,
        )
        contract = to_source_artifact(artifact)
        assert not hasattr(contract, "verification")
        assert "proves_family_scope" not in contract.model_dump()


class TestTextLocation:
    """Infrastructure for the future verifier. Not verification."""

    @pytest.fixture
    def artifact(self):
        return ingest_pdf_bytes(datasheet_pdf())

    def test_an_exact_quote_is_located_with_its_page(self, artifact):
        matches = find_text(artifact, "18 A at AC-3, 400 V")
        assert len(matches) == 1
        assert matches[0].page_number == 2
        assert matches[0].is_exact_raw_match

    def test_a_search_can_be_scoped_to_one_page(self, artifact):
        assert find_text(artifact, "230 V AC", page_number=3)
        assert find_text(artifact, "230 V AC", page_number=1) == ()

    def test_a_quote_that_is_not_present_returns_nothing(self, artifact):
        assert find_text(artifact, "32 A at AC-1") == ()

    def test_case_and_spacing_differences_fall_back_to_the_search_index(self, artifact):
        matches = find_text(artifact, "coil   supply: 230 v ac")
        assert matches
        assert matches[0].page_number == 3
        assert not matches[0].is_exact_raw_match

    def test_page_contains_is_a_convenience_over_the_same_check(self, artifact):
        assert page_contains(artifact, 2, "18 A")
        assert not page_contains(artifact, 1, "18 A")

    def test_an_empty_quote_matches_nothing(self, artifact):
        assert find_text(artifact, "   ") == ()


class TestCitationArtifactChecks:
    """What an evaluation citation can now actually check, and what it still cannot."""

    def test_a_stored_artifact_and_page_verify(self, stored):
        store, artifact, _ = stored
        check = check_citation_artifact(store, artifact.sha256, page=2)
        assert check.outcome is ArtifactCheckOutcome.PAGE_EXISTS
        assert check.artifact_verified
        assert check.page_count == 3

    def test_a_missing_artifact_is_a_result_not_a_crash(self, store):
        check = check_citation_artifact(store, "c" * 64, page=1)
        assert check.outcome is ArtifactCheckOutcome.ARTIFACT_MISSING
        assert not check.artifact_verified

    def test_a_corrupt_artifact_is_reported(self, stored):
        store, artifact, data = stored
        (store.root / artifact.sha256 / ORIGINAL_FILE).write_bytes(data + b"tamper")
        check = check_citation_artifact(store, artifact.sha256, page=1)
        assert check.outcome is ArtifactCheckOutcome.ARTIFACT_CORRUPT

    def test_a_page_beyond_the_document_is_reported(self, stored):
        store, artifact, _ = stored
        check = check_citation_artifact(store, artifact.sha256, page=99)
        assert check.outcome is ArtifactCheckOutcome.PAGE_OUT_OF_RANGE
        assert not check.artifact_verified

    def test_a_quote_can_be_located_but_support_is_never_claimed(self, stored):
        store, artifact, _ = stored
        check = check_citation_artifact(store, artifact.sha256, page=2, quote="18 A")
        assert check.quote_located is True
        assert check.supports_value is None

    def test_a_quote_absent_from_the_cited_page_is_reported(self, stored):
        store, artifact, _ = stored
        check = check_citation_artifact(store, artifact.sha256, page=1, quote="18 A")
        assert check.artifact_verified
        assert check.quote_located is False

    def test_locating_a_quote_is_not_evidence_of_support(self, stored):
        """The semantic question is untouched by this milestone."""
        store, artifact, _ = stored
        check = check_citation_artifact(store, artifact.sha256, page=2, quote="18 A")
        assert "span support not assessed" in check.detail
