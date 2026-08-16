"""The Unilog input/delivery adapter.

Every fixture here is synthetic. No test reads `data/unilog_source/` — the organizer pack
is local, gitignored material, and a committed test that depended on it would break for
anyone who does not have it.
"""

from __future__ import annotations

import csv
import io

import pytest
from skutruth.unilog import (
    ConformanceCode,
    DeliveryRecord,
    DeliverySchema,
    DeliverySchemaError,
    DuplicateColumn,
    MalformedRowError,
    ManufacturerParse,
    MissingRequiredColumn,
    RawProductRow,
    UnknownDeliveryField,
    check_schema,
    is_placeholder,
    parse_part_manuf,
    read_rows,
    record_from_raw_row,
    write_delivery_csv,
)

INPUT_HEADER = "Mfg_Part_Num,Part_Desc,E1_Brand,Unilog_Brand,DIB_Brand,Part_Manuf"


def read_csv(text: str) -> list[RawProductRow]:
    return list(read_rows(io.StringIO(text, newline="")))


def synthetic_schema(slots: int = 3) -> DeliverySchema:
    """A miniature delivery contract with the same shape as the real one."""
    headers = ["MFR URL", "PART_NUMBER", "Mfg_Part_Num", "Part_Desc", "Classpath", "SHORT_DESC"]
    for i in range(1, slots + 1):
        headers += [f"ATTRIBUTE_LABEL {i}", f"ATTRIBUTE_VALUE {i}", f"ATTRIBUTE_UOM {i}"]
    headers += ["UPC", "Product Image", "Country Of Origin"]
    return DeliverySchema(headers)


class TestInputReading:
    def test_normal_row_parses(self):
        rows = read_csv(f"{INPUT_HEADER}\nABC123,Widget 3/8 in,Acme,Acme,Acme,Acme Tools (ACME)\n")
        assert len(rows) == 1
        row = rows[0]
        assert row.row_number == 1
        assert row.mfg_part_num == "ABC123"
        assert row.part_desc == "Widget 3/8 in"
        assert row.raw_value("Part_Manuf") == "Acme Tools (ACME)"

    def test_utf8_bom_is_stripped(self):
        rows = read_csv(f"﻿{INPUT_HEADER}\nA1,Desc,B,B,B,M (M1)\n")
        assert rows[0].mfg_part_num == "A1"

    def test_quoted_comma_and_newline_survive(self):
        text = f'{INPUT_HEADER}\nA1,"Widget, large\nsecond line",B,B,B,M (M1)\n'
        rows = read_csv(text)
        assert rows[0].part_desc == "Widget, large\nsecond line"

    def test_missing_required_header_rejected_by_name(self):
        with pytest.raises(MissingRequiredColumn, match="Part_Manuf"):
            read_csv("Mfg_Part_Num,Part_Desc,E1_Brand,Unilog_Brand,DIB_Brand\nA,B,C,D,E\n")

    def test_duplicate_header_rejected(self):
        with pytest.raises(DuplicateColumn, match="Part_Desc"):
            read_csv(f"{INPUT_HEADER},Part_Desc\nA,B,C,D,E,F,G\n")

    def test_extra_column_is_preserved_not_adopted(self):
        rows = read_csv(f"{INPUT_HEADER},Warehouse\nA1,Desc,B,B,B,M (M1),WH7\n")
        row = rows[0]
        assert row.extra == {"Warehouse": "WH7"}
        assert "Warehouse" not in {"Mfg_Part_Num", "Part_Desc"}
        assert row.raw_value("Warehouse") == "WH7"

    def test_row_width_mismatch_rejected(self):
        with pytest.raises(MalformedRowError, match="row 1"):
            read_csv(f"{INPUT_HEADER}\nA1,Desc,B\n")

    def test_blank_line_is_skipped_not_an_error(self):
        rows = read_csv(f"{INPUT_HEADER}\nA1,Desc,B,B,B,M (M1)\n\n")
        assert len(rows) == 1

    def test_empty_file_yields_nothing(self):
        assert read_csv("") == []

    def test_rows_are_streamed(self):
        """The reader is a generator; it must not materialise the file."""
        import types

        assert isinstance(read_rows(io.StringIO(INPUT_HEADER + "\n")), types.GeneratorType)


