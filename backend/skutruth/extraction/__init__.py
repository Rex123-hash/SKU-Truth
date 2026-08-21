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
    HtmlSourcePayloadTooLargeError,
    IdentityNotExactError,
    MalformedModelResponseError,
)
from .html_attribute_models import (
    HTML_ATTRIBUTE_PROFILE,
    HtmlAttributeConcept,
    HtmlAttributeExtractionRun,
    HtmlAttributeKey,
    HtmlAttributeProfile,
    HtmlAttributeRejectedProposal,
    HtmlAttributeRejectionCode,
    HtmlAttributeTarget,
    HtmlLocatorBinding,
    HtmlProfileAuthority,
    RawHtmlAttributeProposal,
    RawHtmlAttributeResponse,
    SourceBoundHtmlAttributeCandidate,
    ValidatedHtmlAttributeExtraction,
)
from .html_attribute_prompt import (
    HTML_ATTRIBUTE_PROMPT_VERSION,
    HTML_ATTRIBUTE_SYSTEM_INSTRUCTION,
    build_html_attribute_user_prompt,
)
from .html_attribute_service import (
    HTML_ATTRIBUTE_SCHEMA_VERSION,
    HTML_SOURCE_MEDIA_TYPE,
    HTML_SOURCE_PAYLOAD_VERSION,
    MAX_HTML_SOURCE_PAYLOAD_BYTES,
    build_html_interaction_request,
    build_html_source_payload,
    extract_html_attribute_candidates,
    validate_html_attribute_response,
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
    "HTML_ATTRIBUTE_PROFILE",
    "HTML_ATTRIBUTE_PROMPT_VERSION",
    "HTML_ATTRIBUTE_SCHEMA_VERSION",
    "HTML_ATTRIBUTE_SYSTEM_INSTRUCTION",
    "HTML_SOURCE_MEDIA_TYPE",
    "HTML_SOURCE_PAYLOAD_VERSION",
    "MAX_HTML_SOURCE_PAYLOAD_BYTES",
    "ExtractionCall",
    "ExtractionCandidate",
    "ExtractionError",
    "ExtractionRun",
    "ExtractionTarget",
    "HtmlAttributeConcept",
    "HtmlAttributeExtractionRun",
    "HtmlAttributeKey",
    "HtmlAttributeProfile",
    "HtmlAttributeRejectedProposal",
    "HtmlAttributeRejectionCode",
    "HtmlAttributeTarget",
    "HtmlLocatorBinding",
    "HtmlProfileAuthority",
    "HtmlSourcePayloadTooLargeError",
    "IdentityNotExactError",
    "MalformedModelResponseError",
    "ProviderResult",
    "RawModelExtraction",
    "RawHtmlAttributeProposal",
    "RawHtmlAttributeResponse",
    "RejectedProposal",
    "RejectionCode",
    "StructuredExtractionProvider",
    "SourceBoundHtmlAttributeCandidate",
    "ValidatedExtraction",
    "ValidatedHtmlAttributeExtraction",
    "VertexConfig",
    "build_interaction_request",
    "build_html_attribute_user_prompt",
    "build_html_interaction_request",
    "build_html_source_payload",
    "build_user_prompt",
    "extract_product_attributes",
    "extract_html_attribute_candidates",
    "require_exact_identity",
    "validate_raw_extraction",
    "validate_html_attribute_response",
]
