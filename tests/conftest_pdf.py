"""A minimal, deterministic PDF builder for tests.

Written by hand rather than pulled in as a dependency: emitting a valid single-font
PDF is about eighty lines, and adding a generation library to the project purely to
make fixtures would be a poor trade.

Every document produced here is obviously synthetic. `TESTCO` is not a manufacturer,
and the figures below are structural filler, not product truth. **No real
manufacturer PDF is downloaded or committed for tests.**
"""

from __future__ import annotations


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def _encode_stream(text: str) -> bytes:
    """Encode a content stream as cp1252 to match the declared WinAnsiEncoding.

    Writing UTF-8 bytes into a PDF literal string would store `°` as two mojibake
    characters, so a fixture exercising units like `°C` would test a corruption
    rather than the real thing. Unmappable characters become `?` loudly.
    """
    return text.encode("cp1252", errors="replace")


def build_pdf(pages: list[str], *, font: str = "Helvetica") -> bytes:
    """A valid PDF with one text line per page, byte-identical for identical input."""
    if not pages:
        raise ValueError("a PDF needs at least one page")

    body: dict[int, bytes] = {}
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    body[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    body[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    body[3] = (
        f"<< /Type /Font /Subtype /Type1 /BaseFont /{font} /Encoding /WinAnsiEncoding >>"
    ).encode()

    for i, text in enumerate(pages):
        page_obj, content_obj = 4 + 2 * i, 5 + 2 * i
        body[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode()
        stream = _encode_stream(f"BT /F1 12 Tf 72 720 Td ({_escape(text)}) Tj ET")
        body[content_obj] = b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream)

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(body):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + body[num] + b"\nendobj\n"

    xref_at = len(out)
    total = max(body) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % total
    for num in range(1, total):
        out += b"%010d 00000 n \n" % offsets[num]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (total, xref_at)
    return bytes(out)


def build_imageless_pdf(page_count: int = 1) -> bytes:
    """Pages with no text content stream, standing in for a scanned document."""
    body: dict[int, bytes] = {}
    kids = " ".join(f"{3 + i} 0 R" for i in range(page_count))
    body[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    body[2] = f"<< /Type /Pages /Kids [{kids}] /Count {page_count} >>".encode()
    for i in range(page_count):
        body[3 + i] = b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>"

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(body):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + body[num] + b"\nendobj\n"
    xref_at = len(out)
    total = max(body) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % total
    for num in range(1, total):
        out += b"%010d 00000 n \n" % offsets[num]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (total, xref_at)
    return bytes(out)


def build_ruled_table_pdf(
    rules: list[tuple[float, float, float]],
    texts: list[tuple[float, float, str]],
    *,
    width: int = 612,
    height: int = 792,
) -> bytes:
    """A page with vertical ruling lines and positioned text.

    `rules` are `(x, y_bottom, y_top)` stroked vertical lines — the column boundaries a
    real catalogue draws. `texts` are `(x, y, string)`. Coordinates are PDF user space,
    so y grows upward from the bottom of the page.

    This exists so table-reconstruction tests never need a real manufacturer document.
    """
    ops = ["0.5 w"]
    for x, y0, y1 in rules:
        ops.append(f"{x} {y0} m {x} {y1} l S")
    for x, y, text in texts:
        ops.append(f"BT /F1 8 Tf {x} {y} Td ({_escape(text)}) Tj ET")
    stream = "\n".join(ops).encode()

    body: dict[int, bytes] = {
        1: b"<< /Type /Catalog /Pages 2 0 R >>",
        2: b"<< /Type /Pages /Kids [4 0 R] /Count 1 >>",
        3: b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
        4: (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {width} {height}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents 5 0 R >>"
        ).encode(),
        5: b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream),
    }

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for num in sorted(body):
        offsets[num] = len(out)
        out += b"%d 0 obj\n" % num + body[num] + b"\nendobj\n"
    xref_at = len(out)
    total = max(body) + 1
    out += b"xref\n0 %d\n0000000000 65535 f \n" % total
    for num in range(1, total):
        out += b"%010d 00000 n \n" % offsets[num]
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (total, xref_at)
    return bytes(out)


#: A synthetic stand-in for the catalogue layout that defeats pypdf: a header band whose
#: column boundaries are drawn as rules, grouped voltage labels stacked two-deep in one
#: column, and unruled data rows below. TESTCO is not a manufacturer and these figures
#: are structural filler, not product truth.
GROUPED_HEADER_RULES = [(x, 700.0, 740.0) for x in (60, 160, 260, 360, 460)]
GROUPED_HEADER_TEXTS = [
    (65, 728, "220 V"),
    (165, 728, "380 V"),
    (265, 728, "500 V"),
    (65, 715, "230 V"),
    (165, 715, "400 V"),
    (65, 704, "kW"),
    (165, 704, "kW"),
    (265, 704, "kW"),
    (365, 704, "Reference"),
    # unruled body rows, projected down the same boundaries
    (65, 685, "4"),
    (165, 685, "7.5"),
    (265, 685, "10"),
    (365, 685, "AAA111"),
    (65, 670, "5.5"),
    (165, 670, "11"),
    (265, 670, "15"),
    (365, 670, "BBB222"),
]


def grouped_header_pdf() -> bytes:
    """The synthetic analogue of the real failure page."""
    return build_ruled_table_pdf(GROUPED_HEADER_RULES, GROUPED_HEADER_TEXTS)


#: The standard three-page synthetic datasheet used across ingestion tests.
DATASHEET_PAGES = [
    "TESTCO INDUSTRIAL CONTACTOR",
    "Rated operation current: 18 A at AC-3, 400 V",
    "Coil supply: 230 V AC",
]


def datasheet_pdf() -> bytes:
    return build_pdf(DATASHEET_PAGES)