class TestPlaceholders:
    def test_documented_sentinels_are_removed(self):
        rows = read_csv(
            f"{INPUT_HEADER}\n"
            f"A1,Desc,-- Unbranded --,-- No Unilog Brand --,-- No DIB Brand --,M (M1)\n"
        )
        row = rows[0]
        assert row.e1_brand is None
        assert row.unilog_brand is None
        assert row.dib_brand is None
        assert row.brand_signals == ()

    def test_raw_value_survives_cleaning(self):
        """ "the source said -- Unbranded --" and "the source said nothing" differ."""
        rows = read_csv(f"{INPUT_HEADER}\nA1,Desc,-- Unbranded --,X,X,M (M1)\n")
        assert rows[0].e1_brand is None
        assert rows[0].raw_value("E1_Brand") == "-- Unbranded --"

    def test_bare_hyphen_is_a_placeholder_only_for_part_manuf(self):
        assert is_placeholder("Part_Manuf", "-") is True
        assert is_placeholder("Part_Desc", "-") is False
        assert is_placeholder("Mfg_Part_Num", "-") is False

    def test_hyphen_inside_a_description_is_untouched(self):
        rows = read_csv(f"{INPUT_HEADER}\nA-1,3/8 CPLG - BRS,B,B,B,M (M1)\n")
        assert rows[0].part_desc == "3/8 CPLG - BRS"
        assert rows[0].mfg_part_num == "A-1"

    def test_empty_string_is_not_a_placeholder(self):
        assert is_placeholder("E1_Brand", "") is False
        assert is_placeholder("E1_Brand", "   ") is False

    def test_whitespace_is_trimmed(self):
        rows = read_csv(f"{INPUT_HEADER}\n  A1  ,  Desc  ,B,B,B,M (M1)\n")
        assert rows[0].mfg_part_num == "A1"
        assert rows[0].part_desc == "Desc"


class TestManufacturerParsing:
    def test_name_with_code(self):
        parsed = parse_part_manuf("Kichler Lighting (KICLI)")
        assert parsed.status is ManufacturerParse.NAME_WITH_CODE
        assert parsed.display_name == "Kichler Lighting"
        assert parsed.supplier_code == "KICLI"
        assert parsed.is_resolved and parsed.has_code

    def test_surrounding_whitespace(self):
        parsed = parse_part_manuf("   Acme Tools   (AC12)   ")
        assert parsed.display_name == "Acme Tools"
        assert parsed.supplier_code == "AC12"

    def test_numeric_code_preserved_verbatim(self):
        parsed = parse_part_manuf("Phillips Lighting (5831)")
        assert parsed.supplier_code == "5831"
        assert parsed.display_name == "Phillips Lighting"

    def test_spelling_is_never_corrected(self):
        """Canonicalisation needs the approved master, which is not available."""
        assert parse_part_manuf("Phillips Lighting (5831)").display_name == "Phillips Lighting"
        assert (
            parse_part_manuf("Black & Decker/dewlt (2585)").display_name == "Black & Decker/dewlt"
        )

    def test_name_without_code_is_resolved_not_failed(self):
        parsed = parse_part_manuf("Acme Tools")
        assert parsed.status is ManufacturerParse.NAME_ONLY
        assert parsed.display_name == "Acme Tools"
        assert parsed.supplier_code is None
        assert parsed.is_resolved

    def test_placeholder_yields_no_manufacturer(self):
        parsed = parse_part_manuf("-")
        assert parsed.status is ManufacturerParse.PLACEHOLDER
        assert parsed.display_name is None
        assert not parsed.is_resolved

    def test_blank_is_missing(self):
        assert parse_part_manuf("   ").status is ManufacturerParse.MISSING
        assert parse_part_manuf(None).status is ManufacturerParse.MISSING

    @pytest.mark.parametrize("value", ["(ACME)", "Acme ()", "Acme (AC", "Acme )AC("])
    def test_ambiguous_forms_stay_unresolved(self, value):
        parsed = parse_part_manuf(value)
        assert parsed.status is ManufacturerParse.UNRESOLVED
        assert parsed.supplier_code is None

    def test_embedded_parentheses_are_not_mistaken_for_a_code(self):
        parsed = parse_part_manuf("Acme (US) Tools")
        assert parsed.status is ManufacturerParse.NAME_ONLY
        assert parsed.supplier_code is None

    def test_code_length_is_not_constrained(self):
        """4 and 5 chars is an observation about one sample, not a contract."""
        assert parse_part_manuf("Acme (A)").supplier_code == "A"
        assert parse_part_manuf("Acme (ABCDEFGHIJ)").supplier_code == "ABCDEFGHIJ"


