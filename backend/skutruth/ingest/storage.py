"""Content-addressed artifact storage.

Layout, one directory per artifact, named by its hash:

    <root>/<sha256>/
        metadata.json     artifact record, minus page text
        original.pdf      the exact bytes that produced the hash
        page-map.json     per-page hashes and character counts
        pages/0001.txt    raw page text, one file per page
        pages/0002.txt

Two roots, exactly as with replay cassettes:

* **runtime** (`data/artifacts/runtime/`) — everything ingestion writes. Gitignored,
  because it will contain third-party manufacturer PDFs that we have every right to
  read locally and no right to redistribute.
* **fixtures** (`data/artifacts/fixtures/`) — documents a person has confirmed are
  safe to publish. Opened read-only, so an ingestion run cannot write into it.

Promotion is a deliberate human copy. That review is the only thing standing between
this repository and a committed copyrighted datasheet.

**Loading validates; it never repairs.** A stored artifact whose bytes, page files, or
hashes disagree with its metadata raises `CorruptArtifactError`. Silently
regenerating on read would mean a citation could be re-derived from whatever is on
disk now rather than from what was actually ingested — which is precisely the
property the hash exists to prevent. Re-ingestion is a separate, explicit act.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .errors import ArtifactNotFoundError, CorruptArtifactError
from .hashing import is_valid_sha256, sha256_bytes, sha256_text
from .models import IngestedArtifact, IngestedPage

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Written here by ingestion. Gitignored.
DEFAULT_RUNTIME_DIR = _REPO_ROOT / "data" / "artifacts" / "runtime"

#: Human-reviewed, redistribution-safe documents that may be committed.
DEFAULT_FIXTURE_DIR = _REPO_ROOT / "data" / "artifacts" / "fixtures"

METADATA_FILE = "metadata.json"
ORIGINAL_FILE = "original.pdf"
PAGE_MAP_FILE = "page-map.json"
PAGES_DIR = "pages"

#: Bumped if the on-disk layout changes.
STORAGE_VERSION = "artifact-store@v1"


class PageMapEntry(BaseModel):
    """The per-page record used to detect drift without loading every page file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page_number: int = Field(ge=1)
    text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    character_count: int = Field(ge=0)
    status: str
    filename: str


def page_filename(page_number: int) -> str:
    return f"{page_number:04d}.txt"


