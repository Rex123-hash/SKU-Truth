"""Structured table reconstruction.

Every fixture here is synthetic. The real Schneider catalogue that motivated this module
is gitignored runtime material and is validated by a local, uncommitted script instead —
a committed test must never depend on a third-party copyrighted document.
"""

from __future__ import annotations

import pytest
from conftest_pdf import (
    build_pdf,
    build_ruled_table_pdf,
    datasheet_pdf,
    grouped_header_pdf,
)
from skutruth.ingest import (
    TABLE_EXTRACTION_VERSION,
    IngestionError,
    TableExtractionStatus,
    extract_page_tables,
    ingest_pdf_bytes,
)


def _table(pdf: bytes, page_number: int = 1):
    result = extract_page_tables(pdf, page_number)
    assert result.status is TableExtractionStatus.TABLES_EXTRACTED
    return result.tables[0]


class TestGroupedColumns:
    """The failure this module exists for: grouped column headers.

    Two voltage labels stacked in one ruled column must stay one column. Reading them as
    two columns is what produces a confidently wrong value.
    """

    def test_stacked_labels_stay_in_one_column(self):
        table = _table(grouped_header_pdf())
        header = table.header_rows()
        assert header[0][:3] == ("220 V", "380 V", "500 V")
        assert header[1][:2] == ("230 V", "400 V")

    def test_body_row_aligns_with_grouped_header(self):
        table = _table(grouped_header_pdf())
        first = table.body_rows()[0]
        # 380 V and 400 V share column 1, so column 1 carries exactly one value.
        assert first[:4] == ("4", "7.5", "10", "AAA111")

    def test_row_identity_column_is_preserved(self):
        """The reference must survive; a table of numbers with no row identity is useless."""
        table = _table(grouped_header_pdf())
        assert [r[3] for r in table.body_rows()] == ["AAA111", "BBB222"]

    def test_find_rows_locates_a_reference(self):
        table = _table(grouped_header_pdf())
        rows = table.find_rows("BBB222")
        assert len(rows) == 1
        assert table.row(rows[0])[1] == "11"


class TestStructure:
    def test_rows_are_dense_and_uniform(self):
        table = _table(grouped_header_pdf())
        assert table.column_count == 4
        assert all(len(r) == table.column_count for r in table.rows())
        assert table.row_count == len(table.header_rows()) + len(table.body_rows())

    def test_header_and_body_are_distinguished(self):
        table = _table(grouped_header_pdf())
        assert table.header_row_count == 3
        assert {c.is_header for c in table.cells if c.row_index == 0} == {True}
        assert {c.is_header for c in table.cells if c.row_index == table.row_count - 1} == {False}

    def test_cell_indices_are_complete(self):
        table = _table(grouped_header_pdf())
        seen = {(c.row_index, c.column_index) for c in table.cells}
        assert seen == {(r, c) for r in range(table.row_count) for c in range(table.column_count)}

    def test_page_number_is_one_indexed(self):
        pdf = build_pdf(["first page"])
        assert extract_page_tables(pdf, 1).page_number == 1

    def test_bbox_reported(self):
        table = _table(grouped_header_pdf())
        assert table.bbox is not None
        x0, _, x1, _ = table.bbox
        assert x0 == pytest.approx(60, abs=1)
        assert x1 == pytest.approx(460, abs=1)


class TestVersioning:
    """A parser upgrade can move a word into a different cell. That must be observable."""

    def test_engine_and_versions_recorded(self):
        table = _table(grouped_header_pdf())
        assert table.engine == "pdfplumber"
        assert table.engine_version and table.engine_version[0].isdigit()
        assert table.strategy_version == TABLE_EXTRACTION_VERSION

    def test_versions_recorded_even_when_no_table(self):
        result = extract_page_tables(datasheet_pdf(), 1)
        assert result.engine == "pdfplumber"
        assert result.engine_version
        assert result.strategy_version == TABLE_EXTRACTION_VERSION


