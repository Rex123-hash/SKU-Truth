"""Which hosts belong to which manufacturer, and which are known not to.

## Fuzzy matching cannot answer this question

`philips-superstore-example.com` contains "philips". `philips.com` is Philips. No amount
of string similarity separates those two reliably, and getting it wrong does not produce
a slightly weaker citation — it produces a reseller's marketing copy presented as
manufacturer specification.

So domain authority is **configuration, not inference**. A host is manufacturer-owned
because a reviewed registry says so, and for no other reason. A hint that matches no
entry yields no approved domain, which is a perfectly good answer.

## Two kinds of hint, and only one of them grants ownership

Manufacturer hints are dirty: `Phillips Lighting`, `Black & Decker/dewlt`, `Makita Usa
Inc`. Some of that dirt is cosmetic and some of it is a substantive claim, and treating
the two alike is how a spelling mistake becomes a publisher identity.

* **`authority_hints`** — reviewed as genuinely naming this manufacturer. Differences are
  case, punctuation, or corporate form: `Schneider Electric` and `SCHNEIDER ELECTRIC,
  INC.` are one string written twice, and `Makita Usa Inc` reduces to `Makita` under a
  documented suffix rule. These may produce `APPROVED_MANUFACTURER`.
* **`locator_hints`** — spellings observed in the input that are *plausibly* this
  manufacturer and have not been confirmed. `Phillips Lighting` is probably Philips.
  `Black & Decker/dewlt` is probably DeWalt. Probably is not a licence. These help build
  search queries and can never grant ownership.

The distinction exists because the approved manufacturer master is missing. Deciding that
`Black & Decker/dewlt` *is* DeWalt is exactly the canonicalisation that file would
authorise, and asserting it here — as a side effect of a domain lookup — would smuggle in
the decision without the evidence. Nothing rewrites the input spelling either way.

Hosts match on exact equality or on a **subdomain** of an approved domain, so
`download.se.com` is covered by `se.com` while `se.com.evil.example` is not — a
suffix test alone would accept the second.

## Authority of the registry itself

`MappingAuthority`-style provenance applies here too: a registry declares whether it is
`OFFICIAL` (organizer-supplied), `REVIEWED` (a person checked each entry), or `DEMO`. We
hold no organizer manufacturer master, so everything shipped today is `DEMO` or
`REVIEWED`, and `is_authoritative` is false.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path

from .errors import MalformedRegistryError

DEFAULT_REGISTRY_DIR = Path(__file__).resolve().parents[3] / "data" / "discovery"

#: Dropped before comparing manufacturer names. Corporate form is not identity.
_SUFFIXES = {
    "inc",
    "incorporated",
    "llc",
    "ltd",
    "limited",
    "corp",
    "corporation",
    "co",
    "company",
    "gmbh",
    "ag",
    "sa",
    "sas",
    "bv",
    "nv",
    "plc",
    "usa",
    "us",
}

_PUNCTUATION = re.compile(r"[^a-z0-9]+")


class RegistryAuthority(StrEnum):
    """Where a registry's contents came from, and therefore what they may do.

    Two different questions, kept apart because conflating them either blocks all work or
    licenses unchecked data:

    * `is_authoritative` — did this come from the organizer's own master? Only `OFFICIAL`
      does, and nothing may be described as conforming to published rules without it.
    * `may_license_evidence` — may an entry here bind a host to a manufacturer strongly
      enough to store its bytes as that manufacturer's evidence? `OFFICIAL` and
      `REVIEWED` may; `DEMO` may not.

    `REVIEWED` licenses evidence because domain ownership is a *checkable* fact and a
    different claim from conforming to Unilog's catalogue rules. But "a person checked it"
    is only worth something if the check left a record — otherwise it is an assertion
    wearing a review's clothing, and it would be load-bearing for every fact acquired
    through it. So a `REVIEWED` entry licenses evidence **only when it carries a
    `DomainReview`**; without one it is locator-grade, exactly like a `DEMO` entry.

    `DEMO` licenses nothing at all: it exists for illustration and tests, and an
    illustrative entry that could authorise a download would make the label meaningless.
    """

    #: Organizer-supplied manufacturer master. We do not have one.
    OFFICIAL = "OFFICIAL"
    #: A person checked each domain against the manufacturer's own publications, and
    #: recorded what they checked.
    REVIEWED = "REVIEWED"
    #: Illustrative. Not checked, and never a licence.
    DEMO = "DEMO"

    @property
    def is_authoritative(self) -> bool:
        """Whether this came from organizer-supplied data."""
        return self is RegistryAuthority.OFFICIAL

    @property
    def may_license_evidence(self) -> bool:
        """Whether entries here *can* establish ownership — necessary, not sufficient.

        A `REVIEWED` registry still needs a per-entry review record; see
        `ManufacturerEntry.licenses_evidence`.
        """
        return self in {RegistryAuthority.OFFICIAL, RegistryAuthority.REVIEWED}

    @property
    def requires_entry_review(self) -> bool:
        """Whether each licensing entry must carry its own review record.

        `OFFICIAL` does not: its basis is the organizer master, named once on the
        registry, and inventing a per-entry "manual review" for rows that came from a
        supplied file would be recording a check nobody performed.
        """
        return self is RegistryAuthority.REVIEWED


@dataclass(frozen=True, slots=True)
class DomainReview:
    """The audit record behind one manufacturer-domain binding.

    Small on purpose. The question a reviewer needs answered later is only ever "who
    decided this, when, and on what evidence" — and a `basis` that names something
    checkable in this repository is worth more than a long prose justification.
    """

    reviewed_at: str
    reviewed_by: str
    basis: str
    note: str = ""

    def describe(self) -> str:
        return f"{self.reviewed_by} on {self.reviewed_at}: {self.basis}"


def normalize_manufacturer(name: str | None) -> str:
    """Fold case, punctuation, and corporate suffixes. Never a similarity score."""
    if not name:
        return ""
    tokens = [t for t in _PUNCTUATION.sub(" ", name.casefold()).split() if t]
    kept = [t for t in tokens if t not in _SUFFIXES]
    return " ".join(kept or tokens)


def normalize_host(host: str | None) -> str:
    """Lowercase, strip a trailing dot and a leading `www.`."""
    if not host:
        return ""
    cleaned = host.strip().casefold().rstrip(".")
    return cleaned[4:] if cleaned.startswith("www.") else cleaned


def host_covered_by(host: str, domain: str) -> bool:
    """Whether `host` is `domain` or a subdomain of it.

    Label-aware on purpose. A bare `endswith` would accept `se.com.evil.example` for
    `se.com`, which is exactly how a lookalike host gets treated as manufacturer-owned.
    """
    h, d = normalize_host(host), normalize_host(domain)
    if not h or not d:
        return False
    return h == d or h.endswith(f".{d}")


@dataclass(frozen=True, slots=True)
class ManufacturerEntry:
    """One manufacturer, the hosts it publishes from, and the names it answers to."""

    key: str
    #: Reviewed spellings that genuinely name this manufacturer.
    authority_hints: tuple[str, ...]
    #: Observed spellings that may help find it, and may not identify it.
    locator_hints: tuple[str, ...]
    domains: tuple[str, ...]
    #: The audit record behind this binding. `None` means nobody has checked it yet,
    #: which is a normal state and simply means the entry cannot license evidence.
    review: DomainReview | None = None
    note: str = ""
    _authority_keys: frozenset[str] = field(default_factory=frozenset, repr=False)
    _locator_keys: frozenset[str] = field(default_factory=frozenset, repr=False)

    def licenses_evidence(self, authority: RegistryAuthority) -> bool:
        """Whether this binding may make a host's bytes count as manufacturer evidence.

        Both halves must hold: the registry's provenance must permit licensing at all,
        and — where that provenance is a manual review — this entry must carry the record
        of it. An unreviewed entry in a `REVIEWED` file is not an error; it is an entry
        that has not been checked yet, and it stays useful for locating candidates.
        """
        if not authority.may_license_evidence:
            return False
        return self.review is not None or not authority.requires_entry_review

    def grants_authority(self, hint: str | None) -> bool:
        """Whether this hint may bind the manufacturer's ownership of its domains."""
        normalized = normalize_manufacturer(hint)
        return bool(normalized) and normalized in self._authority_keys

    def matches_for_locating(self, hint: str | None) -> bool:
        """Whether this hint may be used to build queries. Broader, and grants nothing."""
        normalized = normalize_manufacturer(hint)
        return bool(normalized) and normalized in (self._authority_keys | self._locator_keys)

    def owns(self, host: str) -> bool:
        return any(host_covered_by(host, d) for d in self.domains)


