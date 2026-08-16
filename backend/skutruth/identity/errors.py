"""Typed identity failures.

Resolution itself never raises — an unresolvable input is a *disposition*, not an
error, and turning "we don't know" into an exception would tempt callers to swallow it.
These cover malformed evidence, which is a programming or curation fault.
"""

from __future__ import annotations


class IdentityError(Exception):
    """Base class for every refusal in this package."""


class MalformedConstructionRule(IdentityError, ValueError):
    """A completion rule's construction template cannot be applied safely.

    Rejected rather than guessed at. A template we only half-understand would build a
    reference string that looks authoritative and points at nothing.

    Also a `ValueError` so that raising it inside a pydantic validator is collected into
    a `ValidationError` like any other field problem, while callers validating a template
    directly still get the typed error.
    """
