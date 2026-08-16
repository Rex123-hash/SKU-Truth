"""Structured table extraction — an *additional* representation, never a replacement.

`IngestedPage.raw_text` and its hash stay exactly as pypdf produced them. This module
adds a second, optional view of a page: cells laid out on the column grid the page
itself draws. Both are kept because they answer different questions —

    raw_text  : "the parser emitted this text"
    this      : "the table reconstructor placed these words in these cells"

and a citation may later need to distinguish them.

## Why this exists

On the real Schneider TeSys catalogue (artifact
`ca5977404d8ae…`, PDF page 4, printed B8/2) pypdf preserves every character but
destroys the column grouping. Ten voltage labels are emitted across seven lines whose
breaks do not fall on column boundaries, against seven `kW` value columns. Reading each
label as its own column yields `400 V -> 9 kW`; Schneider's own LC1D18P7 data sheet says
`380/400 V -> 7.5 kW`. That is not lost recall — it is a confidently wrong answer, which
is the one failure mode this project cannot tolerate.

## How it works

The page draws its own column boundaries as vertical ruling lines. Those lines are the
ground truth for column geometry, so:

1. cluster vertical ruling edges into bands that share a y-extent (a *rule frame*);
2. merge vertically adjacent bands — a header's label row and unit row are ruled
   separately but are one table;
3. bin words into columns by midpoint and into rows by baseline.

Step 3 is deliberately done here rather than by handing explicit lines back to
pdfplumber, which was observed to silently drop a column on catalogue page 10. A silent
column drop is precisely the class of defect this module exists to prevent, so the
mapping is kept inspectable.

Rule frames end where the ruling ends, but catalogue data rows continue below them
unruled. Body rows are therefore *projected* down the same column boundaries for as long
as rows keep filling more than one column.

## What it will not do

* **Guess.** A page with no ruling yields `NO_TABLE_STRUCTURE`, not a table inferred from
  whitespace. Withholding beats `400 V -> 9 kW`.
* **Name columns.** Header rows are emitted verbatim and never collapsed into one label
  per column. A catalogue header band also contains shredded title text, so *which* header
  row carries the column labels is not deterministically derivable here and is left to the
  caller, who can see all of them.
* **Run automatically.** There is no malformed-table detector yet; extraction is requested
  per page by the caller. Inventing an unreliable trigger would be worse than asking.
* **Verify anything.** Locating a cell is infrastructure for the span verifier, not
  verification. Nothing here sets `EvidenceVerification`, and nothing builds a
  `ProductAttribute`.
"""

from __future__ import annotations

import io
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from .errors import IngestionError
from .limits import MAX_FILE_BYTES, PDF_MAGIC

#: Bumped when reconstruction could place a word in a different cell. A parser upgrade
#: can shift cell boundaries, and that must be observable rather than inferred.
TABLE_EXTRACTION_VERSION = "table-extract@v1"

ENGINE_NAME = "pdfplumber"

# -- reconstruction constants. Geometry only; no document-specific tuning. --

#: Vertical rules within this many points are the same boundary.
X_CLUSTER_TOLERANCE = 2.0
#: Rule bands closer than this vertically are one table (label row + unit row).
BAND_MERGE_GAP = 3.0
#: Words whose tops differ by less than this share a row.
ROW_TOLERANCE = 3.0
#: Below this many columns a "table" is not worth reconstructing.
MIN_COLUMNS = 3
#: A projected body row must fill at least this many columns to still be a table row.
MIN_FILLED_CELLS = 2
#: How far below a rule frame body rows may be projected, in points.
MAX_PROJECTION_POINTS = 400.0


class TableExtractionStatus(StrEnum):
    """What structured extraction achieved for a page."""

    TABLES_EXTRACTED = "TABLES_EXTRACTED"
    #: The page draws no column ruling. There is nothing to reconstruct from, and
    #: whitespace alone is not evidence of a column boundary.
    NO_TABLE_STRUCTURE = "NO_TABLE_STRUCTURE"
    #: Ruling was found but produced no usable rows. The relationship is *known to be
    #: unrecovered* — callers must withhold rather than fall back to reading text order.
    TABLE_STRUCTURE_UNRESOLVED = "TABLE_STRUCTURE_UNRESOLVED"


