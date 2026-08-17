"""Preparing manufacturer-domain reviews for a human, and applying the ones they sign.

A `DomainReview` is the only thing that lets an entry license evidence, and it is an
assertion that a *named person checked something*. That makes this module unusual: its
job is to do as much of the work as possible while carefully not doing the one part that
matters.

## What this module may and may not decide

It may: gather every fact a reviewer needs — the spellings the organizer input actually
uses, how many rows each covers, sample references, the domains currently configured,
whether a hint is authority-grade or locator-only, and what a live search returned.

It may not: conclude anything from those facts. There is no threshold of row count, no
number of search hits, and no domain-name similarity that promotes an entry. A packet
always comes out unreviewed, and `HumanDomainReview` can only be constructed from values
an operator supplied explicitly.

## Reviewer identity is never inferred

Nothing here reads git config, `getpass`, `os.getlogin`, `USER`, or any other ambient
signal, and a test asserts the module imports nothing that could. The repository already
had a review attributed to a person who never performed one, inferred from git authorship;
that is the failure this module is shaped around. A reviewer's name has to be typed by the
reviewer, because the name *is* the claim.

## Confirming a binding means confirming all of it

An entry licenses evidence for every domain it lists, so a partial confirmation cannot be
applied to it. Confirming `kichler.com` on an entry that also lists `kichlerlighting.net`
would silently license the second. `apply_review` refuses unless the confirmed set covers
the entry exactly, and tells the operator to split the entry if they meant only one host.

## Review is not canonicalisation

Confirming that Signify operates `lighting.philips.com` says nothing about whether the
organizer's `Phillips Lighting` rows are that manufacturer. Applying a review never moves
a spelling from `locator_hints` to `authority_hints`; those rows stay locator-grade until
the manufacturer master settles them.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from .domains import DomainRegistry, ManufacturerEntry, normalize_host
from .errors import DiscoveryError
from .models import SearchResult

#: Bumped when the packet's shape changes in a way a consumer would notice.
REVIEW_PACKET_VERSION = "domain-review-packet@v1"


class ReviewError(DiscoveryError):
    """A review could not be prepared or applied as stated."""


@dataclass(frozen=True, slots=True)
class ObservedSpelling:
    """One distinct `Part_Manuf` value seen in the organizer input, and its reading.

    Both the raw string and the parsed name are kept. The raw string is what a reviewer
    must actually recognise, and the parsed name is what discovery matches on; when they
    differ, that difference is usually the thing worth looking at.
    """

    raw: str
    display_name: str | None
    supplier_code: str | None
    row_count: int
    sample_mpns: tuple[str, ...]
    #: Whether this spelling may bind ownership, or only build queries.
    grants_authority: bool


@dataclass(frozen=True, slots=True)
class ReviewCandidate:
    """One manufacturer entry, everything observed about it, and nothing decided.

    `search_results` is populated only when the caller ran a live search; an empty tuple
    means no search was run, which is different from a search that found nothing. The
    caller reports which of those it was — this type does not guess.
    """

    key: str
    domains: tuple[str, ...]
    authority_hints: tuple[str, ...]
    locator_hints: tuple[str, ...]
    spellings: tuple[ObservedSpelling, ...]
    #: Whether the registry *already* carries a review. Read from the registry, never set
    #: by anything in this module.
    already_reviewed: bool
    existing_basis: str | None = None
    search_results: tuple[SearchResult, ...] = ()
    note: str = ""

    @property
    def row_count(self) -> int:
        return sum(s.row_count for s in self.spellings)

    @property
    def sample_mpns(self) -> tuple[str, ...]:
        seen: list[str] = []
        for spelling in self.spellings:
            for mpn in spelling.sample_mpns:
                if mpn not in seen:
                    seen.append(mpn)
        return tuple(seen)

    @property
    def observed_hosts(self) -> tuple[str, ...]:
        """Distinct hosts a live search named, in first-seen order.

        Offered as *reading material* for the reviewer. A host appearing here has been
        named by a search engine and nothing more; it is not a proposed domain, and
        adding one to the registry is a separate, deliberate edit.
        """
        seen: list[str] = []
        for result in self.search_results:
            host = normalize_host(_host_of(result.url))
            if host and host not in seen:
                seen.append(host)
        return tuple(seen)

    @property
    def needs_review(self) -> bool:
        """Whether a human decision would change anything. Never a recommendation."""
        return not self.already_reviewed


@dataclass(frozen=True, slots=True)
class ReviewPacket:
    """Everything prepared for a human, with no decision taken.

    There is deliberately no `confirmed` field anywhere in this structure. A packet
    cannot express a confirmation, so no code path can produce one by filling a packet
    in — a confirmation has to be constructed as a `HumanDomainReview` from arguments an
    operator supplied.
    """

    candidates: tuple[ReviewCandidate, ...]
    registry_name: str
    registry_authority: str
    rows_scanned: int
    searched: bool = False
    version: str = REVIEW_PACKET_VERSION

    @property
    def pending(self) -> tuple[ReviewCandidate, ...]:
        return tuple(c for c in self.candidates if c.needs_review)


def _host_of(url: str) -> str:
    """Host of a URL, without importing the fetch layer's policy for a display string."""
    match = re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://([^/?#]+)", url.strip())
    if not match:
        return ""
    authority = match.group(1)
    _, _, hostport = authority.rpartition("@")
    if hostport.startswith("["):
        return hostport.partition("]")[0].lstrip("[")
    return hostport.partition(":")[0]


