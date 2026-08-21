"""Deterministic product identity resolution.

Turns a minimal brand + MPN input plus typed identity evidence into one of the frozen
`IdentityDisposition` values. See ./README.md for the rules this stage enforces — above
all that constructing a candidate reference is not the same thing as confirming one.
"""

from .errors import IdentityError, MalformedConstructionRule
from .eval_adapter import identity_prediction_fields, to_case_prediction
from .evidence import (
    DEFAULT_CONSTRUCTION_TEMPLATE,
    DiscriminatorMappingFact,
    EvidenceAnchor,
    ExactReferenceFact,
    IdentityEvidence,
    ReferenceCompletionFact,
    VariationAxisFact,
    brands_match,
    canonical_brand,
)
from .html import (
    HtmlIdentityDecision,
    HtmlIdentityObservation,
    HtmlIdentityObservationKind,
    HtmlIdentityReason,
    HtmlIdentityResolution,
    HtmlIdentityWarning,
    resolve_html_product_identity,
)
from .models import (
    DecisionStep,
    DiscriminatorSelection,
    IdentityResolution,
    TraceEntry,
)
from .resolver import resolve_identity

__all__ = [
    "DEFAULT_CONSTRUCTION_TEMPLATE",
    "DecisionStep",
    "DiscriminatorMappingFact",
    "DiscriminatorSelection",
    "EvidenceAnchor",
    "ExactReferenceFact",
    "IdentityError",
    "IdentityEvidence",
    "IdentityResolution",
    "HtmlIdentityDecision",
    "HtmlIdentityObservation",
    "HtmlIdentityObservationKind",
    "HtmlIdentityReason",
    "HtmlIdentityResolution",
    "HtmlIdentityWarning",
    "MalformedConstructionRule",
    "ReferenceCompletionFact",
    "TraceEntry",
    "VariationAxisFact",
    "brands_match",
    "canonical_brand",
    "identity_prediction_fields",
    "resolve_identity",
    "resolve_html_product_identity",
    "to_case_prediction",
]
