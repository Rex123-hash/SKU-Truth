"""Table evidence units.

A table row and the header cells above it are *structurally* related, so combining them
is not Frankenstein evidence — the page itself asserts that relationship by drawing the
column. That is the one place the one-evidence-unit rule admits more than a single line.

## Row identity is a gate, not a hint

A correct number in the wrong row is a wrong answer. Before a row may support a claim,
some cell in it must carry a reference that conservatively matches the target MPN, using
the frozen `canonical_mpn` comparison — case and whitespace only.

That deliberately makes a family placeholder such as `LC1D18pp` fail to support
`LC1D18P7`. The placeholder is a *base* reference; treating it as its own child is exactly
the family-to-exact leap the identity gate exists to prevent.
"""

from __future__ import annotations

from dataclasses import dataclass

from skutruth.contracts.mpn import canonical_mpn
from skutruth.ingest.tables import ExtractedTable, PageTableExtraction, TableExtractionStatus


@dataclass(frozen=True, slots=True)
class TableEvidence:
    """One body row plus the header cells structurally above its populated columns."""

    table_index: int
    row_index: int
    row: tuple[str, ...]
    headers: tuple[tuple[str, ...], ...]
    identity_cell: str
    identity_column: int
    bbox: tuple[float, float, float, float] | None

    def text(self) -> str:
        """A flat rendering of the unit, header context first. For matching only."""
        header_text = " ".join(cell for rows in self.headers for cell in rows if cell.strip())
        row_text = " ".join(cell for cell in self.row if cell.strip())
        return f"{header_text} {row_text}".strip()

    def column_headers(self, column_index: int) -> tuple[str, ...]:
        """Every header cell sitting above one column, top to bottom."""
        return tuple(
            rows[column_index]
            for rows in self.headers
            if column_index < len(rows) and rows[column_index].strip()
        )


def _row_identity(table: ExtractedTable, row_index: int, exact_mpn: str) -> int | None:
    """Index of the cell in this row whose reference matches the target, if any."""
    target = canonical_mpn(exact_mpn)
    if target is None:
        return None
    for cell in table.cells:
        if cell.row_index != row_index or cell.is_header:
            continue
        if canonical_mpn(cell.text) == target:
            return cell.column_index
    return None


def find_row_evidence(extraction: PageTableExtraction, exact_mpn: str) -> tuple[TableEvidence, ...]:
    """Body rows on this page that identify themselves as the target product."""
    if extraction.status is not TableExtractionStatus.TABLES_EXTRACTED:
        return ()

    found: list[TableEvidence] = []
    for table in extraction.tables:
        headers = table.header_rows()
        for row_index in range(table.header_row_count, table.row_count):
            column = _row_identity(table, row_index, exact_mpn)
            if column is None:
                continue
            found.append(
                TableEvidence(
                    table_index=table.table_index,
                    row_index=row_index,
                    row=table.row(row_index),
                    headers=headers,
                    identity_cell=table.row(row_index)[column],
                    identity_column=column,
                    bbox=table.bbox,
                )
            )
    return tuple(found)


__all__ = ["TableEvidence", "find_row_evidence"]
