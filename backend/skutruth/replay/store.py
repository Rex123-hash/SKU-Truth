"""Filesystem cassette storage.

Two directories, deliberately distinct:

* **runtime** (`data/replay/runtime/`) — everything LIVE mode records. Gitignored.
  Recordings land here first because they may contain licensed third-party content
  or provider material nobody has reviewed yet.
* **fixtures** (`data/replay/fixtures/`) — curated recordings that have been looked
  at by a person and are intended for commit.

Promotion from one to the other is a deliberate human copy, not an automatic step,
and the fixture store is opened read-only by default so a live run cannot write into
it by accident. Reviewing a recording before it enters the repository is the only
thing standing between us and committing a credential or someone else's copyrighted
datasheet.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from pydantic import ValidationError

from .errors import InvalidCassetteError, ReplayMissError
from .keys import is_valid_key
from .models import CASSETTE_VERSION, Cassette, InteractionRequest

_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Recorded here by LIVE runs. Gitignored — see .gitignore.
DEFAULT_RUNTIME_DIR = _REPO_ROOT / "data" / "replay" / "runtime"

#: Human-reviewed recordings that may be committed.
DEFAULT_FIXTURE_DIR = _REPO_ROOT / "data" / "replay" / "fixtures"


class CassetteStore:
    """Cassettes on disk, one JSON file per key.

    `writable=False` makes the store refuse writes outright, which is how the
    curated fixture directory is protected from an accidental live recording.
    """

    def __init__(self, root: Path | str, *, writable: bool = True) -> None:
        self.root = Path(root)
        self.writable = writable

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return f"CassetteStore({str(self.root)!r}, writable={self.writable})"

    def path_for(self, key: str) -> Path:
        if not is_valid_key(key):
            # Keys become filenames, so anything that is not a bare digest is
            # rejected before it can reach into the filesystem.
            raise InvalidCassetteError(str(self.root), f"{key!r} is not a valid cassette key")
        return self.root / f"{key}.json"

    def exists(self, key: str) -> bool:
        return self.path_for(key).is_file()

    def keys(self) -> tuple[str, ...]:
        if not self.root.is_dir():
            return ()
        return tuple(sorted(p.stem for p in self.root.glob("*.json") if is_valid_key(p.stem)))

    # -- reading ------------------------------------------------------------

    def load(self, key: str) -> Cassette:
        """Load and fully validate a cassette. Never returns something unchecked."""
        path = self.path_for(key)
        if not path.is_file():
            raise ReplayMissError(
                key, provider="unknown", model="unknown", searched=str(self.root)
            )
        return self._read(path, expected_key=key)

    def load_for(self, request: InteractionRequest) -> Cassette:
        """Load the cassette for a request, with a diagnosable miss on absence."""
        key = request.cassette_key()
        path = self.path_for(key)
        if not path.is_file():
            raise ReplayMissError(
                key,
                provider=request.provider,
                model=request.model,
                searched=str(self.root),
                prompt_version=request.prompt_version,
                schema_version=request.schema_version,
            )
        cassette = self._read(path, expected_key=key)
        if cassette.request.cassette_key() != key:  # pragma: no cover - guarded in model
            raise InvalidCassetteError(str(path), "stored request derives a different key")
        return cassette

    def _read(self, path: Path, *, expected_key: str) -> Cassette:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise InvalidCassetteError(str(path), f"unreadable JSON: {exc}") from exc
        except OSError as exc:  # pragma: no cover - filesystem failure
            raise InvalidCassetteError(str(path), f"unreadable file: {exc}") from exc

        if not isinstance(raw, dict):
            raise InvalidCassetteError(str(path), "top level is not an object")

        version = raw.get("cassette_version")
        if version != CASSETTE_VERSION:
            raise InvalidCassetteError(
                str(path),
                f"format version {version!r} is not the supported {CASSETTE_VERSION!r}",
            )

        try:
            cassette = Cassette.model_validate(raw)
        except ValidationError as exc:
            raise InvalidCassetteError(str(path), f"failed validation: {exc}") from exc

        if cassette.key != expected_key:
            raise InvalidCassetteError(
                str(path),
                f"stored key {cassette.key} does not match filename key {expected_key}",
            )
        return cassette

    # -- writing ------------------------------------------------------------

    def save(self, cassette: Cassette) -> Path:
        """Write a cassette atomically. Returns the final path.

        The temporary file is created in the destination directory so `os.replace`
        is a same-filesystem rename, which is atomic. A process killed mid-write
        leaves a stray temporary file, never a truncated cassette that would load
        and validate as though it were whole.
        """
        if not self.writable:
            raise InvalidCassetteError(
                str(self.root),
                "this cassette store is read-only; curated fixtures are promoted from "
                "the runtime directory by a reviewed, deliberate copy",
            )
        path = self.path_for(cassette.key)
        self.root.mkdir(parents=True, exist_ok=True)
        payload = cassette.model_dump(mode="json")
        text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"

        fd, tmp_name = tempfile.mkstemp(
            dir=self.root, prefix=f".{cassette.key[:12]}-", suffix=".tmp"
        )
        tmp = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(text)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise
        return path


def runtime_store() -> CassetteStore:
    """The writable store LIVE runs record into."""
    return CassetteStore(DEFAULT_RUNTIME_DIR, writable=True)


def fixture_store() -> CassetteStore:
    """The curated store, read-only so live runs cannot write into it."""
    return CassetteStore(DEFAULT_FIXTURE_DIR, writable=False)
