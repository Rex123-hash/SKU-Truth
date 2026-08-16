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


def build_pdf(pages: list[str], *, font: str = "Helvetica") -> bytes:
    """A valid PDF with one text line per page, byte-identical for identical input."""
    if not pages:
        raise ValueError("a PDF needs at least one page")

    body: dict[int, bytes] = {}
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(len(pages)))
    body[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    body[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(pages)} >>".encode()
    body[3] = f"<< /Type /Font /Subtype /Type1 /BaseFont /{font} >>".encode()

    for i, text in enumerate(pages):
        page_obj, content_obj = 4 + 2 * i, 5 + 2 * i
        body[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_obj} 0 R >>"
        ).encode()
        stream = f"BT /F1 12 Tf 72 720 Td ({_escape(text)}) Tj ET".encode()
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


#: The standard three-page synthetic datasheet used across ingestion tests.
DATASHEET_PAGES = [
    "TESTCO INDUSTRIAL CONTACTOR",
    "Rated operation current: 18 A at AC-3, 400 V",
    "Coil supply: 230 V AC",
]


def datasheet_pdf() -> bytes:
    return build_pdf(DATASHEET_PAGES)