class ExtractedCell(BaseModel):
    """One cell. `text` is the words that fell in this column, in reading order."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    row_index: int = Field(ge=0)
    column_index: int = Field(ge=0)
    text: str
    is_header: bool = False


class ExtractedTable(BaseModel):
    """A reconstructed table on one page.

    `header_row_count` rows sit inside the ruling; the rest were projected below it.
    Rows and columns are dense — every row has `column_count` cells, empty ones included —
    so a column index means the same thing on every row.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int = Field(ge=1)
    table_index: int = Field(ge=0)
    engine: str = ENGINE_NAME
    engine_version: str
    strategy_version: str = TABLE_EXTRACTION_VERSION
    bbox: tuple[float, float, float, float] | None = None
    column_count: int = Field(ge=1)
    row_count: int = Field(ge=0)
    header_row_count: int = Field(ge=0)
    cells: tuple[ExtractedCell, ...]
    #: Words inside the row band that fell outside every column. A high count means the
    #: ruling does not span the page's content and the reconstruction is partial.
    words_outside_frame: int = Field(default=0, ge=0)

    def row(self, row_index: int) -> tuple[str, ...]:
        by_col = {c.column_index: c.text for c in self.cells if c.row_index == row_index}
        return tuple(by_col.get(i, "") for i in range(self.column_count))

    def rows(self) -> tuple[tuple[str, ...], ...]:
        return tuple(self.row(i) for i in range(self.row_count))

    def header_rows(self) -> tuple[tuple[str, ...], ...]:
        return tuple(self.row(i) for i in range(self.header_row_count))

    def body_rows(self) -> tuple[tuple[str, ...], ...]:
        return tuple(self.row(i) for i in range(self.header_row_count, self.row_count))

    def find_rows(self, needle: str) -> tuple[int, ...]:
        """Row indices containing `needle` in any cell. Locating, not verifying."""
        return tuple(sorted({c.row_index for c in self.cells if needle in c.text}))


class PageTableExtraction(BaseModel):
    """The structured-table view of one page, or an explicit statement that there is none."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int = Field(ge=1)
    status: TableExtractionStatus
    engine: str = ENGINE_NAME
    engine_version: str
    strategy_version: str = TABLE_EXTRACTION_VERSION
    tables: tuple[ExtractedTable, ...] = ()

    @property
    def has_tables(self) -> bool:
        return bool(self.tables)


def _cluster(values: list[float], tolerance: float) -> list[float]:
    groups: list[list[float]] = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] <= tolerance:
            groups[-1].append(v)
        else:
            groups.append([v])
    return [sum(g) / len(g) for g in groups]


def _rule_frames(page) -> list[dict]:
    """Bands of vertical ruling edges sharing a y-extent, merged when adjacent."""
    verticals = [
        e for e in page.edges if e["orientation"] == "v" and e["x0"] >= 0 and e["x1"] <= page.width
    ]
    bands: list[dict] = []
    for e in sorted(verticals, key=lambda e: e["top"]):
        for band in bands:
            if e["top"] < band["bottom"] and e["bottom"] > band["top"]:
                band["top"] = min(band["top"], e["top"])
                band["bottom"] = max(band["bottom"], e["bottom"])
                band["xs"].append(e["x0"])
                break
        else:
            bands.append({"top": e["top"], "bottom": e["bottom"], "xs": [e["x0"]]})

    bands.sort(key=lambda b: b["top"])
    merged: list[dict] = []
    for band in bands:
        if merged and band["top"] - merged[-1]["bottom"] <= BAND_MERGE_GAP:
            merged[-1]["bottom"] = max(merged[-1]["bottom"], band["bottom"])
            merged[-1]["xs"].extend(band["xs"])
        else:
            merged.append(dict(band))

    frames = []
    for band in merged:
        xs = _cluster(band["xs"], X_CLUSTER_TOLERANCE)
        if len(xs) - 1 >= MIN_COLUMNS and band["bottom"] - band["top"] > 4:
            frames.append({"top": band["top"], "bottom": band["bottom"], "xs": xs})
    return frames


def _column_of(word: dict, xs: list[float]) -> int | None:
    """Column containing the word's midpoint, or None if it falls outside the frame."""
    midpoint = (word["x0"] + word["x1"]) / 2
    for i in range(len(xs) - 1):
        if xs[i] <= midpoint < xs[i + 1]:
            return i
    return None


