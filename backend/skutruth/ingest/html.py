"""Deterministic, network-free HTML snapshot ingestion.

Only the bytes supplied by discovery are parsed. The standard-library parser executes no
JavaScript, loads no subresources, follows no frames, and has no network capability.
Parsed metadata remains source data; this module establishes neither product identity nor
attribute truth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .errors import DocumentTooLargeError, EmptyDocumentError, MalformedDocumentError
from .hashing import artifact_id, sha256_bytes
from .models import ArtifactKind, SourceFragmentKind, SourceMetadata

HTML_INGESTION_VERSION = "html-ingest@v1"
HTML_PARSER_NAME = "python.html.parser"
HTML_PARSER_VERSION = "stdlib"
HTML_MEDIA_TYPES = frozenset({"text/html", "application/xhtml+xml"})
MAX_HTML_BYTES = 5 * 1024 * 1024
MAX_HTML_ELEMENTS = 100_000
MAX_VISIBLE_TEXT_CHARS = 2_000_000
MAX_JSONLD_BLOCKS = 100


@dataclass(frozen=True, slots=True)
class HtmlIngestionLimits:
    max_html_bytes: int = MAX_HTML_BYTES
    max_elements: int = MAX_HTML_ELEMENTS
    max_visible_text_chars: int = MAX_VISIBLE_TEXT_CHARS
    max_jsonld_blocks: int = MAX_JSONLD_BLOCKS


DEFAULT_HTML_LIMITS = HtmlIngestionLimits()


class HtmlEvidenceLocator(BaseModel):
    """A stable address into derived HTML text or one JSON-LD block."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: SourceFragmentKind
    element_index: int | None = Field(default=None, ge=0)
    char_start: int | None = Field(default=None, ge=0)
    char_end: int | None = Field(default=None, ge=0)
    jsonld_block_index: int | None = Field(default=None, ge=0)
    json_pointer: str | None = None

    @model_validator(mode="after")
    def _matches_address_space(self) -> HtmlEvidenceLocator:
        if self.kind is SourceFragmentKind.HTML_TEXT:
            if self.element_index is None or self.char_start is None or self.char_end is None:
                raise ValueError("HTML_TEXT requires element index and character offsets")
            if self.char_end < self.char_start:
                raise ValueError("char_end precedes char_start")
            if self.jsonld_block_index is not None or self.json_pointer is not None:
                raise ValueError("HTML_TEXT cannot carry a JSON-LD address")
        elif self.kind is SourceFragmentKind.HTML_JSONLD:
            if self.jsonld_block_index is None:
                raise ValueError("HTML_JSONLD requires a block index")
            if (
                self.element_index is not None
                or self.char_start is not None
                or self.char_end is not None
            ):
                raise ValueError("HTML_JSONLD cannot carry visible-text offsets")
        else:
            raise ValueError("HtmlEvidenceLocator cannot address a PDF page")
        return self


class HtmlTextFragment(BaseModel):
    """One normalized visible text node and its offsets in ``visible_text``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: str = Field(min_length=1)
    locator: HtmlEvidenceLocator


class HtmlJsonLdBlock(BaseModel):
    """One JSON-LD script, preserved independently whether valid or malformed."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw_text: str
    parsed: Any = None
    parse_error: str | None = None
    locator: HtmlEvidenceLocator

    @model_validator(mode="after")
    def _parse_state_is_unambiguous(self) -> HtmlJsonLdBlock:
        if self.parse_error is not None and self.parsed is not None:
            raise ValueError("a malformed JSON-LD block cannot also carry parsed data")
        return self


