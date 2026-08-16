"""Typed extraction failures.

A model proposing nothing, or proposing something invalid, is a *result* — recorded as
a rejection and reported. These errors cover the cases where the stage cannot legitimately
run at all.
"""

from __future__ import annotations


class ExtractionError(Exception):
    """Base class for every refusal in this package."""


class IdentityNotExactError(ExtractionError):
    """Extraction was requested for a product whose identity is not resolved.

    Refused rather than delegated. Asking a model to work out which product a family
    stem "probably" means would move the exact-identity decision out of the deterministic
    resolver and into a guess — which is the one thing the identity gate exists to prevent.
    """


class MalformedModelResponseError(ExtractionError):
    """The provider returned something that is not a usable extraction payload.

    Structured output makes this unlikely, not impossible. A truncated or non-JSON
    response is a failure, never an empty extraction: silently treating it as "the
    document establishes nothing" would turn a provider fault into a factual claim.
    """


class ArtifactMismatchError(ExtractionError):
    """The supplied bytes are not the artifact whose hash the request names."""