@dataclass
class _Accumulator:
    """Mutable per-spelling tally, collapsed into `ObservedSpelling` at the end."""

    display_name: str | None = None
    supplier_code: str | None = None
    rows: int = 0
    mpns: list[str] = field(default_factory=list)
    grants_authority: bool = False


def observe_input(
    rows: Iterable[object], registry: DomainRegistry, *, sample_mpns: int = 5
) -> tuple[dict[str, dict[str, _Accumulator]], int]:
    """Tally organizer rows against registry entries. Counts only; nothing is decided.

    Rows are matched with the *broad* locator match, because a reviewer confirming that
    Signify operates `lighting.philips.com` needs to see the `Phillips Lighting` rows
    that would benefit — while `grants_authority` records, per spelling, whether that
    row could ever license anything even after the review lands.
    """
    tallies: dict[str, dict[str, _Accumulator]] = {}
    scanned = 0

    for row in rows:
        scanned += 1
        parsed = row.manufacturer  # type: ignore[attr-defined]
        raw = (parsed.raw or "").strip()
        hint = parsed.display_name
        if not raw or not hint:
            continue
        entry = registry.entry_for_locating(hint)
        if entry is None:
            continue

        by_spelling = tallies.setdefault(entry.key, {})
        acc = by_spelling.setdefault(raw, _Accumulator())
        acc.display_name = hint
        acc.supplier_code = parsed.supplier_code
        acc.grants_authority = entry.grants_authority(hint)
        acc.rows += 1
        mpn = row.mfg_part_num  # type: ignore[attr-defined]
        if mpn and len(acc.mpns) < sample_mpns and mpn not in acc.mpns:
            acc.mpns.append(mpn)

    return tallies, scanned


def build_packet(
    rows: Iterable[object],
    registry: DomainRegistry,
    *,
    only: Sequence[str] | None = None,
    search_results: dict[str, tuple[SearchResult, ...]] | None = None,
    searched: bool = False,
    include_unobserved: bool = False,
    sample_mpns: int = 5,
) -> ReviewPacket:
    """Assemble the packet. Every candidate comes out unreviewed unless already reviewed.

    `include_unobserved` keeps registry entries the organizer input never mentions.
    Off by default: a reviewer's time is best spent on bindings that would actually
    license rows, and an entry nothing references can wait.
    """
    tallies, scanned = observe_input(rows, registry, sample_mpns=sample_mpns)
    wanted = {k.strip() for k in only} if only else None
    results = search_results or {}

    candidates: list[ReviewCandidate] = []
    for entry in registry.entries:
        if wanted is not None and entry.key not in wanted:
            continue
        by_spelling = tallies.get(entry.key, {})
        if not by_spelling and not include_unobserved:
            continue
        spellings = tuple(
            ObservedSpelling(
                raw=raw,
                display_name=acc.display_name,
                supplier_code=acc.supplier_code,
                row_count=acc.rows,
                sample_mpns=tuple(acc.mpns),
                grants_authority=acc.grants_authority,
            )
            # Most-referenced spelling first, then alphabetically so the packet is
            # byte-stable across runs and can be diffed.
            for raw, acc in sorted(by_spelling.items(), key=lambda kv: (-kv[1].rows, kv[0]))
        )
        candidates.append(
            ReviewCandidate(
                key=entry.key,
                domains=entry.domains,
                authority_hints=entry.authority_hints,
                locator_hints=entry.locator_hints,
                spellings=spellings,
                already_reviewed=entry.review is not None,
                existing_basis=entry.review.describe() if entry.review else None,
                search_results=tuple(results.get(entry.key, ())),
                note=entry.note.strip(),
            )
        )

    if wanted is not None:
        unknown = sorted(wanted - {e.key for e in registry.entries})
        if unknown:
            raise ReviewError(
                f"no manufacturer entry named {', '.join(unknown)} in {registry.name}"
            )

    candidates.sort(key=lambda c: (-c.row_count, c.key))
    return ReviewPacket(
        candidates=tuple(candidates),
        registry_name=registry.name,
        registry_authority=registry.authority.value,
        rows_scanned=scanned,
        searched=searched,
    )


