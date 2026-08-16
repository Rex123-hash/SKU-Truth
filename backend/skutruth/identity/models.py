"""Inputs and results for identity resolution.

There is deliberately **no confidence score anywhere in this module.** Identity here is
adjudicated from explicit facts, and a probability would invite a caller to treat 0.9 as
"exact enough". The disposition is the answer; the trace is the justification.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import IdentityDisposition, ProductInput

from .evidence import EvidenceAnchor


class DecisionStep(StrEnum):
    """Machine-readable reason codes. The trace is built only from these."""

    BRAND_EVIDENCE_IGNORED = "BRAND_EVIDENCE_IGNORED"
    NO_APPLICABLE_EVIDENCE = "NO_APPLICABLE_EVIDENCE"
    EXACT_REFERENCE_CONFIRMED = "EXACT_REFERENCE_CONFIRMED"
    BASE_REFERENCE_INCOMPLETE = "BASE_REFERENCE_INCOMPLETE"
    DISCRIMINATOR_REQUIRED = "DISCRIMINATOR_REQUIRED"
    DISCRIMINATOR_SUPPLIED = "DISCRIMINATOR_SUPPLIED"
    DISCRIMINATOR_UNRESOLVED = "DISCRIMINATOR_UNRESOLVED"
    SELECTION_NOT_MAPPED = "SELECTION_NOT_MAPPED"
    CANDIDATE_CONSTRUCTED = "CANDIDATE_CONSTRUCTED"
    CANDIDATE_UNCONFIRMED = "CANDIDATE_UNCONFIRMED"
    CONSTRUCTION_NOT_SUPPORTED = "CONSTRUCTION_NOT_SUPPORTED"
    VARIATION_AXIS_KNOWN = "VARIATION_AXIS_KNOWN"
    CONFLICT_EXACT_AND_INCOMPLETE = "CONFLICT_EXACT_AND_INCOMPLETE"
    CONFLICT_RIVAL_COMPLETION_CODES = "CONFLICT_RIVAL_COMPLETION_CODES"
    CONFLICT_RIVAL_EXACT_TARGETS = "CONFLICT_RIVAL_EXACT_TARGETS"


class DiscriminatorSelection(BaseModel):
    """A caller's answer to "which variant?".

    Matching is on `canonical_value`, never on `label`. Free text would make resolution
    depend on how a question happened to be worded.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)
    canonical_value: str = Field(min_length=1)
    label: str | None = Field(default=None, description="Display only; never matched on")


class TraceEntry(BaseModel):
    """One step of the decision, generated from an explicit fact."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    step: int = Field(ge=1)
    code: DecisionStep
    detail: str = Field(min_length=1)
    anchor: EvidenceAnchor | None = None

    def render(self) -> str:
        where = f" [{self.anchor.short}]" if self.anchor else ""
        return f"{self.step}. {self.detail}{where}"


class IdentityResolution(BaseModel):
    """What the input was determined to refer to, and why."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    input: ProductInput
    brand_normalized: str
    mpn_normalized: str

    disposition: IdentityDisposition
    exact_mpn: str | None = None

    supplied_discriminators: tuple[DiscriminatorSelection, ...] = ()
    unresolved_discriminators: tuple[str, ...] = ()
    candidate_references: tuple[str, ...] = ()
    candidate_exactness_confirmed: bool = Field(
        default=False,
        description="Whether an exact-reference fact independently confirmed a candidate. "
        "Constructing a candidate never sets this.",
    )

    known_variation_axes: tuple[str, ...] = Field(
        default=(), description="Other axes this reference varies along. Informational."
    )
    warnings: tuple[str, ...] = ()
    trace: tuple[TraceEntry, ...] = ()
    evidence_anchors: tuple[EvidenceAnchor, ...] = ()

    @model_validator(mode="after")
    def _exact_is_anchored_to_a_reference(self) -> IdentityResolution:
        """EXACT must name the reference, and nothing else may."""
        if self.disposition is IdentityDisposition.EXACT:
            if not self.exact_mpn:
                raise ValueError("EXACT requires exact_mpn")
        elif self.exact_mpn is not None:
            raise ValueError(
                f"{self.disposition} must not carry exact_mpn; a candidate is not a "
                "resolved reference"
            )
        return self

    @model_validator(mode="after")
    def _confirmation_implies_exact(self) -> IdentityResolution:
        if self.candidate_exactness_confirmed and self.disposition is not (
            IdentityDisposition.EXACT
        ):
            raise ValueError("candidate_exactness_confirmed is only meaningful for EXACT")
        return self

    @property
    def is_exact(self) -> bool:
        return self.disposition is IdentityDisposition.EXACT

    def explain(self) -> str:
        """The decision trace as readable lines. Nothing hidden, nothing added."""
        return "\n".join(entry.render() for entry in self.trace)


__all__ = [
    "DecisionStep",
    "DiscriminatorSelection",
    "IdentityResolution",
    "TraceEntry",
]
