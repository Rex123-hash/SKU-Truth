"""The mapping registry: explicit rules, injected, never inferred.

We do not hold the official Unilog LOV, UOM master, or category attribute rules. So
mapping cannot be derived — it has to be *supplied*, and the supply has to record where
it came from. A registry is a set of `AttributeMappingSpec` rules plus a name and an
authority, and the adjudicator consults it without ever inspecting a source key itself.

That seam is the deliverable. When organizer rule data arrives, an `OFFICIAL` registry
replaces a `DEMO` one and no adjudication logic changes.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterable
from pathlib import Path

from pydantic import ValidationError

from skutruth.contracts import Condition, ConditionSet

from .errors import MalformedMappingError
from .models import AttributeMappingSpec, ConditionPolicy, MappingAuthority

DEFAULT_MAPPING_DIR = Path(__file__).resolve().parents[3] / "data" / "mappings"


class MappingRegistry:
    """Mapping rules for one output target, keyed by opaque source key.

    Two rules for one source key would make the outcome depend on iteration order, and
    two rules for one target label would make two facts silently compete for one slot.
    Both are rejected at construction, where the author can still fix them.
    """

    def __init__(
        self,
        specs: Iterable[AttributeMappingSpec],
        *,
        name: str,
        authority: MappingAuthority | None = None,
    ) -> None:
        self.name = name
        self._specs: dict[str, AttributeMappingSpec] = {}
        by_label: dict[str, str] = {}

        for spec in specs:
            if spec.source_key in self._specs:
                raise MalformedMappingError(
                    f"{name}: source key {spec.source_key!r} is mapped twice; which rule "
                    f"applies would otherwise depend on iteration order"
                )
            existing = by_label.get(spec.target_label)
            if existing is not None:
                raise MalformedMappingError(
                    f"{name}: target {spec.target_label!r} is claimed by both "
                    f"{existing!r} and {spec.source_key!r}; two sources competing for "
                    f"one attribute slot must be resolved in the rules, not at runtime"
                )
            self._specs[spec.source_key] = spec
            by_label[spec.target_label] = spec.source_key

        declared = {s.authority for s in self._specs.values()}
        if authority is not None and declared - {authority}:
            raise MalformedMappingError(
                f"{name}: declared authority {authority.value} but contains rules marked "
                f"{', '.join(sorted(a.value for a in declared - {authority}))}"
            )
        self.authority = authority

    def spec_for(self, source_key: str) -> AttributeMappingSpec | None:
        """The rule for this key, or None. A missing rule is not an error."""
        return self._specs.get(source_key)

    @property
    def specs(self) -> tuple[AttributeMappingSpec, ...]:
        """Every rule, in priority then target order. Deterministic."""
        return tuple(sorted(self._specs.values(), key=lambda s: (s.priority, s.target_label)))

    @property
    def source_keys(self) -> tuple[str, ...]:
        return tuple(sorted(self._specs))

    @property
    def is_authoritative(self) -> bool:
        """True only when every rule came from organizer-supplied data.

        Deliberately conservative: one hand-written rule makes the whole registry
        non-authoritative, because a caller asking this question is deciding whether it
        may describe its output as conforming to published rules.
        """
        return bool(self._specs) and all(s.authority.is_authoritative for s in self._specs.values())

    def __len__(self) -> int:
        return len(self._specs)

    def __contains__(self, source_key: object) -> bool:
        return source_key in self._specs

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        mark = "authoritative" if self.is_authoritative else "non-authoritative"
        return f"MappingRegistry({self.name!r}, {len(self._specs)} rules, {mark})"


def parse_registry(data: dict, *, source: str = "<memory>") -> MappingRegistry:
    """Build a registry from already-parsed TOML.

    Deliberately dumb about what a source key means. It reads strings and hands them to
    the spec model, so a file of ETIM ids and a file of Unilog keys load identically.
    """
    try:
        name = data["name"]
        authority = MappingAuthority(data["authority"])
    except (KeyError, ValueError) as exc:
        raise MalformedMappingError(
            f"{source}: a mapping file must declare `name` and a valid `authority` "
            f"({', '.join(a.value for a in MappingAuthority)}); {exc}"
        ) from exc

    specs: list[AttributeMappingSpec] = []
    for index, entry in enumerate(data.get("mapping", []) or [], start=1):
        body = dict(entry)
        raw_conditions = body.pop("required_conditions", []) or []
        try:
            conditions = ConditionSet(
                conditions=tuple(
                    Condition(kind=c["kind"], value=c["value"]) for c in raw_conditions
                )
            )
            specs.append(
                AttributeMappingSpec(
                    authority=authority,
                    required_conditions=conditions,
                    condition_policy=ConditionPolicy(
                        body.pop("condition_policy", ConditionPolicy.REJECT_IF_CONDITIONED)
                    ),
                    **body,
                )
            )
        except (ValidationError, KeyError, TypeError, ValueError) as exc:
            raise MalformedMappingError(
                f"{source}: mapping entry {index} "
                f"({body.get('source_key', 'unnamed')!r}) is invalid: {exc}"
            ) from exc

    return MappingRegistry(specs, name=name, authority=authority)


def load_registry(path: str | Path) -> MappingRegistry:
    """Load a mapping registry from a TOML file."""
    file = Path(path)
    if not file.is_file():
        raise MalformedMappingError(f"no mapping file at {file}")
    with file.open("rb") as handle:
        try:
            data = tomllib.load(handle)
        except tomllib.TOMLDecodeError as exc:
            raise MalformedMappingError(f"{file}: unreadable TOML: {exc}") from exc
    return parse_registry(data, source=file.name)


def available_registries(directory: Path | None = None) -> tuple[str, ...]:
    folder = Path(directory) if directory is not None else DEFAULT_MAPPING_DIR
    if not folder.is_dir():
        return ()
    return tuple(sorted(p.stem for p in folder.glob("*.toml")))


__all__ = [
    "DEFAULT_MAPPING_DIR",
    "MappingRegistry",
    "available_registries",
    "load_registry",
    "parse_registry",
]
