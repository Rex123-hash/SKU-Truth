"""Typed API failures.

A demo that swallows failures is worse than one that fails visibly: the whole claim of
this project is that it refuses rather than guesses, and an error contract is where that
claim is most easily broken. So every failure that reaches a client is one of these
codes, with the stage it happened at, and nothing else -- no traceback, no filesystem
path, no provider message, no resource id.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from .models import Stage


class ApiErrorCode(StrEnum):
    """What went wrong, in terms the UI can branch on."""

    #: The requested demo case does not exist.
    DEMO_CASE_NOT_FOUND = "DEMO_CASE_NOT_FOUND"
    #: The request body did not satisfy the input contract.
    INVALID_REQUEST = "INVALID_REQUEST"
    #: No stored evidence exists for this product, so replay cannot answer.
    REPLAY_NOT_AVAILABLE = "REPLAY_NOT_AVAILABLE"
    #: The manufacturer site refused the fetch with a rate limit.
    SOURCE_RATE_LIMITED = "SOURCE_RATE_LIMITED"
    #: Search returned results, but none established the exact reference.
    NO_EXACT_SOURCE = "NO_EXACT_SOURCE"
    #: Acquisition was attempted and did not produce a stored artifact.
    SOURCE_ACQUISITION_FAILED = "SOURCE_ACQUISITION_FAILED"
    #: The stored document did not prove it covers this exact SKU.
    IDENTITY_WITHHELD = "IDENTITY_WITHHELD"
    #: LIVE was requested and the live provider is not configured or failed.
    LIVE_MODE_UNAVAILABLE = "LIVE_MODE_UNAVAILABLE"
    #: A live provider returned a typed failure. Never downgraded to replay.
    LIVE_PROVIDER_FAILED = "LIVE_PROVIDER_FAILED"


class ApiError(BaseModel):
    """The only failure shape this API emits."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: ApiErrorCode
    stage: Stage | None = None
    message: str
    retryable: bool = False
    details: dict[str, str] = {}


class ApiException(Exception):  # noqa: N818 - the name is the contract, not the suffix
    """Raised inside the API layer; rendered by one handler as an `ApiError`."""

    def __init__(
        self,
        code: ApiErrorCode,
        message: str,
        *,
        status_code: int = 400,
        stage: Stage | None = None,
        retryable: bool = False,
        details: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.error = ApiError(
            code=code,
            stage=stage,
            message=message,
            retryable=retryable,
            details=details or {},
        )
        self.status_code = status_code


__all__ = ["ApiError", "ApiErrorCode", "ApiException"]