class TestDeliverySchema:
    def test_header_order_is_preserved_exactly(self):
        headers = ["Zebra", "Alpha", "Mike"]
        assert DeliverySchema(headers).headers == ("Zebra", "Alpha", "Mike")

    def test_duplicate_delivery_header_rejected(self):
        with pytest.raises(DeliverySchemaError, match="repeats"):
            DeliverySchema(["A", "B", "A"])

    def test_empty_schema_rejected(self):
        with pytest.raises(DeliverySchemaError):
            DeliverySchema([])

    def test_attribute_triplets_are_discovered(self):
        schema = synthetic_schema(slots=4)
        assert schema.attribute_slot_count == 4
        spec = schema.attribute_slots[0]
        assert (spec.index, spec.label_field, spec.value_field, spec.uom_field) == (
            1,
            "ATTRIBUTE_LABEL 1",
            "ATTRIBUTE_VALUE 1",
            "ATTRIBUTE_UOM 1",
        )

    def test_broken_triplet_rejected(self):
        with pytest.raises(DeliverySchemaError, match="slot 2 is incomplete"):
            DeliverySchema(
                [
                    "A",
                    "ATTRIBUTE_LABEL 1",
                    "ATTRIBUTE_VALUE 1",
                    "ATTRIBUTE_UOM 1",
                    "ATTRIBUTE_LABEL 2",
                    "ATTRIBUTE_VALUE 2",
                ]
            )

    def test_slot_count_is_derived_not_assumed(self):
        assert synthetic_schema(slots=1).attribute_slot_count == 1
        assert synthetic_schema(slots=60).attribute_slot_count == 60

    def test_groups_cover_every_header(self):
        schema = synthetic_schema()
        grouped = sum(len(v) for v in schema.groups().values())
        assert grouped == schema.field_count

    def test_grouping_does_not_change_export_order(self):
        schema = synthetic_schema()
        before = schema.headers
        schema.groups()
        assert schema.headers == before

    def test_from_csv_reads_only_the_header(self, tmp_path):
        path = tmp_path / "delivery.csv"
        path.write_text("A,B,C\n1,2,3\n4,5,6\n", encoding="utf-8")
        assert DeliverySchema.from_csv(path).headers == ("A", "B", "C")


class TestFingerprint:
    def test_fingerprint_is_stable(self):
        assert synthetic_schema().fingerprint() == synthetic_schema().fingerprint()

    def test_order_change_changes_fingerprint(self):
        a = DeliverySchema(["A", "B", "C"])
        b = DeliverySchema(["A", "C", "B"])
        assert a.fingerprint() != b.fingerprint()
        assert not a.matches(b)

    def test_rename_changes_fingerprint(self):
        assert DeliverySchema(["A", "B"]).fingerprint() != DeliverySchema(["A", "B2"]).fingerprint()

    def test_fingerprint_ignores_row_values(self, tmp_path):
        """The contract is the header; data must not move the fingerprint."""
        one = tmp_path / "a.csv"
        two = tmp_path / "b.csv"
        one.write_text("A,B\n1,2\n", encoding="utf-8")
        two.write_text("A,B\n9,9\n9,9\n", encoding="utf-8")
        assert DeliverySchema.from_csv(one).fingerprint() == (
            DeliverySchema.from_csv(two).fingerprint()
        )