def _bin_rows(words: list[dict], xs: list[float]) -> list[dict]:
    """Group words into rows by baseline, then into columns by midpoint."""
    grouped: list[dict] = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if grouped and abs(w["top"] - grouped[-1]["top"]) <= ROW_TOLERANCE:
            grouped[-1]["words"].append(w)
        else:
            grouped.append({"top": w["top"], "words": [w]})

    column_count = len(xs) - 1
    rows = []
    for group in grouped:
        buckets: list[list[str]] = [[] for _ in range(column_count)]
        outside = 0
        for w in sorted(group["words"], key=lambda w: w["x0"]):
            index = _column_of(w, xs)
            if index is None:
                outside += 1
            else:
                buckets[index].append(w["text"])
        rows.append(
            {
                "cells": [" ".join(b).strip() for b in buckets],
                "outside": outside,
            }
        )
    return rows


def _build_table(
    page, frame: dict, page_number: int, table_index: int, engine_version: str
) -> ExtractedTable | None:
    xs = frame["xs"]
    words = page.extract_words()
    header_words = [w for w in words if frame["top"] - 1 <= w["top"] < frame["bottom"]]
    body_words = [
        w for w in words if frame["bottom"] <= w["top"] < frame["bottom"] + MAX_PROJECTION_POINTS
    ]

    header = [r for r in _bin_rows(header_words, xs) if any(r["cells"])]
    body = []
    for row in _bin_rows(body_words, xs):
        filled = sum(1 for c in row["cells"] if c)
        if filled == 0:
            continue
        if filled < MIN_FILLED_CELLS:
            break  # ran out of table-shaped rows
        body.append(row)

    if not header and not body:
        return None

    all_rows = header + body
    cells = tuple(
        ExtractedCell(row_index=ri, column_index=ci, text=text, is_header=ri < len(header))
        for ri, row in enumerate(all_rows)
        for ci, text in enumerate(row["cells"])
    )
    return ExtractedTable(
        page_number=page_number,
        table_index=table_index,
        engine_version=engine_version,
        bbox=(
            round(min(xs), 2),
            round(frame["top"], 2),
            round(max(xs), 2),
            round(frame["bottom"], 2),
        ),
        column_count=len(xs) - 1,
        row_count=len(all_rows),
        header_row_count=len(header),
        cells=cells,
        words_outside_frame=sum(r["outside"] for r in all_rows),
    )


def extract_page_tables(data: bytes, page_number: int) -> PageTableExtraction:
    """Reconstruct tables on one page. Opt-in; ingestion never calls this on its own.

    `page_number` is 1-indexed, matching citations and `IngestedPage`.

    Raises `IngestionError` for bytes that are not a PDF or a page that does not exist.
    Never raises because a page merely has no table — that is a status, not an error.
    """
    if not data.startswith(PDF_MAGIC):
        raise IngestionError("not a PDF: missing %PDF- signature")
    if len(data) > MAX_FILE_BYTES:
        raise IngestionError(f"{len(data)} bytes exceeds the {MAX_FILE_BYTES} byte cap")
    if page_number < 1:
        raise IngestionError(f"page_number is 1-indexed; got {page_number}")

    import pdfplumber
    from pdfplumber._version import __version__ as engine_version

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        if page_number > len(pdf.pages):
            raise IngestionError(
                f"page {page_number} requested but the document has {len(pdf.pages)}"
            )
        page = pdf.pages[page_number - 1]
        frames = _rule_frames(page)
        if not frames:
            return PageTableExtraction(
                page_number=page_number,
                status=TableExtractionStatus.NO_TABLE_STRUCTURE,
                engine_version=engine_version,
            )

        tables = []
        for frame in frames:
            table = _build_table(page, frame, page_number, len(tables), engine_version)
            if table is not None:
                tables.append(table)

    if not tables:
        return PageTableExtraction(
            page_number=page_number,
            status=TableExtractionStatus.TABLE_STRUCTURE_UNRESOLVED,
            engine_version=engine_version,
        )
    return PageTableExtraction(
        page_number=page_number,
        status=TableExtractionStatus.TABLES_EXTRACTED,
        engine_version=engine_version,
        tables=tuple(tables),
    )
