"""Deterministic record/replay for every external and model interaction.

See ./README.md for the design and the guarantees.
"""

from .errors import (
    InvalidCassetteError,
    ModeNotRequestableError,
    RecordedProviderError,
    ReplayError,
    ReplayMissError,
)
from .keys import KEY_VERSION, canonical_json, digest, is_valid_key
from .models import (
    CASSETTE_VERSION,
    Cassette,
    InteractionRequest,
    RecordedError,
    Usage,
)
from .redaction import PLACEHOLDER, REDACTION_VERSION, is_sensitive_key, redact, redact_text
from .runner import (
    InteractionResult,
    LiveResponse,
    is_mode_requestable,
    is_public_demo_safe,
    require_public_demo_safe,
    require_requestable,
    run_interaction,
)
from .store import (
    DEFAULT_FIXTURE_DIR,
    DEFAULT_RUNTIME_DIR,
    CassetteStore,
    fixture_store,
    runtime_store,
)

__all__ = [
    "CASSETTE_VERSION",
    "DEFAULT_FIXTURE_DIR",
    "DEFAULT_RUNTIME_DIR",
    "KEY_VERSION",
    "PLACEHOLDER",
    "REDACTION_VERSION",
    "Cassette",
    "CassetteStore",
    "InteractionRequest",
    "InteractionResult",
    "InvalidCassetteError",
    "LiveResponse",
    "ModeNotRequestableError",
    "RecordedError",
    "RecordedProviderError",
    "ReplayError",
    "ReplayMissError",
    "Usage",
    "canonical_json",
    "digest",
    "fixture_store",
    "is_mode_requestable",
    "is_public_demo_safe",
    "is_sensitive_key",
    "is_valid_key",
    "redact",
    "redact_text",
    "require_public_demo_safe",
    "require_requestable",
    "run_interaction",
    "runtime_store",
]