class TestDeliveryRecord:
    def test_unknown_field_rejected(self):
        record = DeliveryRecord(synthetic_schema())
        with pytest.raises(UnknownDeliveryField, match="Invented"):
            record.set("Invented", "x")

    def test_missing_values_export_as_empty_string(self):
        schema = synthetic_schema()
        row = DeliveryRecord(schema).to_row()
        assert len(row) == schema.field_count
        assert set(row) == {""}

    def test_none_never_leaks_as_text(self):
        record = DeliveryRecord(synthetic_schema())
        record.set("SHORT_DESC", None)
        assert record.get("SHORT_DESC") == ""
        assert "None" not in record.to_row()
        assert "null" not in record.to_row()

    def test_assigned_fields_report_in_schema_order(self):
        schema = synthetic_schema()
        record = DeliveryRecord(schema)
        record.set("SHORT_DESC", "b")
        record.set("MFR URL", "a")
        assert record.assigned_fields == ("MFR URL", "SHORT_DESC")

    def test_blank_attribute_value_is_preserved(self):
        """Declared-but-blank is meaningful: applies, but not established."""
        schema = synthetic_schema()
        record = DeliveryRecord(schema)
        record.set_attribute(1, "Series", "Professional Series")
        record.set_attribute(2, "Model")  # declared, deliberately blank
        slots = record.attribute_slots()
        assert len(slots) == schema.attribute_slot_count
        assert slots[1].label == "Model"
        assert slots[1].is_declared and not slots[1].has_value
        assert slots[1].is_declared_but_blank

    def test_undeclared_slot_differs_from_blank_slot(self):
        record = DeliveryRecord(synthetic_schema())
        record.set_attribute(1, "Series", "X")
        record.set_attribute(2, "Model")
        slots = record.attribute_slots()
        assert slots[1].is_declared is True  # blank value, real label
        assert slots[2].is_declared is False  # never declared at all
        assert len(record.declared_attribute_slots()) == 2

    def test_slots_are_never_compacted(self):
        schema = synthetic_schema(slots=5)
        record = DeliveryRecord(schema)
        record.set_attribute(4, "Late", "value")
        assert len(record.attribute_slots()) == 5

    def test_unknown_attribute_slot_rejected(self):
        record = DeliveryRecord(synthetic_schema(slots=2))
        with pytest.raises(UnknownDeliveryField, match="slot 9"):
            record.set_attribute(9, "Nope")


class TestPassthrough:
    def test_only_identical_headers_are_carried_across(self):
        schema = DeliverySchema(
            ["Mfg_Part_Num", "Part_Desc", "PART_NUMBER", "MANUFACTURER_PART_NUMBER"]
        )
        row = read_csv(f"{INPUT_HEADER}\nA1,Desc,B,B,B,M (M1)\n")[0]
        record = record_from_raw_row(row, schema)
        assert record.get("Mfg_Part_Num") == "A1"
        assert record.get("Part_Desc") == "Desc"
        # Similar names are not proof of the same meaning.
        assert record.get("PART_NUMBER") == ""
        assert record.get("MANUFACTURER_PART_NUMBER") == ""

    def test_no_identity_or_classification_is_invented(self):
        schema = DeliverySchema(["Mfg_Part_Num", "MANUFACTURER_NAME", "BRAND_NAME", "Classpath"])
        row = read_csv(f"{INPUT_HEADER}\nA1,Desc,Acme,B,B,Acme Tools (ACME)\n")[0]
        record = record_from_raw_row(row, schema)
        assert record.get("MANUFACTURER_NAME") == ""
        assert record.get("BRAND_NAME") == ""
        assert record.get("Classpath") == ""

    def test_passthrough_echoes_raw_placeholders(self):
        """The organizer's own examples echo the placeholder back in this block."""
        schema = DeliverySchema(["E1_Brand"])
        row = read_csv(f"{INPUT_HEADER}\nA1,Desc,-- Unbranded --,B,B,M (M1)\n")[0]
        assert record_from_raw_row(row, schema).get("E1_Brand") == "-- Unbranded --"


