"""SKUTruth frozen data contracts.

These types are the interface between every stage of the pipeline, the API, the
frontend, and the evaluation harness. They are frozen: components adapt to the
contract, the contract does not adapt to components. See ./README.md.
"""

from .enums import (
    AttributeStatus,
    ConflictCause,
    EtimFeatureType,
    EvidenceModality,
    IdentityKind,
    ResolvedBy,
    RunMode,
    SkuSpecificity,
    SourceType,
)
from .evidence import Conflict, DocumentLocator, Evidence, EvidenceCluster
from .product import (
    CommerceContent,
    ConfidenceFactors,
    GoldenRecord,
    ProductAttribute,
    ProductIdentity,
    ProductInput,
    RunCost,
    VariantAxis,
)
from .value import (
    VALUE_KIND_FOR_FEATURE_TYPE,
    AlphanumericValue,
    AttributeValue,
    LogicalValue,
    NumericValue,
    RangeValue,
)

__all__ = [
    "VALUE_KIND_FOR_FEATURE_TYPE",
    "AlphanumericValue",
    "AttributeStatus",
    "AttributeValue",
    "CommerceContent",
    "ConfidenceFactors",
    "Conflict",
    "ConflictCause",
    "DocumentLocator",
    "EtimFeatureType",
    "Evidence",
    "EvidenceCluster",
    "EvidenceModality",
    "GoldenRecord",
    "IdentityKind",
    "LogicalValue",
    "NumericValue",
    "ProductAttribute",
    "ProductIdentity",
    "ProductInput",
    "RangeValue",
    "ResolvedBy",
    "RunCost",
    "RunMode",
    "SkuSpecificity",
    "SourceType",
    "VariantAxis",
]
