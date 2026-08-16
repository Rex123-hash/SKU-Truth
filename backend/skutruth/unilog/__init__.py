"""Unilog organizer adapter: raw input in, delivery contract out.

Deterministic only. No model, no fuzzy matching, no classification, no content
generation — see ./README.md for why each of those is deliberately absent.
"""

from .conformance import (
    ConformanceCode,
    ConformanceIssue,
    ConformanceReport,
    check_rows,
    check_schema,
)
from .delivery import (
    PASSTHROUGH_FIELDS,
    AttributeSlot,
    DeliveryRecord,
    record_from_raw_row,
    write_delivery_csv,
)
from .errors import (
    DeliverySchemaError,
    DuplicateColumn,
    InputSchemaError,
    MalformedRowError,
    MissingRequiredColumn,
    UnilogError,
    UnknownDeliveryField,
)
from .input import (
    REQUIRED_COLUMNS,
    RawProductRow,
    read_rows,
    read_unilog_input,
    validate_input_header,
)
from .manufacturer import ManufacturerParse, ParsedManufacturer, parse_part_manuf
from .placeholders import (
    BARE_HYPHEN_FIELDS,
    DOCUMENTED_PLACEHOLDERS,
    clean,
    is_placeholder,
)
from .schema import AttributeSlotSpec, DeliverySchema

__all__ = [
    "BARE_HYPHEN_FIELDS",
    "DOCUMENTED_PLACEHOLDERS",
    "PASSTHROUGH_FIELDS",
    "REQUIRED_COLUMNS",
    "AttributeSlot",
    "AttributeSlotSpec",
    "ConformanceCode",
    "ConformanceIssue",
    "ConformanceReport",
    "DeliveryRecord",
    "DeliverySchema",
    "DeliverySchemaError",
    "DuplicateColumn",
    "InputSchemaError",
    "MalformedRowError",
    "ManufacturerParse",
    "MissingRequiredColumn",
    "ParsedManufacturer",
    "RawProductRow",
    "UnilogError",
    "UnknownDeliveryField",
    "check_rows",
    "check_schema",
    "clean",
    "is_placeholder",
    "parse_part_manuf",
    "read_rows",
    "read_unilog_input",
    "record_from_raw_row",
    "validate_input_header",
    "write_delivery_csv",
]
