"""Content addressing.

The artifact hash is taken over the **original document bytes**, never over extracted
text. Text extraction depends on the parser and its version; the bytes do not. A
citation points at a byte sequence, and that is what has to be identifiable.
"""

from __future__ import annotations

import hashlib
import re

SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def sha256_bytes(data: bytes) -> str:
    """Lowercase hex SHA-256 of exactly these bytes."""
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    """SHA-256 of text, over its UTF-8 encoding.

    Used for page text, where the point is to detect a change in what the parser
    produced. Distinct in purpose from the artifact hash: this one is expected to
    change when the parser is upgraded, and that change is the signal.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_valid_sha256(value: str) -> bool:
    return bool(SHA256_PATTERN.fullmatch(value))


def artifact_id(sha256: str) -> str:
    """The stable identifier for an artifact, derived from its content.

    Content-addressed on purpose. A random UUID would make the same document ingested
    twice into two different pieces of evidence, and would let evidence identity drift
    from the thing it identifies. Ingesting identical bytes must always yield the same
    artifact.
    """
    if not is_valid_sha256(sha256):
        raise ValueError(f"{sha256!r} is not a lowercase hex SHA-256 digest")
    return f"sha256:{sha256}"


def sha256_from_artifact_id(value: str) -> str:
    if not value.startswith("sha256:"):
        raise ValueError(f"{value!r} is not a content-addressed artifact id")
    digest = value.removeprefix("sha256:")
    if not is_valid_sha256(digest):
        raise ValueError(f"{value!r} does not carry a valid SHA-256 digest")
    return digest