class TestWriter:
    def test_header_written_in_schema_order(self):
        schema = DeliverySchema(["Zebra", "Alpha", "Mike"])
        buf = io.StringIO(newline="")
        write_delivery_csv([], schema, buf)
        assert next(csv.reader(io.StringIO(buf.getvalue()))) == ["Zebra", "Alpha", "Mike"]

    def test_writer_ignores_assignment_order(self):
        schema = DeliverySchema(["Zebra", "Alpha", "Mike"])
        record = DeliveryRecord(schema)
        record.set("Mike", "3")
        record.set("Zebra", "1")
        record.set("Alpha", "2")
        buf = io.StringIO(newline="")
        write_delivery_csv([record], schema, buf)
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        assert rows[1] == ["1", "2", "3"]

    def test_every_row_has_exact_field_count(self):
        schema = synthetic_schema()
        records = [DeliveryRecord(schema) for _ in range(3)]
        records[0].set("SHORT_DESC", "x")
        buf = io.StringIO(newline="")
        assert write_delivery_csv(records, schema, buf) == 3
        for row in list(csv.reader(io.StringIO(buf.getvalue()))):
            assert len(row) == schema.field_count

    def test_unicode_trademark_survives_roundtrip(self):
        schema = DeliverySchema(["BRAND_NAME", "SHORT_DESC"])
        record = DeliveryRecord(schema)
        record.set("BRAND_NAME", "FRIGIDAIRE®")
        record.set("SHORT_DESC", "Dishwasher With CleanBoost™, 24-1/4 in")
        buf = io.StringIO(newline="")
        write_delivery_csv([record], schema, buf)
        rows = list(csv.reader(io.StringIO(buf.getvalue())))
        assert rows[1] == ["FRIGIDAIRE®", "Dishwasher With CleanBoost™, 24-1/4 in"]

    def test_multiline_and_comma_content_roundtrips(self):
        schema = DeliverySchema(["LONG_DESC1", "Standard/Approvals"])
        record = DeliveryRecord(schema)
        record.set("LONG_DESC1", 'Line one,\nline "two"')
        record.set("Standard/Approvals", "UL Listed|NSF Certified")
        buf = io.StringIO(newline="")
        write_delivery_csv([record], schema, buf)
        rows = list(csv.reader(io.StringIO(buf.getvalue(), newline="")))
        assert rows[1] == ['Line one,\nline "two"', "UL Listed|NSF Certified"]

    def test_record_from_a_different_schema_is_rejected(self):
        record = DeliveryRecord(DeliverySchema(["A", "B"]))
        buf = io.StringIO(newline="")
        with pytest.raises(UnknownDeliveryField, match="different delivery schema"):
            write_delivery_csv([record], DeliverySchema(["A", "C"]), buf)


class TestConformance:
    def test_matching_schema_conforms(self):
        assert check_schema(synthetic_schema(), synthetic_schema()).ok

    def test_missing_and_unexpected_headers_reported_separately(self):
        report = check_schema(DeliverySchema(["A", "X"]), DeliverySchema(["A", "B"]))
        assert ConformanceCode.MISSING_HEADER in report.codes()
        assert ConformanceCode.UNEXPECTED_HEADER in report.codes()

    def test_order_mismatch_is_its_own_code(self):
        report = check_schema(DeliverySchema(["A", "B"]), DeliverySchema(["B", "A"]))
        assert ConformanceCode.ORDER_MISMATCH in report.codes()
        assert ConformanceCode.MISSING_HEADER not in report.codes()

    def test_field_count_mismatch_reported(self):
        report = check_schema(DeliverySchema(["A"]), DeliverySchema(["A", "B"]))
        assert ConformanceCode.FIELD_COUNT_MISMATCH in report.codes()

    def test_row_width_mismatch_reported(self):
        from skutruth.unilog import check_rows

        schema = DeliverySchema(["A", "B"])
        report = check_rows([["1", "2"], ["1"]], schema)
        assert ConformanceCode.ROW_WIDTH_MISMATCH in report.codes()
        assert "row 2" in report.issues[0].detail

    def test_report_is_not_one_generic_error(self):
        report = check_schema(DeliverySchema(["A", "X"]), DeliverySchema(["A", "B"]))
        assert len({i.code for i in report.issues}) > 1


class TestOrganizerDataStaysLocal:
    def test_source_directory_is_gitignored(self):
        import subprocess
        from pathlib import Path

        repo = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["git", "check-ignore", str(repo / "data" / "unilog_source")],
            cwd=repo,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, "data/unilog_source/ must stay gitignored"

    def test_no_committed_test_names_an_organizer_file(self):
        """The real risk is a test hardcoding an organizer filename it cannot ship."""
        from pathlib import Path

        # Assembled at runtime so this guard does not match its own source text.
        prefix = "Unihack" + "_ "
        organizer_files = (prefix + "Sample Dataset", prefix + "Expected Output")
        for path in Path(__file__).parent.glob("test_*.py"):
            source = path.read_text(encoding="utf-8")
            for name in organizer_files:
                assert name not in source, f"{path.name} depends on organizer file {name!r}"