class TestNoFabrication:
    """Withholding beats guessing. Whitespace is not evidence of a column boundary."""

    def test_unruled_page_yields_no_table_structure(self):
        result = extract_page_tables(datasheet_pdf(), 1)
        assert result.status is TableExtractionStatus.NO_TABLE_STRUCTURE
        assert result.tables == ()
        assert not result.has_tables

    def test_columnar_looking_text_without_rules_is_not_a_table(self):
        """Text that reads like a table but has no ruling must not become one."""
        pdf = build_pdf(["220 V   380 V   500 V", "4   7.5   10"])
        result = extract_page_tables(pdf, 1)
        assert result.status is TableExtractionStatus.NO_TABLE_STRUCTURE

    def test_too_few_columns_is_not_reconstructed(self):
        pdf = build_ruled_table_pdf(
            [(x, 700.0, 740.0) for x in (60, 160)],
            [(65, 728, "Volts"), (65, 685, "24")],
        )
        assert extract_page_tables(pdf, 1).status is (TableExtractionStatus.NO_TABLE_STRUCTURE)

    def test_rules_with_no_words_are_unresolved_not_invented(self):
        pdf = build_ruled_table_pdf([(x, 700.0, 740.0) for x in (60, 160, 260, 360)], [])
        result = extract_page_tables(pdf, 1)
        assert result.status is TableExtractionStatus.TABLE_STRUCTURE_UNRESOLVED
        assert result.tables == ()

    def test_words_outside_the_frame_are_counted_not_forced_into_a_cell(self):
        pdf = build_ruled_table_pdf(
            [(x, 700.0, 740.0) for x in (60, 160, 260, 360)],
            [
                (65, 728, "A"),
                (165, 728, "B"),
                (265, 728, "C"),
                (65, 685, "1"),
                (165, 685, "2"),
                (265, 685, "3"),
                (500, 685, "OUTSIDE"),
            ],
        )
        table = _table(pdf)
        assert table.words_outside_frame >= 1
        assert not any("OUTSIDE" in c.text for c in table.cells)


class TestRawTextUntouched:
    """The canonical representation must be unaffected by any of this."""

    def test_pypdf_page_text_and_hash_are_unchanged(self):
        pdf = grouped_header_pdf()
        before = ingest_pdf_bytes(pdf)
        extract_page_tables(pdf, 1)
        after = ingest_pdf_bytes(pdf)
        assert before.sha256 == after.sha256
        assert before.pages[0].raw_text == after.pages[0].raw_text
        assert before.pages[0].text_sha256 == after.pages[0].text_sha256

    def test_table_extraction_does_not_alter_artifact_identity(self):
        pdf = grouped_header_pdf()
        artifact = ingest_pdf_bytes(pdf)
        result = extract_page_tables(pdf, 1)
        assert result.page_number == artifact.pages[0].page_number


class TestDeterminism:
    def test_repeated_extraction_is_identical(self):
        pdf = grouped_header_pdf()
        assert extract_page_tables(pdf, 1) == extract_page_tables(pdf, 1)


class TestRefusals:
    def test_non_pdf_bytes_refused(self):
        with pytest.raises(IngestionError, match="not a PDF"):
            extract_page_tables(b"<html></html>", 1)

    def test_page_beyond_document_refused(self):
        with pytest.raises(IngestionError, match="page 99 requested"):
            extract_page_tables(datasheet_pdf(), 99)

    def test_zero_page_number_refused(self):
        with pytest.raises(IngestionError, match="1-indexed"):
            extract_page_tables(datasheet_pdf(), 0)


class TestRuntimeArtifactsStayOutOfGit:
    def test_runtime_directory_is_ignored(self):
        import subprocess
        from pathlib import Path

        from skutruth.ingest import DEFAULT_RUNTIME_DIR

        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "check-ignore", str(DEFAULT_RUNTIME_DIR)],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "data/artifacts/runtime/ must stay gitignored"
