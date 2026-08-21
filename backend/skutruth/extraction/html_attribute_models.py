"""Typed contracts for source-bound HTML attribute model proposals.

The profile is intentionally local and generic.  It is neither ETIM nor an official
Unilog label profile, and every surviving value remains a ``MODEL_PROPOSAL``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from skutruth.contracts import RunMode
from skutruth.ingest.html import HtmlEvidenceLocator
from skutruth.replay.models import Usage
from skutruth.unilog.attributes import AttributeCandidate, AttributeValueKind


class HtmlProfileAuthority(StrEnum):
    LOCAL_DEMO_INTERNAL = "LOCAL_DEMO_INTERNAL"


class HtmlAttributeKey(StrEnum):
    LIGHT_COUNT_DESCRIPTOR = "lighting.light_count_descriptor"
    DIFFUSER_DESCRIPTION = "lighting.diffuser_description"
    OVERALL_DEPTH = "lighting.overall_depth"
    OVERALL_HEIGHT = "lighting.overall_height"
    OVERALL_WIDTH = "lighting.overall_width"
    FINISH_NAME = "lighting.finish_name"
    INSTALLATION_ORIENTATION = "lighting.installation_orientation"
    SHADE_DIMENSIONS = "lighting.shade_dimensions"
    SOCKET_CONFIGURATION = "lighting.socket_configuration"
    LAMP_WATTAGE = "lighting.lamp_wattage"


class HtmlAttributeConcept(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: HtmlAttributeKey
    label: str = Field(min_length=1)
    value_kind: AttributeValueKind
    description: str = Field(min_length=1)


class HtmlAttributeProfile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    profile_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    authority: HtmlProfileAuthority
    official_unilog_labels: bool = False
    concepts: tuple[HtmlAttributeConcept, ...]

    def concept(self, source_key: HtmlAttributeKey) -> HtmlAttributeConcept:
        return next(item for item in self.concepts if item.source_key is source_key)


HTML_ATTRIBUTE_PROFILE = HtmlAttributeProfile(
    profile_id="lighting-html-local-demo",
    version="lighting-html-local-demo@v1",
    authority=HtmlProfileAuthority.LOCAL_DEMO_INTERNAL,
    official_unilog_labels=False,
    concepts=(
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.LIGHT_COUNT_DESCRIPTOR,
            label="Light count descriptor",
            value_kind=AttributeValueKind.TEXT,
            description="Source wording such as 3-Light; do not derive a count.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.DIFFUSER_DESCRIPTION,
            label="Diffuser description",
            value_kind=AttributeValueKind.TEXT,
            description="Explicit shade, lens, or glass wording.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.OVERALL_DEPTH,
            label="Overall depth",
            value_kind=AttributeValueKind.NUMBER,
            description="Explicit overall depth numeric value.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.OVERALL_HEIGHT,
            label="Overall height",
            value_kind=AttributeValueKind.NUMBER,
            description="Explicit overall height numeric value.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.OVERALL_WIDTH,
            label="Overall width",
            value_kind=AttributeValueKind.NUMBER,
            description="Explicit overall width numeric value.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.FINISH_NAME,
            label="Finish name",
            value_kind=AttributeValueKind.ENUM,
            description="Finish explicitly bound to the exact target variant.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.INSTALLATION_ORIENTATION,
            label="Installation orientation",
            value_kind=AttributeValueKind.ENUM,
            description="Explicit allowed installation orientation.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.SHADE_DIMENSIONS,
            label="Shade dimensions",
            value_kind=AttributeValueKind.TEXT,
            description="Verbatim compound shade-dimension wording.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.SOCKET_CONFIGURATION,
            label="Socket configuration",
            value_kind=AttributeValueKind.TEXT,
            description="Verbatim socket count/type/base wording.",
        ),
        HtmlAttributeConcept(
            source_key=HtmlAttributeKey.LAMP_WATTAGE,
            label="Lamp wattage",
            value_kind=AttributeValueKind.NUMBER,
            description="Explicit lamp wattage number and source UOM.",
        ),
    ),
)


class RawHtmlAttributeProposal(BaseModel):
    """Strict model output; a missing locator survives parsing only to be rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: HtmlAttributeKey
    raw_value: str = Field(min_length=1)
    raw_uom: str
    value_kind: AttributeValueKind
    source_excerpt: str = Field(min_length=1)
    locator: HtmlEvidenceLocator | None = None


class RawHtmlAttributeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    proposals: tuple[RawHtmlAttributeProposal, ...]


class HtmlLocatorBinding(StrEnum):
    EXACT = "EXACT"


class HtmlAttributeRejectionCode(StrEnum):
    MISSING_LOCATOR = "MISSING_LOCATOR"
    LOCATOR_INVALID = "LOCATOR_INVALID"
    SOURCE_MISMATCH = "SOURCE_MISMATCH"
    VALUE_KIND_MISMATCH = "VALUE_KIND_MISMATCH"
    INVALID_VALUE = "INVALID_VALUE"
    DUPLICATE_SOURCE_KEY = "DUPLICATE_SOURCE_KEY"


class HtmlAttributeRejectedProposal(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    source_key: HtmlAttributeKey
    code: HtmlAttributeRejectionCode
    detail: str = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class SourceBoundHtmlAttributeCandidate:
    candidate: AttributeCandidate
    locator: HtmlEvidenceLocator
    source_excerpt: str
    binding: HtmlLocatorBinding = HtmlLocatorBinding.EXACT


@dataclass(frozen=True, slots=True)
class ValidatedHtmlAttributeExtraction:
    candidates: tuple[SourceBoundHtmlAttributeCandidate, ...] = ()
    rejected: tuple[HtmlAttributeRejectedProposal, ...] = ()
    requested_source_keys: tuple[HtmlAttributeKey, ...] = ()
    abstained_source_keys: tuple[HtmlAttributeKey, ...] = ()

    def candidate(self, source_key: HtmlAttributeKey) -> SourceBoundHtmlAttributeCandidate | None:
        return next(
            (item for item in self.candidates if item.candidate.source_key == source_key.value),
            None,
        )


class HtmlAttributeTarget(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    brand: str = Field(min_length=1)
    exact_mpn: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    content_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    profile_id: str = Field(min_length=1)
    profile_version: str = Field(min_length=1)


@dataclass(frozen=True, slots=True)
class HtmlAttributeExtractionRun:
    target: HtmlAttributeTarget
    raw: RawHtmlAttributeResponse
    validated: ValidatedHtmlAttributeExtraction
    mode: RunMode
    replayed: bool
    cassette_key: str
    usage: Usage | None = None
    latency_seconds: float | None = None

    def summary(self) -> str:
        return (
            f"{self.target.exact_mpn} · {len(self.validated.requested_source_keys)} requested · "
            f"{len(self.raw.proposals)} proposed · {len(self.validated.candidates)} bound · "
            f"{len(self.validated.rejected)} rejected · "
            f"{'REPLAY' if self.replayed else 'LIVE'}"
        )


JsonObject = dict[str, Any]


__all__ = [
    "HTML_ATTRIBUTE_PROFILE",
    "HtmlAttributeConcept",
    "HtmlAttributeExtractionRun",
    "HtmlAttributeKey",
    "HtmlAttributeProfile",
    "HtmlAttributeRejectedProposal",
    "HtmlAttributeRejectionCode",
    "HtmlAttributeTarget",
    "HtmlLocatorBinding",
    "HtmlProfileAuthority",
    "RawHtmlAttributeProposal",
    "RawHtmlAttributeResponse",
    "SourceBoundHtmlAttributeCandidate",
    "ValidatedHtmlAttributeExtraction",
]
