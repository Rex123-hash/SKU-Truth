"""Typed identity evidence facts.

The resolver adjudicates over these, never over document text or model prose. That
separation is the point:

    document parser -> evidence facts -> identity resolver

so the resolver imports no PDF library, and swapping how a fact was obtained cannot
change how identity is decided.

## What these facts are not

An `EvidenceAnchor` records *where a reviewer can go and look* — artifact hash, page,
publisher, and a short statement of what was observed there. It deliberately carries no
`EvidenceVerification`: span verification does not exist yet, and stamping `EXACT_SPAN`
on a hand-curated fact would claim a mechanical check nobody ran. When that milestone
lands it strengthens these anchors; it does not change identity logic.

Anchors also do not go through `SourceArtifact`. That contract requires a `SourceType`,
and the frozen enum has no clean category for a manufacturer catalogue, so the real
catalogue we ingested carries `source_type=null`. Forcing one here would mean inventing
provenance to satisfy a type, so the anchor stays narrower than the contract.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from skutruth.contracts import IdentityScope
from skutruth.contracts.mpn import canonical_mpn, mpn_matches

from .errors import MalformedConstructionRule

#: The only placeholders a construction template may contain.
TEMPLATE_BASE = "{base}"
TEMPLATE_CODE = "{code}"

#: The construction most manufacturers use, and the only one assumed by default.
#: Recorded on every mapping fact rather than hardcoded in the resolver, because
#: "append the code" is a property of a publisher's scheme, not a law.
DEFAULT_CONSTRUCTION_TEMPLATE = "{base}{code}"


def validate_construction_template(template: str) -> None:
    """Accept only templates this version can apply in full.

    Exactly the two known placeholders, and nothing else that looks like one. A template
    carrying an unrecognised placeholder is refused rather than applied partially, since
    a half-substituted reference would still be a well-formed-looking string.
    """
    if TEMPLATE_BASE not in template or TEMPLATE_CODE not in template:
        raise MalformedConstructionRule(
            f"construction_template must contain {TEMPLATE_BASE} and {TEMPLATE_CODE}; "
            f"got {template!r}"
        )
    remainder = template.replace(TEMPLATE_BASE, "").replace(TEMPLATE_CODE, "")
    if "{" in remainder or "}" in remainder:
        raise MalformedConstructionRule(
            f"construction_template has placeholders this version cannot apply: {template!r}"
        )


def canonical_brand(brand: str | None) -> str | None:
    """Fold case and whitespace. Nothing else.

    Deliberately not fuzzy: a bare company name does not become its full legal name, and
    no prefix match is performed. Evidence for one manufacturer must never resolve
    another because the MPN text happens to coincide, and a deterministic alias map — if
    it is ever needed — belongs in explicit configuration, not in a normaliser that
    quietly widens over time.
    """
    if brand is None:
        return None
    folded = " ".join(brand.split()).upper()
    return folded or None


def brands_match(a: str | None, b: str | None) -> bool:
    """True only when both brands are present and canonically identical."""
    ca, cb = canonical_brand(a), canonical_brand(b)
    return ca is not None and ca == cb


class EvidenceAnchor(BaseModel):
    """Where a fact came from, in terms a reviewer can act on."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    page_number: int | None = Field(default=None, ge=1)
    publisher: str | None = None
    identity_scope: IdentityScope | None = Field(
        default=None, description="How tightly the source artifact binds to a reference"
    )
    observed_statement: str = Field(
        min_length=1,
        description="Minimal derived statement of what the source says. Not a verified span.",
    )

    @property
    def short(self) -> str:
        page = f" p{self.page_number}" if self.page_number is not None else ""
        return f"{self.artifact_sha256[:12]}…{page}"


