"""ETIM 10.0 classification model — the deterministic backbone of SKUTruth.

Provides the expected attribute set per product class (the denominator of our
completeness metric), canonical units, and allowed picklist values. Loaded from the
vendored ODC-BY licensed release; see data/etim/ATTRIBUTION.md.
"""

from .demo_classes import (
    DemoClassConfig,
    QualifierRule,
    available_demo_classes,
    load_demo_class,
)
from .loader import (
    DEFAULT_ARCHIVE,
    DEFAULT_LANGUAGE,
    DEFAULT_RELEASE,
    EXPECTED_ARCHIVE_SHA256,
    archive_sha256,
    load_etim,
)
from .model import (
    EtimAllowedValue,
    EtimClass,
    EtimFeature,
    EtimModel,
    EtimStats,
    IntegrityIssue,
)
from .schema_gen import (
    EXTRACTION_SCHEMA_VERSION,
    ClassExtractionSchema,
    FeatureSchema,
    build_extraction_schema,
)
from .validators import (
    RawCondition,
    RawFeatureValue,
    Severity,
    ValidationCode,
    ValidationIssue,
    ValidationResult,
    build_value,
    resolve_conditions,
    validate_conditions,
    validate_feature_value,
)

__all__ = [
    "EXTRACTION_SCHEMA_VERSION",
    "ClassExtractionSchema",
    "DemoClassConfig",
    "FeatureSchema",
    "QualifierRule",
    "RawCondition",
    "RawFeatureValue",
    "Severity",
    "ValidationCode",
    "ValidationIssue",
    "ValidationResult",
    "available_demo_classes",
    "build_extraction_schema",
    "build_value",
    "load_demo_class",
    "resolve_conditions",
    "validate_conditions",
    "validate_feature_value",
    "DEFAULT_ARCHIVE",
    "DEFAULT_LANGUAGE",
    "DEFAULT_RELEASE",
    "EXPECTED_ARCHIVE_SHA256",
    "EtimAllowedValue",
    "EtimClass",
    "EtimFeature",
    "EtimModel",
    "EtimStats",
    "IntegrityIssue",
    "archive_sha256",
    "load_etim",
]
