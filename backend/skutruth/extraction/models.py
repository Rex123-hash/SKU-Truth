"""Extraction inputs and the two output levels.

Two levels are kept deliberately distinct:

* `RawModelExtraction` — exactly what the model returned, unedited. Kept even when it
  is wrong, because a bad proposal is evidence about the model and deleting it would
  make the stage look better than it is.
* `ValidatedExtraction` — what survived deterministic checks, plus every rejection and
  the reason for it.

**Neither is an accepted product attribute.** Nothing here carries a support grade, a
confidence score, or a verification status. A model saying `page=1, quote="18 A"` does
not make that quote verified; locating it mechanically is a later stage. Until then these
are proposals with provenance attached, and a test asserts no such field ever appears.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from skutruth.contracts import AttributeValue, ConditionSet, RunMode
from skutruth.replay.models import Usage


class RejectionCode(StrEnum):
    """Why a proposal did not become a candidate. Deterministic, never a judgement call."""

    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"
    MALFORMED_PROPOSAL = "MALFORMED_PROPOSAL"
    MISSING_SOURCE_FRAGMENT = "MISSING_SOURCE_FRAGMENT"
    PAGE_OUT_OF_RANGE = "PAGE_OUT_OF_RANGE"
    INVALID_VALUE = "INVALID_VALUE"


class ExtractionTarget(BaseModel):
    """The exact product and document one extraction call is about.

    Every field is required. An extraction that cannot say which reference, which class,
    and which artifact it read is not attributable to anything.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    brand: str = Field(min_length=1)
    exact_mpn: str = Field(min_length=1)
    etim_class_id: str = Field(pattern=r"^EC\d{6}$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_count: int = Field(ge=1)


class RawModelExtraction(BaseModel):
    """What the model returned, before any interpretation.

    `payload` is stored verbatim. It is not pruned, corrected, or reordered.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model: str = Field(min_length=1)
    prompt_version: str = Field(min_length=1)
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    payload: dict

    @property
    def proposed_features(self) -> dict:
        features = self.payload.get("features")
        return features if isinstance(features, dict) else {}

    @property
    def non_null_count(self) -> int:
        return sum(1 for v in self.proposed_features.values() if v is not None)


class ExtractionCandidate(BaseModel):
    """One proposal that survived deterministic validation.

    Still only a candidate. `source_fragment` and `page_number` say where the model
    *claims* the support is; nothing has looked. `conditions.completeness` was derived by
    `resolve_conditions`, never supplied by the model.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_feature_id: str = Field(pattern=r"^EF\d{6}$")
    feature_name: str = Field(min_length=1)
    value: AttributeValue
    conditions: ConditionSet
    source_fragment: str = Field(
        min_length=1, description="Model-supplied wording. Not a verified span."
    )
    page_number: int = Field(ge=1)
    buyer_critical: bool = False


class RejectedProposal(BaseModel):
    """A proposal that did not survive, kept with its reason."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_feature_id: str = Field(min_length=1)
    code: RejectionCode
    detail: str = Field(min_length=1)


class ValidatedExtraction(BaseModel):
    """The deterministic outcome over one raw model response."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    candidates: tuple[ExtractionCandidate, ...] = ()
    rejected: tuple[RejectedProposal, ...] = ()
    abstained_feature_ids: tuple[str, ...] = Field(
        default=(), description="Features the model explicitly declined to fill"
    )
    requested_feature_ids: tuple[str, ...] = ()

    @property
    def candidate_count(self) -> int:
        return len(self.candidates)

    def candidate(self, feature_id: str) -> ExtractionCandidate | None:
        for c in self.candidates:
            if c.etim_feature_id == feature_id:
                return c
        return None


class ExtractionRun(BaseModel):
    """One extraction call end to end, with provenance."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    target: ExtractionTarget
    raw: RawModelExtraction
    validated: ValidatedExtraction

    mode: RunMode
    replayed: bool
    cassette_key: str = Field(min_length=1)
    usage: Usage | None = None
    latency_seconds: float | None = Field(default=None, ge=0.0)

    def summary(self) -> str:
        v = self.validated
        return (
            f"{self.target.exact_mpn} · {self.raw.model} · "
            f"{len(v.requested_feature_ids)} requested · {self.raw.non_null_count} proposed · "
            f"{v.candidate_count} candidates · {len(v.rejected)} rejected · "
            f"{'REPLAY' if self.replayed else 'LIVE'}"
        )


__all__ = [
    "ExtractionCandidate",
    "ExtractionRun",
    "ExtractionTarget",
    "RawModelExtraction",
    "RejectedProposal",
    "RejectionCode",
    "ValidatedExtraction",
]
