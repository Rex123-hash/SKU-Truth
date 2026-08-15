"""Evaluation manifests: the locked statement of what truth is.

A manifest is the thing a reported number points back at. `manifest_fingerprint` is
what lets us say *"these metrics came from this set"* rather than asking anyone to
take it on trust — and what makes it obvious if the locked truth moved after a
disappointing run.

Validation is deliberately unforgiving. A manifest that contradicts itself, or that
lets one product family sit on both sides of the split, produces numbers that look
fine and mean nothing.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import Applicability, AttributeStatus, IdentityDisposition

from .models import EvalCase, ReviewStatus, Split

#: Bumped when the manifest schema changes. Participates in the fingerprint, so a
#: schema change cannot silently reuse an old fingerprint.
MANIFEST_SCHEMA_VERSION = "eval-manifest@v1"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_DIR = _REPO_ROOT / "data" / "eval" / "manifests"


class ManifestValidationError(ValueError):
    """A manifest that would produce meaningless numbers."""

    def __init__(self, problems: list[str]) -> None:
        listed = "\n  - ".join(problems)
        super().__init__(f"manifest is not usable:\n  - {listed}")
        self.problems = problems


class CoverageSummary(BaseModel):
    """What a manifest actually covers. Reported so nobody has to infer it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    cases: int
    manufacturers: int
    families: int
    etim_classes: int
    dev_cases: int
    locked_test_cases: int
    synthetic_cases: int
    reviewed_cases: int

    def display(self) -> str:
        return (
            f"{self.cases} cases · {self.manufacturers} manufacturers · "
            f"{self.families} families · {self.etim_classes} ETIM classes · "
            f"dev {self.dev_cases} / locked {self.locked_test_cases}"
        )


