"""Typed failures for the Unilog adapter.

Every one of these is a refusal to guess. A malformed header, an ambiguous
manufacturer string, or a record field nobody declared are all situations where
continuing would mean inventing structure the organizer did not supply — and the
delivery format is a contract we are explicitly told not to modify.
"""

from __future__ import annotations


class UnilogError(Exception):
    """Base class for every refusal in this package."""


class InputSchemaError(UnilogError):
    """The raw organizer input file's header is not usable."""


class MissingRequiredColumn(InputSchemaError):
    """A required input column is absent. Named explicitly, never inferred by position."""


class DuplicateColumn(InputSchemaError):
    """The same header appears twice, so a value cannot be attributed to one field."""


class MalformedRowError(UnilogError):
    """A data row does not match the header width."""


class DeliverySchemaError(UnilogError):
    """The 252-column delivery contract could not be established."""


class UnknownDeliveryField(UnilogError):
    """A value was assigned to a field the delivery schema does not declare.

    Refused rather than appended: the export order is fixed by the organizer, and a
    field we invented has nowhere legitimate to go.
    """