class ArtifactStore:
    """Ingested artifacts on disk, addressed by content hash.

    `writable=False` makes the store refuse writes, which is how the curated fixture
    directory is protected from an accidental ingestion run.
    """

    def __init__(self, root: Path | str, *, writable: bool = True) -> None:
        self.root = Path(root)
        self.writable = writable

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return f"ArtifactStore({str(self.root)!r}, writable={self.writable})"

    def path_for(self, sha256: str) -> Path:
        if not is_valid_sha256(sha256):
            # Hashes become directory names, so anything that is not a bare digest is
            # rejected before it can reach into the filesystem.
            raise CorruptArtifactError(sha256, "not a valid lowercase hex SHA-256 digest")
        return self.root / sha256

    def exists(self, sha256: str) -> bool:
        return (self.path_for(sha256) / METADATA_FILE).is_file()

    def hashes(self) -> tuple[str, ...]:
        if not self.root.is_dir():
            return ()
        return tuple(
            sorted(
                p.name
                for p in self.root.iterdir()
                if p.is_dir() and is_valid_sha256(p.name) and (p / METADATA_FILE).is_file()
            )
        )

    def original_path(self, sha256: str) -> Path:
        return self.path_for(sha256) / ORIGINAL_FILE

    # -- writing ------------------------------------------------------------

    def save(self, artifact: IngestedArtifact, original_bytes: bytes) -> Path:
        """Store an artifact and the exact bytes it was derived from.

        Idempotent by construction: the directory is the content hash, so ingesting
        identical bytes twice writes the same place rather than creating a second
        artifact identity. Derived files are rewritten deterministically.

        The original is written byte-for-byte and its hash re-verified afterwards —
        never re-saved through the parser, never recompressed. The evidence artifact
        is the original byte sequence.
        """
        if not self.writable:
            raise CorruptArtifactError(
                artifact.sha256,
                "this artifact store is read-only; curated fixtures are promoted from "
                "the runtime directory by a reviewed, deliberate copy",
            )
        actual = sha256_bytes(original_bytes)
        if actual != artifact.sha256:
            raise CorruptArtifactError(
                artifact.sha256, f"supplied bytes hash to {actual}, not the artifact's digest"
            )

        directory = self.path_for(artifact.sha256)
        pages_dir = directory / PAGES_DIR
        pages_dir.mkdir(parents=True, exist_ok=True)

        _atomic_write_bytes(directory / ORIGINAL_FILE, original_bytes)
        stored = (directory / ORIGINAL_FILE).read_bytes()
        if sha256_bytes(stored) != artifact.sha256:  # pragma: no cover - filesystem fault
            raise CorruptArtifactError(
                artifact.sha256, "stored original.pdf does not hash to the artifact digest"
            )

        for page in artifact.pages:
            _atomic_write_text(pages_dir / page_filename(page.page_number), page.raw_text)

        page_map = [
            PageMapEntry(
                page_number=p.page_number,
                text_sha256=p.text_sha256,
                character_count=p.character_count,
                status=p.status.value,
                filename=page_filename(p.page_number),
            ).model_dump()
            for p in artifact.pages
        ]
        _atomic_write_text(
            directory / PAGE_MAP_FILE,
            json.dumps(
                {"storage_version": STORAGE_VERSION, "pages": page_map},
                indent=2,
                sort_keys=True,
            )
            + "\n",
        )

        metadata = artifact.model_dump(mode="json", exclude={"pages"})
        metadata["storage_version"] = STORAGE_VERSION
        _atomic_write_text(
            directory / METADATA_FILE,
            json.dumps(metadata, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        )
        return directory

    # -- reading ------------------------------------------------------------

    def load(self, sha256: str, *, verify_original: bool = True) -> IngestedArtifact:
        """Load a stored artifact, validating everything before returning it.

        Checks the original's hash, the page map's completeness, and every page file
        against its recorded hash. Any disagreement raises `CorruptArtifactError`.
        Nothing is regenerated.

        `verify_original=False` skips only the re-hash of the PDF, for callers that
        need page text from a large artifact repeatedly; the page hashes are still
        checked, so text drift is still caught.
        """
        directory = self.path_for(sha256)
        if not (directory / METADATA_FILE).is_file():
            raise ArtifactNotFoundError(sha256, str(self.root))

        metadata = _read_json(directory / METADATA_FILE, sha256, "metadata.json")
        if not isinstance(metadata, dict):
            raise CorruptArtifactError(sha256, "metadata.json is not an object")
        metadata.pop("storage_version", None)

        recorded_sha = metadata.get("sha256")
        if recorded_sha != sha256:
            raise CorruptArtifactError(
                sha256, f"metadata records sha256 {recorded_sha!r}, but it is stored under {sha256}"
            )

        original = directory / ORIGINAL_FILE
        if not original.is_file():
            raise CorruptArtifactError(sha256, "original.pdf is missing")
        if verify_original:
            actual = sha256_bytes(original.read_bytes())
            if actual != sha256:
                raise CorruptArtifactError(
                    sha256, f"original.pdf hashes to {actual}; the stored bytes have changed"
                )

        page_map_raw = _read_json(directory / PAGE_MAP_FILE, sha256, PAGE_MAP_FILE)
        if not isinstance(page_map_raw, dict) or "pages" not in page_map_raw:
            raise CorruptArtifactError(sha256, "page-map.json is malformed")

        try:
            entries = [PageMapEntry.model_validate(e) for e in page_map_raw["pages"]]
        except ValidationError as exc:
            raise CorruptArtifactError(sha256, f"page-map.json failed validation: {exc}") from exc

        expected_count = metadata.get("page_count")
        if expected_count != len(entries):
            raise CorruptArtifactError(
                sha256,
                f"metadata records {expected_count} pages but the page map has {len(entries)}",
            )
        numbers = [e.page_number for e in entries]
        if numbers != list(range(1, len(entries) + 1)):
            raise CorruptArtifactError(
                sha256, "page map is not a complete 1..n sequence without duplicates"
            )

        pages = [_load_page(directory, entry, sha256) for entry in entries]
        metadata["pages"] = [p.model_dump(mode="json") for p in pages]

        try:
            return IngestedArtifact.model_validate(metadata)
        except ValidationError as exc:
            raise CorruptArtifactError(sha256, f"artifact failed validation: {exc}") from exc

    def load_original_bytes(self, sha256: str) -> bytes:
        """The exact stored bytes, re-verified against the hash before returning."""
        path = self.original_path(sha256)
        if not path.is_file():
            raise ArtifactNotFoundError(sha256, str(self.root))
        data = path.read_bytes()
        actual = sha256_bytes(data)
        if actual != sha256:
            raise CorruptArtifactError(sha256, f"original.pdf hashes to {actual}")
        return data

    def delete(self, sha256: str) -> None:
        if not self.writable:
            raise CorruptArtifactError(sha256, "store is read-only")
        directory = self.path_for(sha256)
        if directory.is_dir():
            shutil.rmtree(directory)


def _load_page(directory: Path, entry: PageMapEntry, sha256: str) -> IngestedPage:
    from .models import ExtractionStatus
    from .text import build_search_text

    path = directory / PAGES_DIR / entry.filename
    if not path.is_file():
        raise CorruptArtifactError(sha256, f"page file {entry.filename} is missing")
    raw = path.read_text(encoding="utf-8")
    actual = sha256_text(raw)
    if actual != entry.text_sha256:
        raise CorruptArtifactError(
            sha256,
            f"page {entry.page_number} text hashes to {actual[:12]}…, but the page map "
            f"records {entry.text_sha256[:12]}…; the stored text has changed",
        )
    if len(raw) != entry.character_count:
        raise CorruptArtifactError(
            sha256,
            f"page {entry.page_number} has {len(raw)} characters, page map records "
            f"{entry.character_count}",
        )
    return IngestedPage(
        page_number=entry.page_number,
        raw_text=raw,
        search_text=build_search_text(raw),
        text_sha256=entry.text_sha256,
        character_count=entry.character_count,
        status=ExtractionStatus(entry.status),
    )


def _read_json(path: Path, sha256: str, label: str):
    if not path.is_file():
        raise CorruptArtifactError(sha256, f"{label} is missing")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorruptArtifactError(sha256, f"{label} is unreadable JSON: {exc}") from exc


def _atomic_write_bytes(path: Path, data: bytes) -> None:
    """Write via a same-directory temporary file, then rename.

    An interrupted process leaves a stray temp file, never a truncated original.pdf
    that would hash to something plausible-looking.
    """
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}-", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _atomic_write_text(path: Path, text: str) -> None:
    _atomic_write_bytes(path, text.encode("utf-8"))


def runtime_store() -> ArtifactStore:
    """The writable store ingestion records into."""
    return ArtifactStore(DEFAULT_RUNTIME_DIR, writable=True)


def fixture_store() -> ArtifactStore:
    """The curated store, read-only so ingestion cannot write into it."""
    return ArtifactStore(DEFAULT_FIXTURE_DIR, writable=False)


def ingest_and_store(
    data: bytes,
    store: ArtifactStore,
    *,
    source=None,
    limits=None,
    ingested_at: datetime | None = None,
) -> IngestedArtifact:
    """Ingest bytes and persist the result. Idempotent on identical bytes."""
    from .pdf import ingest_pdf_bytes

    artifact = ingest_pdf_bytes(data, source=source, limits=limits, ingested_at=ingested_at)
    store.save(artifact, data)
    return artifact