class _BrandedFact(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    brand: str = Field(min_length=1)
    anchor: EvidenceAnchor

    def applies_to_brand(self, brand: str | None) -> bool:
        return brands_match(self.brand, brand)


class ReferenceCompletionFact(_BrandedFact):
    """Records that a base reference is incomplete and names what completes it.

    This is what makes a reference a family stem rather than a product. It says nothing
    about which value of K is right, and the resolver must never pick one.
    """

    base_mpn: str = Field(min_length=1)
    discriminator_key: str = Field(min_length=1)

    def applies_to(self, brand: str | None, mpn: str | None) -> bool:
        return self.applies_to_brand(brand) and mpn_matches(self.base_mpn, mpn)


class DiscriminatorMappingFact(_BrandedFact):
    """Records how one discriminator value is spelled as a completion code.

    Carries its own construction template, because how a completed reference is spelled
    is a property of the publisher's numbering scheme. Assuming concatenation for every
    manufacturer would be a guess dressed as a rule.
    """

    base_mpn: str = Field(min_length=1)
    discriminator_key: str = Field(min_length=1)
    canonical_value: str = Field(
        min_length=1, description="Deterministic value key, not a display label"
    )
    completion_code: str = Field(min_length=1)
    construction_template: str = DEFAULT_CONSTRUCTION_TEMPLATE
    label: str | None = Field(default=None, description="Human-facing wording, display only")

    @model_validator(mode="after")
    def _template_is_understood(self) -> DiscriminatorMappingFact:
        validate_construction_template(self.construction_template)
        return self

    def applies_to(self, brand: str | None, mpn: str | None) -> bool:
        return self.applies_to_brand(brand) and mpn_matches(self.base_mpn, mpn)

    def construct(self, base_mpn: str) -> str:
        """Build the completed reference. Deterministic and total for a valid template."""
        return self.construction_template.replace(TEMPLATE_BASE, base_mpn).replace(
            TEMPLATE_CODE, self.completion_code
        )


class ExactReferenceFact(_BrandedFact):
    """Records that a reference exists as an exact manufacturer product.

    The only thing that can confirm a candidate. Anchored to one reference: evidence for
    a sibling is evidence about the sibling.
    """

    exact_mpn: str = Field(min_length=1)
    commercial_status: str | None = Field(
        default=None, description="Recorded only when the source states it, e.g. Commercialised"
    )

    def confirms(self, brand: str | None, mpn: str | None) -> bool:
        return self.applies_to_brand(brand) and mpn_matches(self.exact_mpn, mpn)


class VariationAxisFact(_BrandedFact):
    """Records another axis along which a base reference varies.

    Informational by default. Real catalogues vary along more axes than the one that
    completes the printed reference, and a resolver that reports only the completing
    discriminator would imply that binding it removes all ambiguity.

    `blocks_resolution` is opt-in and means the evidence explicitly says this axis must
    also be bound before the reference resolves. It is not inferred.
    """

    base_mpn: str = Field(min_length=1)
    axis_key: str = Field(min_length=1)
    description: str = Field(min_length=1)
    blocks_resolution: bool = False

    def applies_to(self, brand: str | None, mpn: str | None) -> bool:
        return self.applies_to_brand(brand) and mpn_matches(self.base_mpn, mpn)


class IdentityEvidence(BaseModel):
    """Everything the resolver is allowed to reason from, for one resolution."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    completion_facts: tuple[ReferenceCompletionFact, ...] = ()
    mapping_facts: tuple[DiscriminatorMappingFact, ...] = ()
    exact_facts: tuple[ExactReferenceFact, ...] = ()
    variation_axes: tuple[VariationAxisFact, ...] = ()

    def completions_for(self, brand: str, mpn: str) -> tuple[ReferenceCompletionFact, ...]:
        return tuple(f for f in self.completion_facts if f.applies_to(brand, mpn))

    def mappings_for(
        self, brand: str, mpn: str, discriminator_key: str, canonical_value: str
    ) -> tuple[DiscriminatorMappingFact, ...]:
        return tuple(
            f
            for f in self.mapping_facts
            if f.applies_to(brand, mpn)
            and f.discriminator_key == discriminator_key
            and f.canonical_value == canonical_value
        )

    def exact_for(self, brand: str, mpn: str) -> tuple[ExactReferenceFact, ...]:
        return tuple(f for f in self.exact_facts if f.confirms(brand, mpn))

    def axes_for(self, brand: str, mpn: str) -> tuple[VariationAxisFact, ...]:
        return tuple(f for f in self.variation_axes if f.applies_to(brand, mpn))

    def facts_for_other_brands(self, brand: str, mpn: str) -> int:
        """Count of facts about this MPN that belong to a different manufacturer."""
        others = 0
        for fact in self.completion_facts:
            others += mpn_matches(fact.base_mpn, mpn) and not fact.applies_to_brand(brand)
        for fact in self.exact_facts:
            others += mpn_matches(fact.exact_mpn, mpn) and not fact.applies_to_brand(brand)
        return others


__all__ = [
    "DEFAULT_CONSTRUCTION_TEMPLATE",
    "DiscriminatorMappingFact",
    "EvidenceAnchor",
    "ExactReferenceFact",
    "IdentityEvidence",
    "ReferenceCompletionFact",
    "VariationAxisFact",
    "brands_match",
    "canonical_brand",
    "canonical_mpn",
    "validate_construction_template",
]
