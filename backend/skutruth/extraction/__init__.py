"""Model-backed structured product extraction.

Gemini proposes candidate observations from a versioned manufacturer artifact;
deterministic code decides what any of it means. See ./README.md.
"""

from .config import (
    DEFAULT_LOCATION,
    DEFAULT_MODEL,
    ENDPOINT,
    ENV_LOCATION,
    ENV_MODEL,
    ENV_PROJECT,
    PROVIDER_NAME,
    VertexConfig,
)
from .errors import (
    ArtifactMismatchError,
    ExtractionError,
    IdentityNotExactError,
    MalformedModelResponseError,
)
from .models import (
    ExtractionCandidate,
    ExtractionRun,
    ExtractionTarget,
    RawModelExtraction,
    RejectedProposal,
    RejectionCode,
    ValidatedExtraction,
)
from .prompt import PROMPT_VERSION, SYSTEM_INSTRUCTION, build_user_prompt
from .provider import ExtractionCall, ProviderResult, StructuredExtractionProvider
from .service import (
    build_interaction_request,
    extract_product_attributes,
    require_exact_identity,
    validate_raw_extraction,
)

__all__ = [
    "DEFAULT_LOCATION",
    "DEFAULT_MODEL",
    "ENDPOINT",
    "ENV_LOCATION",
    "ENV_MODEL",
    "ENV_PROJECT",
    "PROMPT_VERSION",
    "PROVIDER_NAME",
    "SYSTEM_INSTRUCTION",
    "ArtifactMismatchError",
    "ExtractionCall",
    "ExtractionCandidate",
    "ExtractionError",
    "ExtractionRun",
    "ExtractionTarget",
    "IdentityNotExactError",
    "MalformedModelResponseError",
    "ProviderResult",
    "RawModelExtraction",
    "RejectedProposal",
    "RejectionCode",
    "StructuredExtractionProvider",
    "ValidatedExtraction",
    "VertexConfig",
    "build_interaction_request",
    "build_user_prompt",
    "extract_product_attributes",
    "require_exact_identity",
    "validate_raw_extraction",
]
