"""Reading the raw organizer catalogue export.

The currently supplied input has six columns. They are validated by *name*, never by
position, and the file is streamed so the same reader works on a catalogue far larger
than the 1,000-row sample.

## Raw and cleaned are both kept

`RawProductRow.raw` holds exactly what the file said. The cleaned accessors strip
whitespace and turn placeholders into `None`. Both matter: "the source wrote
`-- Unbranded --`" and "the source wrote nothing" are different facts, and only the raw
form can distinguish them for a reviewer.

## Extra columns are preserved, not adopted

An unrecognised header is kept in `extra` rather than rejected, so a later organizer
export with more columns still loads. It is deliberately *not* promoted to a known field:
guessing that a new `Brand2` column means the same thing as `E1_Brand` is exactly the
kind of assumption this layer exists to avoid.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

from .errors import DuplicateColumn, MalformedRowError, MissingRequiredColumn
from .manufacturer import ParsedManufacturer, parse_part_manuf
from .placeholders import clean

#: The columns the organizer input is contracted to provide.
REQUIRED_COLUMNS: tuple[str, ...] = (
    "Mfg_Part_Num",
    "Part_Desc",
    "E1_Brand",
    "Unilog_Brand",
    "DIB_Brand",
    "Part_Manuf",
)


@dataclass(frozen=True, slots=True)
class RawProductRow:
    """One catalogue row: what the file said, plus what it means."""

    row_number: int
    raw: Mapping[str, str]
    extra: Mapping[str, str] = field(default_factory=dict)

    def raw_value(self, column: str) -> str:
        return self.raw.get(column, "")

    def cleaned(self, column: str) -> str | None:
        """Trimmed value, or `None` for empty and placeholder."""
        return clean(column, self.raw.get(column))

    # -- cleaned accessors for the contracted columns ------------------------

    @property
    def mfg_part_num(self) -> str | None:
        return self.cleaned("Mfg_Part_Num")

    @property
    def part_desc(self) -> str | None:
        return self.cleaned("Part_Desc")

    @property
    def e1_brand(self) -> str | None:
        return self.cleaned("E1_Brand")

    @property
    def unilog_brand(self) -> str | None:
        return self.cleaned("Unilog_Brand")

    @property
    def dib_brand(self) -> str | None:
        return self.cleaned("DIB_Brand")

    @property
    def part_manuf(self) -> str | None:
        return self.cleaned("Part_Manuf")

    @property
    def manufacturer(self) -> ParsedManufacturer:
        """The structural reading of `Part_Manuf`. Never canonicalised."""
        return parse_part_manuf(self.raw.get("Part_Manuf"))

    @property
    def brand_signals(self) -> tuple[str, ...]:
        """Non-placeholder brand values, in file order. No preference is expressed.

        Which signal wins is a canonicalisation decision that needs the approved
        manufacturer/brand master, so this only reports what survived cleaning.
        """
        return tuple(v for v in (self.e1_brand, self.unilog_brand, self.dib_brand) if v)


def validate_input_header(header: list[str]) -> tuple[str, ...]:
    """Check the header and return the extra (non-required) column names.

    Duplicates are rejected outright — a repeated name makes a value unattributable, and
    `csv.DictReader` would silently keep only the last one.
    """
    seen: set[str] = set()
    duplicates: list[str] = []
    for name in header:
        if name in seen:
            duplicates.append(name)
        seen.add(name)
    if duplicates:
        raise DuplicateColumn(
            f"input header repeats {sorted(set(duplicates))}; a value in a duplicated "
            f"column cannot be attributed to one field"
        )

    missing = [c for c in REQUIRED_COLUMNS if c not in seen]
    if missing:
        raise MissingRequiredColumn(
            f"input is missing required column(s) {missing}; columns are matched by name, "
            f"never by position"
        )
    return tuple(n for n in header if n not in set(REQUIRED_COLUMNS))


def read_rows(handle: IO[str]) -> Iterator[RawProductRow]:
    """Stream rows from an open text handle. The handle must be opened `newline=''`."""
    reader = csv.reader(handle)
    try:
        header = next(reader)
    except StopIteration:
        return
    # A UTF-8 BOM survives as a leading ZWNBSP when the file was not opened as utf-8-sig.
    if header and header[0].startswith("﻿"):
        header[0] = header[0].lstrip("﻿")

    extras = validate_input_header(header)
    width = len(header)

    for index, values in enumerate(reader, start=1):
        if not values:
            continue  # a stray blank line is not a malformed record
        if len(values) != width:
            raise MalformedRowError(
                f"row {index} has {len(values)} fields but the header declares {width}"
            )
        record = dict(zip(header, values, strict=True))
        yield RawProductRow(
            row_number=index,
            raw=record,
            extra={k: record[k] for k in extras},
        )


def read_unilog_input(path: str | Path) -> Iterator[RawProductRow]:
    """Stream `RawProductRow`s from an organizer input CSV.

    Bounded memory: rows are yielded as they are read rather than materialised.
    """
    with Path(path).open(encoding="utf-8-sig", newline="") as handle:
        yield from read_rows(handle)


__all__ = [
    "REQUIRED_COLUMNS",
    "RawProductRow",
    "read_rows",
    "read_unilog_input",
    "validate_input_header",
]
