"""Which hosts belong to which manufacturer, and which are known not to.

## Fuzzy matching cannot answer this question

`philips-superstore-example.com` contains "philips". `philips.com` is Philips. No amount
of string similarity separates those two reliably, and getting it wrong does not produce
a slightly weaker citation — it produces a reseller's marketing copy presented as
manufacturer specification.

So domain authority is **configuration, not inference**. A host is manufacturer-owned
because a reviewed registry says so, and for no other reason. A hint that matches no
entry yields no approved domain, which is a perfectly good answer.

## Matching

Manufacturer hints are dirty: `Phillips Lighting`, `Black & Decker/dewlt`, `Makita Usa
Inc`. A registry entry therefore lists explicit `hints` — the spellings actually observed
— rather than relying on a similarity score. Comparison folds case, punctuation, and
common corporate suffixes, because `Schneider Electric` and `SCHNEIDER ELECTRIC, INC.`
are the same string written twice, and that much is not a guess.

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
    """Where a registry's contents came from."""

    #: Organizer-supplied manufacturer master. We do not have one.
    OFFICIAL = "OFFICIAL"
    #: A person checked each domain against the manufacturer's own site.
    REVIEWED = "REVIEWED"
    #: Illustrative. Not checked, not authoritative.
    DEMO = "DEMO"

    @property
    def is_authoritative(self) -> bool:
        return self is RegistryAuthority.OFFICIAL


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
    """One manufacturer and the hosts it is known to publish from."""

    key: str
    hints: tuple[str, ...]
    domains: tuple[str, ...]
    note: str = ""
    _normalized_hints: frozenset[str] = field(default_factory=frozenset, repr=False)

    def matches_hint(self, hint: str | None) -> bool:
        normalized = normalize_manufacturer(hint)
        return bool(normalized) and normalized in self._normalized_hints

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
        distributors: tuple[str, ...] = (),
        marketplaces: tuple[str, ...] = (),
        blocked: tuple[str, ...] = (),
    ) -> None:
        self.name = name
        self.authority = authority
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
        """The manufacturer this hint names, or `None`. Never a nearest match."""
        if not hint:
            return None
        for entry in self._entries.values():
            if entry.matches_hint(hint):
                return entry
        return None

    def domains_for_hint(self, hint: str | None) -> tuple[str, ...]:
        entry = self.entry_for_hint(hint)
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
            hints = tuple(str(h) for h in raw.get("hints", []) or [])
            domains = tuple(normalize_host(str(d)) for d in raw["domains"])
        except (KeyError, TypeError) as exc:
            raise MalformedRegistryError(
                f"{source}: manufacturer entry {index} needs `key` and `domains`: {exc}"
            ) from exc
        if not key or not domains or not all(domains):
            raise MalformedRegistryError(
                f"{source}: manufacturer entry {index} has an empty key or domain"
            )
        entries.append(
            ManufacturerEntry(
                key=key,
                hints=hints,
                domains=domains,
                note=str(raw.get("note", "")),
                _normalized_hints=frozenset(
                    filter(None, (normalize_manufacturer(h) for h in (*hints, key)))
                ),
            )
        )

    hosts = data.get("hosts", {}) or {}
    return DomainRegistry(
        entries,
        name=name,
        authority=authority,
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
