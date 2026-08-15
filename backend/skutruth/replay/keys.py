"""Deterministic cassette keys.

    canonical interaction request  ->  canonical JSON  ->  SHA-256  ->  cassette key

The key answers exactly one question: *would replaying this cassette reproduce the
same logical call?* Everything that changes the answer belongs in it, and everything
that does not must stay out — a timestamp or a run id in the key would give every
interaction a fresh key and make replay useless.

`repr()` is never used as the canonical form. It is not stable across Python
versions, it varies with dict insertion order, and it round-trips nothing.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

#: Bumped whenever the key material or the canonicalisation changes. It participates
#: in the digest, so a bump automatically separates old and new keys rather than
#: silently reusing stale cassettes under new semantics.
KEY_VERSION = "record-replay-key@v1"

#: 64 lowercase hex characters. Enforced before a key is ever used as a filename.
KEY_PATTERN = r"^[0-9a-f]{64}$"


def canonical_json(value: Any) -> str:
    """Byte-stable JSON: sorted keys, no incidental whitespace, UTF-8 preserved.

    Sorting keys is what makes dict construction order irrelevant, so two callers
    that build the same payload differently still produce the same key.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(material: Any) -> str:
    return hashlib.sha256(canonical_json(material).encode("utf-8")).hexdigest()


def is_valid_key(key: str) -> bool:
    import re

    return bool(re.fullmatch(KEY_PATTERN, key))
