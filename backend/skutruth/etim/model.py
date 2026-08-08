"""In-memory representation of the ETIM classification model.

Read-only. Built once from the vendored ETIM 10.0 archive and shared across the
process; see `loader.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

from skutruth.contracts import EtimFeatureType


@dataclass(frozen=True, slots=True)
class EtimAllowedValue:
    """One member of an ETIM picklist (`A` features)."""

    value_id: str  # EVxxxxxxx
    text: str
    sort_nr: int = 0


@dataclass(frozen=True, slots=True)
class EtimFeature:
    """One expected attribute on one class.

    A feature is only meaningful in the context of a class: the same FEATUREID can
    appear on several classes with different units and different allowed values.
    """

    feature_id: str  # EFxxxxxx
    name: str
    feature_type: EtimFeatureType
    unit: str | None  # ETIMUNIT.UNITDESC, e.g. "A", "kW", "mm"
    sort_nr: int
    class_feature_nr: str  # ETIMARTCLASSFEATURENR, the join key for allowed values
    allowed_values: tuple[EtimAllowedValue, ...] = ()

    @property
    def is_picklist(self) -> bool:
        return self.feature_type is EtimFeatureType.ALPHANUMERIC

    def allowed_texts(self) -> tuple[str, ...]:
        return tuple(v.text for v in self.allowed_values)

    def find_allowed(self, text: str) -> EtimAllowedValue | None:
        """Case- and whitespace-insensitive lookup of a picklist member."""
        needle = " ".join(text.split()).casefold()
        for v in self.allowed_values:
            if " ".join(v.text.split()).casefold() == needle:
                return v
        return None


# No `slots=True` on the two types below: they memoise lookup indexes with
# `functools.cached_property`, which needs an instance `__dict__`.
@dataclass(frozen=True)
class EtimClass:
    """One ETIM product class and its full expected feature set."""

    class_id: str  # ECxxxxxx
    name: str
    group_id: str
    group_name: str
    version: str
    features: tuple[EtimFeature, ...]
    synonyms: tuple[str, ...] = ()

    @cached_property
    def _by_id(self) -> dict[str, EtimFeature]:
        return {f.feature_id: f for f in self.features}

    def feature(self, feature_id: str) -> EtimFeature | None:
        return self._by_id.get(feature_id)

    @property
    def feature_ids(self) -> tuple[str, ...]:
        return tuple(f.feature_id for f in self.features)

    def __len__(self) -> int:
        return len(self.features)


@dataclass(frozen=True, slots=True)
class EtimStats:
    """Parsed record counts, excluding CSV headers.

    Produced by `scripts/etim_stats.py` and asserted in tests, so a count quoted in
    the pitch is always a number this repository can reproduce.
    """

    classes: int
    groups: int
    features: int
    units: int
    values: int
    class_feature_rows: int
    class_feature_value_rows: int
    synonym_rows: int

    def as_dict(self) -> dict[str, int]:
        return {
            "classes": self.classes,
            "groups": self.groups,
            "features": self.features,
            "units": self.units,
            "values": self.values,
            "class_feature_rows": self.class_feature_rows,
            "class_feature_value_rows": self.class_feature_value_rows,
            "synonym_rows": self.synonym_rows,
        }


@dataclass(frozen=True, slots=True)
class IntegrityIssue:
    """A referential-integrity violation found while loading."""

    kind: str
    detail: str


@dataclass(frozen=True)
class EtimModel:
    """The whole classification model, indexed for lookup."""

    release: str  # e.g. "10.0"
    language: str  # ETIM language code; "EN" is the open master model
    classes: dict[str, EtimClass]
    units: dict[str, str] = field(default_factory=dict)  # EUxxxxxx -> "A"
    stats: EtimStats | None = None
    integrity_issues: tuple[IntegrityIssue, ...] = ()

    @property
    def version_label(self) -> str:
        """Stamped onto every exported record, per the ODC-BY attribution requirement."""
        return f"ETIM {self.release} ({self.language})"

    def get(self, class_id: str) -> EtimClass | None:
        return self.classes.get(class_id)

    def require(self, class_id: str) -> EtimClass:
        cls = self.classes.get(class_id)
        if cls is None:
            raise KeyError(f"unknown ETIM class {class_id!r} in release {self.release}")
        return cls

    def __len__(self) -> int:
        return len(self.classes)

    @cached_property
    def _synonym_index(self) -> dict[str, list[str]]:
        """Casefolded class name or synonym -> class ids.

        Built from the 37k-row ETIM synonym map, which lets us generate class
        candidates lexically with no model call at all.
        """
        index: dict[str, list[str]] = {}
        for cls in self.classes.values():
            for phrase in (cls.name, *cls.synonyms):
                key = " ".join(phrase.split()).casefold()
                index.setdefault(key, []).append(cls.class_id)
        return index

    def lookup_exact(self, phrase: str) -> list[EtimClass]:
        """Classes whose name or a registered synonym equals `phrase`."""
        key = " ".join(phrase.split()).casefold()
        return [self.classes[cid] for cid in self._synonym_index.get(key, ())]

    def search(self, query: str, limit: int = 12) -> list[EtimClass]:
        """Deterministic lexical class candidates, best first.

        Token-overlap scored against class names and synonyms. This exists so that
        class *candidate generation* costs nothing; a model only ever picks from a
        short list it is given, and can never invent a class id.
        """
        q_tokens = _tokens(query)
        if not q_tokens:
            return []

        scored: dict[str, float] = {}
        for phrase, class_ids in self._synonym_index.items():
            p_tokens = _tokens(phrase)
            if not p_tokens:
                continue
            overlap = q_tokens & p_tokens
            if not overlap:
                continue
            # Jaccard, nudged towards phrases the query covers well, so that
            # "contactor" ranks "Power contactor, AC switching" above a 9-word class
            # that merely contains the word.
            score = len(overlap) / len(q_tokens | p_tokens) + 0.25 * (
                len(overlap) / len(p_tokens)
            )
            for cid in class_ids:
                if score > scored.get(cid, 0.0):
                    scored[cid] = score

        ranked = sorted(scored.items(), key=lambda kv: (-kv[1], kv[0]))
        return [self.classes[cid] for cid, _ in ranked[:limit]]


_SPLIT = str.maketrans({c: " " for c in ",;/()[]{}-_+.:\\\"'"})


def _tokens(text: str) -> set[str]:
    return {t for t in text.translate(_SPLIT).casefold().split() if len(t) > 1}
