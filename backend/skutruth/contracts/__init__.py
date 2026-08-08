"""SKUTruth frozen data contracts.

These types are the interface between every stage of the pipeline, the API, the
frontend, and the evaluation harness. They are frozen: components adapt to the
contract, the contract does not adapt to components. See ./README.md.
"""

from .conditions import Condition, ConditionSet
from .coverage import CoverageReport
from .enums import (
    Applicability,
    AttributeStatus,
    ConditionCompleteness,
    ConditionKind,
    ConflictCause,
    DerivationKind,
    DiscoveryMethod,
    EtimFeatureType,
    EvidenceModality,
    EvidenceVerification,
    FamilyInvariance,
    IdentityDisposition,
    IdentityScope,
    ResolvedBy,
    RunMode,
    SourceType,
    SupportGrade,
    WithheldReason,
)
from .evidence import Conflict, Evidence, EvidenceGroup, SourceArtifact, SpanLocator
from .product import (
    GoldenRecord,
    ProductAttribute,
    ProductIdentity,
    ProductInput,
    RunCost,
    RunProvenance,
    VariantAxis,
    accepted_attribute_factors,
)
from .support import (
    KNOWN_FACTOR_KEYS,
    SUPPORT_RULE_VERSION,
    SupportFactors,
    compute_support_factors,
    derive_support_grade,
)
from .value import (
    VALUE_KIND_FOR_FEATURE_TYPE,
    AlphanumericValue,
    AttributeValue,
    Derivation,
    LogicalValue,
    NumericValue,
    RangeValue,
)

__all__ = [
    "KNOWN_FACTOR_KEYS",
    "SUPPORT_RULE_VERSION",
    "VALUE_KIND_FOR_FEATURE_TYPE",
    "AlphanumericValue",
    "Applicability",
    "AttributeStatus",
    "AttributeValue",
    "Condition",
    "ConditionCompleteness",
    "ConditionKind",
    "ConditionSet",
    "Conflict",
    "ConflictCause",
    "CoverageReport",
    "Derivation",
    "DerivationKind",
    "DiscoveryMethod",
    "EtimFeatureType",
    "Evidence",
    "EvidenceGroup",
    "EvidenceModality",
    "EvidenceVerification",
    "FamilyInvariance",
    "GoldenRecord",
    "IdentityDisposition",
    "IdentityScope",
    "LogicalValue",
    "NumericValue",
    "ProductAttribute",
    "ProductIdentity",
    "ProductInput",
    "RangeValue",
    "ResolvedBy",
    "RunCost",
    "RunMode",
    "RunProvenance",
    "SourceArtifact",
    "SourceType",
    "SpanLocator",
    "SupportFactors",
    "SupportGrade",
    "VariantAxis",
    "WithheldReason",
    "accepted_attribute_factors",
    "compute_support_factors",
    "derive_support_grade",
]