class HtmlMetadata(BaseModel):
    """Standard document metadata, copied from the snapshot and never trusted as fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    description: str | None = None
    open_graph_title: str | None = None
    open_graph_description: str | None = None


class HtmlArtifactContent(BaseModel):
    """Small read model for later evidence extraction, not an AttributeCandidate."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: str | None = None
    canonical_url: str | None = None
    visible_text: str = ""
    text_fragments: tuple[HtmlTextFragment, ...] = ()
    jsonld_blocks: tuple[HtmlJsonLdBlock, ...] = ()
    metadata: HtmlMetadata = Field(default_factory=HtmlMetadata)

    @model_validator(mode="after")
    def _text_locators_point_into_visible_text(self) -> HtmlArtifactContent:
        for fragment in self.text_fragments:
            locator = fragment.locator
            assert locator.char_start is not None and locator.char_end is not None
            if self.visible_text[locator.char_start : locator.char_end] != fragment.text:
                raise ValueError("HTML text fragment offsets do not match visible_text")
        return self


def html_content_sha256(content: HtmlArtifactContent) -> str:
    payload = json.dumps(
        content.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


class HtmlArtifact(BaseModel):
    """Original HTML bytes plus a deterministic, independently checked read model."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_kind: ArtifactKind = ArtifactKind.HTML
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$", description="Over original HTML bytes")
    media_type: str
    byte_size: int = Field(ge=1)
    source: SourceMetadata = Field(default_factory=SourceMetadata)
    final_authority: str | None = None
    content: HtmlArtifactContent
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ingested_at: datetime
    ingestion_version: str = HTML_INGESTION_VERSION
    parser_name: str = HTML_PARSER_NAME
    parser_version: str = HTML_PARSER_VERSION
    warnings: tuple[str, ...] = ()

    @property
    def artifact_id(self) -> str:
        return artifact_id(self.sha256)

    @model_validator(mode="after")
    def _representation_is_consistent(self) -> HtmlArtifact:
        if self.artifact_kind is not ArtifactKind.HTML:
            raise ValueError("HtmlArtifact must use artifact_kind HTML")
        if self.media_type not in HTML_MEDIA_TYPES:
            raise ValueError(f"unsupported HTML media type {self.media_type!r}")
        if self.content_sha256 != html_content_sha256(self.content):
            raise ValueError("content_sha256 does not match the HTML read model")
        if self.ingested_at.tzinfo is None or self.ingested_at.utcoffset() is None:
            raise ValueError("ingested_at must be timezone-aware")
        return self

    def summary(self) -> str:
        return (
            f"{self.sha256[:12]} · HTML · {self.byte_size:,} bytes · "
            f"{len(self.content.text_fragments)} text fragments · "
            f"{len(self.content.jsonld_blocks)} JSON-LD blocks"
        )


@dataclass(slots=True)
class _Frame:
    tag: str
    element_index: int
    ignored: bool


class _SnapshotParser(HTMLParser):
    _IGNORED_TAGS = {"head", "style", "noscript", "template", "nav", "iframe"}
    _VOID_TAGS = {
        "area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr",
    }

    def __init__(self, limits: HtmlIngestionLimits) -> None:
        super().__init__(convert_charrefs=True)
        self.limits = limits
        self.element_count = 0
        self.stack: list[_Frame] = []
        self.ignored_depth = 0
        self.title_parts: list[str] = []
        self.in_title = False
        self.canonical_url: str | None = None
        self.meta: dict[str, str] = {}
        self.visible_parts: list[tuple[str, int]] = []
        self.visible_chars = 0
        self.jsonld_raw: list[tuple[str, int]] = []
        self._jsonld_parts: list[str] | None = None
        self._jsonld_element: int | None = None

    @staticmethod
    def _attrs(attrs: list[tuple[str, str | None]]) -> dict[str, str]:
        return {name.casefold(): (value or "") for name, value in attrs}

    @staticmethod
    def _clean(value: str) -> str:
        return " ".join(value.split())

    def _start(self, tag: str, attrs: list[tuple[str, str | None]], *, void: bool) -> None:
        tag = tag.casefold()
        values = self._attrs(attrs)
        self.element_count += 1
        if self.element_count > self.limits.max_elements:
            raise DocumentTooLargeError(
                f"HTML has more than {self.limits.max_elements:,} elements",
                limit="max_elements",
                actual=self.element_count,
                allowed=self.limits.max_elements,
            )
        element_index = self.element_count - 1

        if tag == "link" and self.canonical_url is None:
            rel = {token.casefold() for token in values.get("rel", "").split()}
            href = values.get("href", "").strip()
            if "canonical" in rel and href:
                self.canonical_url = href
        elif tag == "meta":
            key = (values.get("name") or values.get("property") or "").casefold()
            content = self._clean(values.get("content", ""))
            if key and content and key not in self.meta:
                self.meta[key] = content

        is_jsonld = (
            tag == "script"
            and values.get("type", "").split(";", 1)[0].strip().casefold()
            == "application/ld+json"
        )
        if is_jsonld:
            if len(self.jsonld_raw) >= self.limits.max_jsonld_blocks:
                raise DocumentTooLargeError(
                    f"HTML has more than {self.limits.max_jsonld_blocks} JSON-LD blocks",
                    limit="max_jsonld_blocks",
                    actual=len(self.jsonld_raw) + 1,
                    allowed=self.limits.max_jsonld_blocks,
                )
            self._jsonld_parts = []
            self._jsonld_element = element_index

        ignored = (
            tag in self._IGNORED_TAGS
            or tag == "script"
            or "hidden" in values
            or values.get("aria-hidden", "").casefold() == "true"
            or values.get("role", "").casefold() == "navigation"
        )
        if tag == "title":
            self.in_title = True
        if ignored:
            self.ignored_depth += 1
        if not void and tag not in self._VOID_TAGS:
            self.stack.append(_Frame(tag, element_index, ignored))
        elif ignored:
            self.ignored_depth -= 1

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, void=False)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._start(tag, attrs, void=True)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.casefold()
        if tag == "script" and self._jsonld_parts is not None:
            self.jsonld_raw.append(("".join(self._jsonld_parts).strip(), self._jsonld_element or 0))
            self._jsonld_parts = None
            self._jsonld_element = None
        if tag == "title":
            self.in_title = False

        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index].tag == tag:
                removed = self.stack[index:]
                del self.stack[index:]
                self.ignored_depth -= sum(1 for frame in removed if frame.ignored)
                break

    def handle_data(self, data: str) -> None:
        if self._jsonld_parts is not None:
            self._jsonld_parts.append(data)
        cleaned = self._clean(data)
        if self.in_title and cleaned:
            self.title_parts.append(cleaned)
        if self.ignored_depth or not cleaned:
            return
        projected = self.visible_chars + len(cleaned) + (1 if self.visible_parts else 0)
        if projected > self.limits.max_visible_text_chars:
            raise DocumentTooLargeError(
                f"HTML visible text exceeds {self.limits.max_visible_text_chars:,} characters",
                limit="max_visible_text_chars",
                actual=projected,
                allowed=self.limits.max_visible_text_chars,
            )
        element_index = self.stack[-1].element_index if self.stack else 0
        self.visible_parts.append((cleaned, element_index))
        self.visible_chars = projected

    def finish(self) -> None:
        """Preserve an unterminated JSON-LD block as malformed source data."""
        if self._jsonld_parts is not None:
            self.jsonld_raw.append(
                ("".join(self._jsonld_parts).strip(), self._jsonld_element or 0)
            )
            self._jsonld_parts = None
            self._jsonld_element = None


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-standard JSON constant {value}")


def _jsonld_blocks(raw_blocks: list[tuple[str, int]]) -> tuple[HtmlJsonLdBlock, ...]:
    blocks: list[HtmlJsonLdBlock] = []
    for index, (raw, _element_index) in enumerate(raw_blocks):
        parsed: Any = None
        error: str | None = None
        try:
            parsed = json.loads(raw, parse_constant=_reject_json_constant)
        except (json.JSONDecodeError, RecursionError, ValueError) as exc:
            error = f"{type(exc).__name__}: invalid JSON-LD"
        blocks.append(
            HtmlJsonLdBlock(
                raw_text=raw,
                parsed=parsed,
                parse_error=error,
                locator=HtmlEvidenceLocator(
                    kind=SourceFragmentKind.HTML_JSONLD,
                    jsonld_block_index=index,
                    json_pointer="",
                ),
            )
        )
    return tuple(blocks)


def _content(parser: _SnapshotParser) -> HtmlArtifactContent:
    text_parts: list[str] = []
    fragments: list[HtmlTextFragment] = []
    cursor = 0
    for text, element_index in parser.visible_parts:
        if text_parts:
            cursor += 1
        start = cursor
        text_parts.append(text)
        cursor += len(text)
        fragments.append(
            HtmlTextFragment(
                text=text,
                locator=HtmlEvidenceLocator(
                    kind=SourceFragmentKind.HTML_TEXT,
                    element_index=element_index,
                    char_start=start,
                    char_end=cursor,
                ),
            )
        )
    return HtmlArtifactContent(
        title=" ".join(parser.title_parts) or None,
        canonical_url=parser.canonical_url,
        visible_text="\n".join(text_parts),
        text_fragments=tuple(fragments),
        jsonld_blocks=_jsonld_blocks(parser.jsonld_raw),
        metadata=HtmlMetadata(
            description=parser.meta.get("description"),
            open_graph_title=parser.meta.get("og:title"),
            open_graph_description=parser.meta.get("og:description"),
        ),
    )


def ingest_html_bytes(
    data: bytes,
    *,
    media_type: str,
    source: SourceMetadata | None = None,
    final_authority: str | None = None,
    limits: HtmlIngestionLimits | None = None,
    ingested_at: datetime | None = None,
) -> HtmlArtifact:
    """Parse one already-fetched HTML response without any network or code execution."""
    limits = limits or DEFAULT_HTML_LIMITS
    normalized_media_type = media_type.split(";", 1)[0].strip().casefold()
    if normalized_media_type not in HTML_MEDIA_TYPES:
        raise MalformedDocumentError(f"{media_type!r} is not an accepted HTML media type")
    if not data:
        raise EmptyDocumentError("HTML snapshot is empty (zero bytes)")
    if len(data) > limits.max_html_bytes:
        raise DocumentTooLargeError(
            f"HTML snapshot is {len(data):,} bytes, above the {limits.max_html_bytes:,} byte limit",
            limit="max_html_bytes",
            actual=len(data),
            allowed=limits.max_html_bytes,
        )
    if data.startswith(b"%PDF-"):
        raise MalformedDocumentError("response claims HTML but begins with a PDF signature")
    try:
        decoded = data.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise MalformedDocumentError("HTML snapshot is not valid UTF-8") from exc

    parser = _SnapshotParser(limits)
    try:
        parser.feed(decoded)
        parser.close()
        parser.finish()
    except DocumentTooLargeError:
        raise
    except Exception as exc:
        raise MalformedDocumentError(f"HTML parser failed safely ({type(exc).__name__})") from exc
    content = _content(parser)
    return HtmlArtifact(
        sha256=sha256_bytes(data),
        media_type=normalized_media_type,
        byte_size=len(data),
        source=source or SourceMetadata(),
        final_authority=final_authority,
        content=content,
        content_sha256=html_content_sha256(content),
        ingested_at=ingested_at or datetime.now(UTC),
    )


__all__ = [
    "DEFAULT_HTML_LIMITS",
    "HTML_INGESTION_VERSION",
    "HTML_MEDIA_TYPES",
    "HTML_PARSER_NAME",
    "HTML_PARSER_VERSION",
    "MAX_HTML_BYTES",
    "HtmlArtifact",
    "HtmlArtifactContent",
    "HtmlEvidenceLocator",
    "HtmlIngestionLimits",
    "HtmlJsonLdBlock",
    "HtmlMetadata",
    "HtmlTextFragment",
    "html_content_sha256",
    "ingest_html_bytes",
]