class DomainRegistry:
    """Manufacturer domains, plus hosts classified as distributor/marketplace/blocked."""

    def __init__(
        self,
        entries: list[ManufacturerEntry],
        *,
        name: str,
        authority: RegistryAuthority,
        source: str = "",
        distributors: tuple[str, ...] = (),
        marketplaces: tuple[str, ...] = (),
        blocked: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.authority = authority
        #: For `OFFICIAL`, the organizer file these bindings came from. Required there,
        #: because "official" with no named master is the same unaudited assertion this
        #: design exists to refuse — it just sounds more authoritative.
        self.source = source
        if authority is RegistryAuthority.OFFICIAL and not source.strip():
            raise MalformedRegistryError(
                f"{name}: an OFFICIAL registry must name the organizer master it came "
                f"from in `source`; otherwise nothing records what makes it official"
            )
        self.distributors = tuple(sorted({normalize_host(d) for d in distributors if d}))
        self.marketplaces = tuple(sorted({normalize_host(m) for m in marketplaces if m}))
        self.blocked = tuple(sorted({normalize_host(b) for b in blocked if b}))

        self._entries: dict[str, ManufacturerEntry] = {}
        for entry in entries:
            if entry.key in self._entries:
                raise MalformedRegistryError(
                    f"{name}: manufacturer key {entry.key!r} appears twice"
                )
            self._entries[entry.key] = entry

    def entry_for_hint(self, hint: str | None) -> ManufacturerEntry | None:
        """The manufacturer this hint *identifies*, or `None`. Never a nearest match.

        Authority hints only. A locator-only spelling deliberately returns `None` here,
        so nothing that reads this function can turn an unconfirmed name into ownership.
        """
        if not hint:
            return None
        for entry in self._entries.values():
            if entry.grants_authority(hint):
                return entry
        return None

    def entry_for_locating(self, hint: str | None) -> ManufacturerEntry | None:
        """The manufacturer this hint may point at, for query construction only."""
        if not hint:
            return None
        for entry in self._entries.values():
            if entry.matches_for_locating(hint):
                return entry
        return None

    def domains_for_hint(self, hint: str | None) -> tuple[str, ...]:
        """Domains worth searching. Uses the broader locator match on purpose.

        A `site:` query aimed at a manufacturer that turns out to be the wrong one costs
        one query and returns nothing. That is a far better trade than never searching the
        right site because the input misspelled its name — and it grants nothing, because
        whatever comes back is classified by `entry_for_hint`, which is stricter.
        """
        entry = self.entry_for_locating(hint)
        return entry.domains if entry else ()

    def owner_of(self, host: str) -> ManufacturerEntry | None:
        """The manufacturer that publishes from this host, if any."""
        normalized = normalize_host(host)
        for entry in self._entries.values():
            if entry.owns(normalized):
                return entry
        return None

    def _in(self, host: str, listed: tuple[str, ...]) -> bool:
        return any(host_covered_by(host, d) for d in listed)

    def is_distributor(self, host: str) -> bool:
        return self._in(host, self.distributors)

    def is_marketplace(self, host: str) -> bool:
        return self._in(host, self.marketplaces)

    def is_blocked(self, host: str) -> bool:
        return self._in(host, self.blocked)

    @property
    def entries(self) -> tuple[ManufacturerEntry, ...]:
        return tuple(self._entries[k] for k in sorted(self._entries))

    @property
    def licensing_entries(self) -> tuple[ManufacturerEntry, ...]:
        """Entries whose bindings may make a host's bytes manufacturer evidence."""
        return tuple(e for e in self.entries if e.licenses_evidence(self.authority))

    @property
    def unreviewed_entries(self) -> tuple[ManufacturerEntry, ...]:
        """Entries usable for locating candidates but not for licensing them."""
        return tuple(e for e in self.entries if not e.licenses_evidence(self.authority))

    def licenses(self, entry: ManufacturerEntry | None) -> bool:
        return entry is not None and entry.licenses_evidence(self.authority)

    @property
    def is_authoritative(self) -> bool:
        """True only for an organizer-supplied master. Conservative by design."""
        return self.authority.is_authoritative

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return (
            f"DomainRegistry({self.name!r}, {len(self._entries)} manufacturers, "
            f"{self.authority.value})"
        )


def _parse_review(raw: object, *, source: str, key: str) -> DomainReview | None:
    """Read one entry's audit record, or `None` when it has not been reviewed.

    A half-filled review is refused rather than accepted with blanks: a record naming no
    reviewer, no date, or no basis answers none of the questions it exists to answer, and
    accepting it would let an entry license evidence on the strength of an empty form.
    """
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise MalformedRegistryError(
            f"{source}: `review` for {key!r} must be a table, got {type(raw).__name__}"
        )

    required = ("reviewed_at", "reviewed_by", "basis")
    fields = {name: str(raw.get(name, "")).strip() for name in required}
    missing = sorted(name for name, value in fields.items() if not value)
    if missing:
        raise MalformedRegistryError(
            f"{source}: `review` for {key!r} is missing {', '.join(missing)}. A review "
            f"record must say who checked what, and when, or it establishes nothing."
        )
    return DomainReview(**fields, note=str(raw.get("note", "")).strip())


def parse_registry(data: dict, *, source: str = "<memory>") -> DomainRegistry:
    """Build a registry from already-parsed TOML."""
    try:
        name = data["name"]
        authority = RegistryAuthority(data["authority"])
    except (KeyError, ValueError) as exc:
        raise MalformedRegistryError(
            f"{source}: a domain registry must declare `name` and a valid `authority` "
            f"({', '.join(a.value for a in RegistryAuthority)}); {exc}"
        ) from exc

    entries: list[ManufacturerEntry] = []
    for index, raw in enumerate(data.get("manufacturer", []) or [], start=1):
        try:
            key = str(raw["key"]).strip()
            authority_hints = tuple(str(h) for h in raw.get("authority_hints", []) or [])
            locator_hints = tuple(str(h) for h in raw.get("locator_hints", []) or [])
            domains = tuple(normalize_host(str(d)) for d in raw["domains"])
        except (KeyError, TypeError) as exc:
            raise MalformedRegistryError(
                f"{source}: manufacturer entry {index} needs `key` and `domains`: {exc}"
            ) from exc
        if not key or not domains or not all(domains):
            raise MalformedRegistryError(
                f"{source}: manufacturer entry {index} has an empty key or domain"
            )
        if "hints" in raw:
            # The old single-list form is refused rather than mapped onto either side.
            # Guessing which spellings were reviewed is the decision this split exists
            # to stop being made implicitly.
            raise MalformedRegistryError(
                f"{source}: manufacturer entry {index} ({key!r}) uses `hints`; declare "
                f"`authority_hints` (reviewed as naming this manufacturer) and "
                f"`locator_hints` (search aids that grant nothing) separately"
            )

        authority_keys = frozenset(
            filter(None, (normalize_manufacturer(h) for h in (*authority_hints, key)))
        )
        locator_keys = frozenset(
            filter(None, (normalize_manufacturer(h) for h in locator_hints))
        )
        overlap = authority_keys & locator_keys
        if overlap:
            raise MalformedRegistryError(
                f"{source}: {key!r} lists {sorted(overlap)} as both an authority and a "
                f"locator hint; a name either identifies this manufacturer or it does not"
            )

        entries.append(
            ManufacturerEntry(
                key=key,
                authority_hints=authority_hints,
                locator_hints=locator_hints,
                domains=domains,
                review=_parse_review(raw.get("review"), source=source, key=key),
                note=str(raw.get("note", "")),
                _authority_keys=authority_keys,
                _locator_keys=locator_keys,
            )
        )

    hosts = data.get("hosts", {}) or {}
    return DomainRegistry(
        entries,
        name=name,
        authority=authority,
        source=str(data.get("source", "")),
        distributors=tuple(hosts.get("distributors", []) or []),
        marketplaces=tuple(hosts.get("marketplaces", []) or []),
        blocked=tuple(hosts.get("blocked", []) or []),
    )


def load_registry(path: str | Path) -> DomainRegistry:
    """Load a domain registry from TOML."""
    file = Path(path)
    if not file.is_file():
        raise MalformedRegistryError(f"no domain registry at {file}")
    with file.open("rb") as handle:
        try:
            data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise MalformedRegistryError(f"{file}: unreadable TOML: {exc}") from exc
    return parse_registry(data, source=file.name)


__all__ = [
    "DEFAULT_REGISTRY_DIR",
    "DomainRegistry",
    "ManufacturerEntry",
    "RegistryAuthority",
    "host_covered_by",
    "load_registry",
    "normalize_host",
    "normalize_manufacturer",
    "parse_registry",
]
