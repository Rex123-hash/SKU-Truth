"""The submission-facing HTTP API.

A thin, typed view over the pipeline. It renders what the trust layers already decided;
it never decides anything itself. See `README.md` in this package for the routes, the
execution modes, and why the demo record is committed rather than re-derived at runtime.
"""

from .app import TRUST_NOTE, create_app
from .cases import DemoCase, DemoCaseFile, DemoCaseLibrary, load_demo_cases
from .config import API_VERSION, ApiSettings
from .errors import ApiError, ApiErrorCode, ApiException
from .models import (
    AiView,
    AnalyzeRequest,
    AttributesView,
    ClassificationView,
    DeliveryView,
    DemoIndex,
    EvidenceBasis,
    EvidenceLocatorView,
    ExecutionMode,
    HealthResponse,
    IdentityView,
    NormalizationView,
    ProductCard,
    ProductDetail,
    ProductSummary,
    ProposedAttribute,
    SchemaResponse,
    SourceView,
    Stage,
    StageStatus,
    TimelineEntry,
    VerifiedAttribute,
    WithheldAttribute,
)

__all__ = [
    "API_VERSION",
    "TRUST_NOTE",
    "AiView",
    "AnalyzeRequest",
    "ApiError",
    "ApiErrorCode",
    "ApiException",
    "ApiSettings",
    "AttributesView",
    "ClassificationView",
    "DeliveryView",
    "DemoCase",
    "DemoCaseFile",
    "DemoCaseLibrary",
    "DemoIndex",
    "EvidenceBasis",
    "EvidenceLocatorView",
    "ExecutionMode",
    "HealthResponse",
    "IdentityView",
    "NormalizationView",
    "ProductCard",
    "ProductDetail",
    "ProductSummary",
    "ProposedAttribute",
    "SchemaResponse",
    "SourceView",
    "Stage",
    "StageStatus",
    "TimelineEntry",
    "VerifiedAttribute",
    "WithheldAttribute",
    "create_app",
    "load_demo_cases",
]