# -- the human decision -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class HumanDomainReview:
    """A confirmation a person actually made. Every field is operator-supplied.

    Validation is in `__post_init__` rather than at the call site so there is no way to
    build a half-empty review — including from a script that forgot to require a flag.
    """

    manufacturer_key: str
    confirmed_domains: tuple[str, ...]
    reviewed_by: str
    basis: str
    reviewed_at: str
    consulted_urls: tuple[str, ...] = ()
    note: str = ""

    def __post_init__(self) -> None:
        missing = [
            name
            for name, value in (
                ("manufacturer_key", self.manufacturer_key),
                ("reviewed_by", self.reviewed_by),
                ("basis", self.basis),
                ("reviewed_at", self.reviewed_at),
            )
            if not str(value).strip()
        ]
        if missing:
            raise ReviewError(
                f"a review must state {', '.join(missing)}; these are the operator's own "
                f"words and have no default"
            )
        if not self.confirmed_domains or not all(d.strip() for d in self.confirmed_domains):
            raise ReviewError("a review must confirm at least one non-empty domain")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", self.reviewed_at.strip()):
            raise ReviewError(
                f"reviewed_at must be an ISO date (YYYY-MM-DD); got {self.reviewed_at!r}"
            )

    @property
    def normalized_domains(self) -> tuple[str, ...]:
        return tuple(sorted({normalize_host(d) for d in self.confirmed_domains}))

    def full_basis(self) -> str:
        """The basis, with any URLs the reviewer consulted appended.

        Recorded in `basis` rather than a separate field because `DomainReview` is a
        frozen four-field record, and what was consulted is part of what was checked.
        """
        basis = self.basis.strip()
        if not self.consulted_urls:
            return basis
        urls = " ".join(u.strip() for u in self.consulted_urls if u.strip())
        return f"{basis} Consulted: {urls}" if urls else basis


def check_review_applies(review: HumanDomainReview, registry: DomainRegistry) -> ManufacturerEntry:
    """Whether this review can be applied to this registry, and to which entry.

    Refuses three ways, all of which would otherwise license something nobody confirmed:
    an unknown manufacturer, a domain set that does not match the entry exactly, and an
    entry that already carries a review.
    """
    entry = next((e for e in registry.entries if e.key == review.manufacturer_key), None)
    if entry is None:
        raise ReviewError(
            f"{registry.name} has no manufacturer entry {review.manufacturer_key!r}; "
            f"known keys: {', '.join(e.key for e in registry.entries)}"
        )
    if entry.review is not None:
        raise ReviewError(
            f"{entry.key} already carries a review by {entry.review.reviewed_by} on "
            f"{entry.review.reviewed_at}. Overwriting someone else's audit record is not "
            f"something this tool does; edit the registry by hand if it is genuinely wrong."
        )

    configured = tuple(sorted({normalize_host(d) for d in entry.domains}))
    confirmed = review.normalized_domains
    if confirmed != configured:
        missing = [d for d in configured if d not in confirmed]
        extra = [d for d in confirmed if d not in configured]
        detail = []
        if missing:
            detail.append(f"not confirmed: {', '.join(missing)}")
        if extra:
            detail.append(f"not listed on the entry: {', '.join(extra)}")
        raise ReviewError(
            f"{entry.key} lists {', '.join(configured)}; a review licenses every domain "
            f"on the entry, so all of them must be confirmed together ({'; '.join(detail)}). "
            f"To confirm only some, split the entry first."
        )
    return entry


