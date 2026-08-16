"""Adjudication and assembly failures.

These are *engineering* failures — a malformed mapping, more attributes than the
delivery template can hold. They are deliberately not the same thing as a fact being
refused: a refused fact is a normal, typed outcome carried on `AdjudicatedFact`, and
raising for it would make the ordinary case exceptional.
"""

from __future__ import annotations


class AdjudicationError(Exception):
    """Base class for every refusal in this package."""


class MalformedMappingError(AdjudicationError):
    """A mapping specification cannot mean what it says."""


class SlotCapacityError(AdjudicationError):
    """More mapped attributes than the delivery template declares slots for.

    Raised rather than truncated. Dropping the tail would silently lose verified,
    committed facts, and the loss would be invisible in the exported row — the file
    would look complete because every slot it has is full.
    """


__all__ = ["AdjudicationError", "MalformedMappingError", "SlotCapacityError"]
