"""Hand-reviewed per-class configuration.

ETIM says which features characterise a class. It does not say which features a buyer
needs, nor which operating qualifiers a value is meaningless without. Both are
judgement calls, so both live in reviewed TOML under `data/demo_classes/` rather than
being inferred at runtime.

The alternative — parsing "Rated operation current Ie at AC-3, 400 V" to discover it
needs a utilization category and a voltage — happens to work for the contactor class
and would silently misfire elsewhere. A wrong qualifier rule produces a confidently
mis-conditioned value, which is worse than no rule at all, so the rules are written
down with reasons and checked against the loaded ETIM class.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from skutruth.contracts import ConditionKind

from .model import EtimClass

DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[3] / "data" / "demo_classes"


@dataclass(frozen=True, slots=True)
class QualifierRule:
    """The reviewed qualifier requirement for one feature.

    An empty `required_kinds` is a positive finding — reviewed, none needed — and
    resolves to COMPLETE. A feature with *no rule at all* resolves to UNKNOWN, which
    is a different statement: we have not reviewed it and will not pretend otherwise.
    """

    feature_id: str
    required_kinds: tuple[ConditionKind, ...]
    expected: tuple[tuple[ConditionKind, str], ...]
    rationale: str

    def expected_value(self, kind: ConditionKind) -> str | None:
        for k, v in self.expected:
            if k is kind:
                return v
        return None


@dataclass(frozen=True)
class DemoClassConfig:
    """Everything hand-reviewed about one ETIM class."""

    etim_class_id: str
    etim_class_name: str
    etim_release: str
    etim_language: str
    reviewed_on: str
    notes: str
    buyer_critical: frozenset[str]
    qualifier_rules: dict[str, QualifierRule]

    def rule_for(self, feature_id: str) -> QualifierRule | None:
        return self.qualifier_rules.get(feature_id)

    def is_buyer_critical(self, feature_id: str) -> bool:
        return feature_id in self.buyer_critical

    def check_against(self, etim_class: EtimClass) -> list[str]:
        """Problems with this config relative to the real ETIM class. Empty is good.

        Guards against the config drifting out of step with an ETIM release: a rule
        for a feature the class no longer carries would silently never fire, and a
        buyer-critical id that does not exist would quietly shrink the denominator of
        the coverage metric.
        """
        problems: list[str] = []
        if etim_class.class_id != self.etim_class_id:
            problems.append(
                f"config is for {self.etim_class_id}, checked against {etim_class.class_id}"
            )
        known = set(etim_class.feature_ids)
        for fid in sorted(self.buyer_critical - known):
            problems.append(f"buyer-critical feature {fid} is not on {etim_class.class_id}")
        for fid in sorted(set(self.qualifier_rules) - known):
            problems.append(f"qualifier rule for {fid}, which is not on {etim_class.class_id}")
        return problems


def _kinds(raw: list[str], *, where: str) -> tuple[ConditionKind, ...]:
    out: list[ConditionKind] = []
    for name in raw:
        try:
            out.append(ConditionKind(name))
        except ValueError as exc:
            raise ValueError(f"{where}: {name!r} is not a ConditionKind") from exc
    return tuple(out)


def parse_demo_class(data: dict, *, source: str = "<memory>") -> DemoClassConfig:
    """Build a config from already-parsed TOML. Raises on anything malformed."""
    class_id = data["etim_class_id"]
    rules: dict[str, QualifierRule] = {}
    for fid, body in (data.get("qualifiers") or {}).items():
        required = _kinds(body.get("required_kinds", []), where=f"{source}:{fid}")
        expected_raw = body.get("expected", {}) or {}
        expected = tuple(
            (k, expected_raw[k.value])
            for k in _kinds(list(expected_raw), where=f"{source}:{fid}.expected")
        )
        unrequired = [k for k, _ in expected if k not in required]
        if unrequired:
            raise ValueError(
                f"{source}:{fid} pins expected values for qualifier(s) it does not "
                f"require: {', '.join(k.value for k in unrequired)}"
            )
        rules[fid] = QualifierRule(
            feature_id=fid,
            required_kinds=required,
            expected=expected,
            rationale=body.get("rationale", ""),
        )

    return DemoClassConfig(
        etim_class_id=class_id,
        etim_class_name=data.get("etim_class_name", ""),
        etim_release=data.get("etim_release", ""),
        etim_language=data.get("etim_language", "EN"),
        reviewed_on=data.get("reviewed_on", ""),
        notes=(data.get("notes") or "").strip(),
        buyer_critical=frozenset((data.get("buyer_critical") or {}).get("feature_ids", [])),
        qualifier_rules=rules,
    )


@lru_cache(maxsize=16)
def load_demo_class(class_id: str, config_dir: Path | None = None) -> DemoClassConfig:
    """Load `data/demo_classes/<class_id>.toml`. Cached per path."""
    directory = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    path = directory / f"{class_id}.toml"
    if not path.exists():
        raise FileNotFoundError(
            f"no reviewed configuration for {class_id} at {path}. Classes without one "
            "have no buyer-critical subset and resolve every feature's condition "
            "completeness to UNKNOWN."
        )
    with path.open("rb") as fh:
        return parse_demo_class(tomllib.load(fh), source=path.name)


def available_demo_classes(config_dir: Path | None = None) -> tuple[str, ...]:
    directory = Path(config_dir) if config_dir is not None else DEFAULT_CONFIG_DIR
    if not directory.exists():
        return ()
    return tuple(sorted(p.stem for p in directory.glob("*.toml")))