def render_review_block(review: HumanDomainReview) -> str:
    """The TOML a reviewer's decision becomes. Emitted so it can be read before it lands."""
    lines = [
        "[manufacturer.review]",
        f'reviewed_at = "{_toml_escape(review.reviewed_at.strip())}"',
        f'reviewed_by = "{_toml_escape(review.reviewed_by.strip())}"',
        f'basis = "{_toml_escape(review.full_basis())}"',
    ]
    if review.note.strip():
        lines.append(f'note = "{_toml_escape(review.note.strip())}"')
    return "\n".join(lines)


def _toml_escape(value: str) -> str:
    """Escape for a TOML basic string. Control characters are dropped, not encoded."""
    cleaned = "".join(ch for ch in value if ch >= " " or ch == "\t")
    return cleaned.replace("\\", "\\\\").replace('"', '\\"').replace("\t", "\\t")


def _code_lines(lines: Sequence[str]) -> list[bool]:
    """Which lines are TOML structure rather than the inside of a multi-line string.

    Several entries carry multi-line `note = \"\"\"...\"\"\"` values whose prose contains
    bracketed text and `key = ` fragments. A scanner that ignored quoting would read a
    table header out of a note and insert a review into the middle of a string literal,
    producing a file that still parses and means something else entirely.
    """
    flags: list[bool] = []
    in_multiline = False
    for line in lines:
        flags.append(not in_multiline)
        if line.count('"""') % 2 == 1:
            in_multiline = not in_multiline
    return flags


def _manufacturer_block_bounds(lines: Sequence[str], key: str) -> tuple[int, int]:
    """Line bounds of the `[[manufacturer]]` block declaring `key`, end-exclusive."""
    is_code = _code_lines(lines)
    #: Every top-level table header, in order. Any of them closes the preceding block.
    headers = [i for i, line in enumerate(lines) if is_code[i] and line.lstrip().startswith("[")]

    for position, start in enumerate(headers):
        if not lines[start].strip().startswith("[[manufacturer]]"):
            continue
        end = headers[position + 1] if position + 1 < len(headers) else len(lines)
        declares_key = any(
            (match := re.match(r'\s*key\s*=\s*"([^"]*)"', lines[i]))
            and match.group(1).strip() == key
            for i in range(start, end)
            if is_code[i]
        )
        if declares_key:
            return start, end

    raise ReviewError(f"could not locate the `[[manufacturer]]` block for {key!r} in the registry")


def apply_review(registry_text: str, review: HumanDomainReview, registry: DomainRegistry) -> str:
    """Return the registry text with this review inserted. Never writes a file.

    Separated from I/O so the result can be shown to the operator, diffed, or discarded.
    The caller re-loads the result and verifies the review landed before overwriting
    anything — a text edit that produced valid TOML meaning something else would
    otherwise be indistinguishable from success.
    """
    check_review_applies(review, registry)
    lines: Sequence[str] = registry_text.splitlines()
    start, end = _manufacturer_block_bounds(lines, review.manufacturer_key)

    if any("[manufacturer.review]" in line for line in lines[start:end]):
        raise ReviewError(f"{review.manufacturer_key} already has a `[manufacturer.review]` block")

    insert_at = end
    while insert_at > start and not lines[insert_at - 1].strip():
        insert_at -= 1

    block = ["", *render_review_block(review).splitlines()]
    updated = [*lines[:insert_at], *block, *lines[insert_at:]]
    text = "\n".join(updated)
    return text + "\n" if registry_text.endswith("\n") else text


__all__ = [
    "REVIEW_PACKET_VERSION",
    "HumanDomainReview",
    "ObservedSpelling",
    "ReviewCandidate",
    "ReviewError",
    "ReviewPacket",
    "apply_review",
    "build_packet",
    "check_review_applies",
    "observe_input",
    "render_review_block",
]