class EvaluationManifest(BaseModel):
    """A named, versioned, fingerprinted set of evaluation cases."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    manifest_id: str = Field(min_length=1)
    manifest_version: str = Field(min_length=1)
    schema_version: str = MANIFEST_SCHEMA_VERSION
    description: str = ""
    cases: tuple[EvalCase, ...] = ()

    @classmethod
    def build(cls, **kwargs) -> EvaluationManifest:
        """Construct with a typed `ManifestValidationError` on failure.

        Direct construction validates too, but Pydantic wraps the error. This factory
        surfaces the problem list intact so a caller can report every issue at once.
        """
        problems = validate_cases(tuple(kwargs.get("cases", ())))
        if problems:
            raise ManifestValidationError(problems)
        return cls(**kwargs)

    @model_validator(mode="after")
    def _is_internally_consistent(self) -> EvaluationManifest:
        problems = validate_cases(self.cases)
        if problems:
            raise ManifestValidationError(problems)
        return self

    # -- fingerprint ---------------------------------------------------------

    def canonical_dict(self) -> dict:
        """Fingerprint material: identity, schema version, and truth.

        Cases are sorted by `case_id`. Ordering within the file carries no meaning —
        case ids are unique and the scorer looks them up — so a reordered manifest is
        the same manifest, and should not appear to be a different locked set. What
        must change the fingerprint is any change to the truth itself.

        `description` is excluded: prose about the set is not part of the set.
        """
        return {
            "schema_version": self.schema_version,
            "manifest_id": self.manifest_id,
            "manifest_version": self.manifest_version,
            "cases": [
                case.model_dump(mode="json")
                for case in sorted(self.cases, key=lambda c: c.case_id)
            ],
        }

    def canonical_json(self) -> str:
        return json.dumps(
            self.canonical_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def fingerprint(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    # -- views ---------------------------------------------------------------

    def for_split(self, split: Split) -> tuple[EvalCase, ...]:
        return tuple(c for c in self.cases if c.split is split)

    def case(self, case_id: str) -> EvalCase | None:
        for c in self.cases:
            if c.case_id == case_id:
                return c
        return None

    def coverage(self, split: Split | None = None) -> CoverageSummary:
        cases = self.cases if split is None else self.for_split(split)
        return CoverageSummary(
            cases=len(cases),
            manufacturers=len({c.manufacturer for c in cases}),
            families=len({c.product_family_id for c in cases}),
            etim_classes=len({c.etim_class_id for c in cases if c.etim_class_id}),
            dev_cases=sum(1 for c in cases if c.split is Split.DEV),
            locked_test_cases=sum(1 for c in cases if c.split is Split.LOCKED_TEST),
            synthetic_cases=sum(1 for c in cases if c.review_status is ReviewStatus.SYNTHETIC),
            reviewed_cases=sum(1 for c in cases if c.review_status is ReviewStatus.REVIEWED),
        )

    @property
    def contains_only_synthetic_cases(self) -> bool:
        """True when nothing here may be quoted as a benchmark result."""
        return bool(self.cases) and all(c.is_synthetic for c in self.cases)


def validate_cases(cases: tuple[EvalCase, ...]) -> list[str]:
    """Every problem with a case set, collected rather than raised one at a time."""
    problems: list[str] = []

    duplicates = [cid for cid, n in Counter(c.case_id for c in cases).items() if n > 1]
    for cid in sorted(duplicates):
        problems.append(f"duplicate case_id {cid!r}")

    # A family that appears in both splits lets the system learn the family's pattern
    # during development and then be scored on a sibling, which is not a test.
    splits_by_family: dict[str, set[Split]] = defaultdict(set)
    for case in cases:
        splits_by_family[case.product_family_id].add(case.split)
    for family, splits in sorted(splits_by_family.items()):
        if len(splits) > 1:
            names = ", ".join(sorted(s.value for s in splits))
            problems.append(
                f"product family {family!r} appears in more than one split ({names}); "
                "families must not straddle DEV and LOCKED_TEST"
            )

    for case in cases:
        problems.extend(_validate_case(case))

    return problems


def _validate_case(case: EvalCase) -> list[str]:
    problems: list[str] = []
    where = f"case {case.case_id}"

    if (
        case.expected_identity.disposition is IdentityDisposition.EXACT
        and not case.expected_identity.exact_mpn
    ):
        problems.append(f"{where}: EXACT identity truth without an exact MPN")

    if (
        case.expected_identity.disposition is IdentityDisposition.FAMILY_OR_INCOMPLETE_REFERENCE
        and not case.expected_identity.missing_discriminators
    ):
        problems.append(
            f"{where}: FAMILY_OR_INCOMPLETE_REFERENCE truth that names no missing "
            "discriminator is unfalsifiable"
        )

    for attr in case.expected_attributes:
        aw = f"{where} / {attr.etim_feature_id}"
        if attr.applicability is Applicability.NOT_APPLICABLE and attr.buyer_critical:
            problems.append(f"{aw}: marked buyer-critical and NOT_APPLICABLE")
        if (
            attr.applicability is Applicability.NOT_APPLICABLE
            and attr.expected_status is AttributeStatus.ACCEPTED
        ):
            problems.append(f"{aw}: NOT_APPLICABLE but expected to be ACCEPTED")
        if attr.acceptable_withheld_reasons and attr.expected_status is AttributeStatus.ACCEPTED:
            problems.append(f"{aw}: expects ACCEPTED but also lists acceptable withheld reasons")

    return problems


def validate_against_etim(manifest: EvaluationManifest) -> list[str]:
    """Check claimed ETIM class and feature ids against the loaded release.

    Kept separate from construction because it needs the ETIM archive. A manifest
    should be loadable without it; being *checkable* against it is a stronger step
    taken deliberately.
    """
    from skutruth.etim import load_etim

    model = load_etim()
    problems: list[str] = []
    for case in manifest.cases:
        if case.etim_class_id is None:
            continue
        etim_class = model.get(case.etim_class_id)
        if etim_class is None:
            problems.append(f"case {case.case_id}: unknown ETIM class {case.etim_class_id}")
            continue
        known = set(etim_class.feature_ids)
        for attr in case.expected_attributes:
            if attr.etim_feature_id not in known:
                problems.append(
                    f"case {case.case_id}: {attr.etim_feature_id} is not a feature of "
                    f"{case.etim_class_id}"
                )
    return problems


def load_manifest(path: Path | str) -> EvaluationManifest:
    """Load and validate a manifest from JSON."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"no evaluation manifest at {p}")
    return EvaluationManifest.model_validate_json(p.read_text(encoding="utf-8"))


def load_named_manifest(name: str, directory: Path | None = None) -> EvaluationManifest:
    return load_manifest((directory or DEFAULT_MANIFEST_DIR) / f"{name}.json")


def available_manifests(directory: Path | None = None) -> tuple[str, ...]:
    d = directory or DEFAULT_MANIFEST_DIR
    if not d.is_dir():
        return ()
    return tuple(sorted(p.stem for p in d.glob("*.json")))
