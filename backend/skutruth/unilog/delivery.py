"""Delivery records, attribute slots, and the CSV writer.

A `DeliveryRecord` is bound to a `DeliverySchema` and can only hold fields that schema
declares. Assigning an undeclared field raises rather than appending: the export order is
the organizer's contract, and an invented column has nowhere legitimate to sit.

## Blank is not absent

The two worked examples emit attribute *labels* whose values are empty — `Model` and
`Plug Type` are present-but-blank. That is meaningful: the classpath template says the
attribute applies, and the source did not establish it. So slots are never compacted, and
`AttributeSlot` distinguishes a declared-but-blank slot from one that was never declared
at all. Dropping the blank ones would destroy the difference between "not applicable" and
"not found", which is exactly the distinction the rest of this codebase exists to keep.

## No value invention on export

A field never assigned exports as an empty string — never `None`, never the literal
`"None"` or `"null"`. Unicode is preserved as-is, so `FRIGIDAIRE®` and `CleanBoost™`
survive the round trip intact.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import IO, TYPE_CHECKING

from .classification import ClassificationProposal
from .errors import UnknownDeliveryField
from .input import RawProductRow
from .normalization import RowNormalization
from .schema import DeliverySchema

if TYPE_CHECKING:
    from .attributes import AttributeMapping

#: Input columns whose delivery header is byte-identical and whose meaning is therefore
#: not in question. Deliberately excludes PART_NUMBER and MANUFACTURER_PART_NUMBER: their
#: names merely *look* like Mfg_Part_Num, and the two examples do not prove the mapping.
PASSTHROUGH_FIELDS: tuple[str, ...] = (
    "Mfg_Part_Num",
    "Part_Desc",
    "E1_Brand",
    "Unilog_Brand",
    "DIB_Brand",
    "Part_Manuf",
)


@dataclass(frozen=True, slots=True)
class AttributeSlot:
    """One attribute triplet as it stands on a record."""

    index: int
    label: str
    value: str
    uom: str

    @property
    def is_declared(self) -> bool:
        """Whether the classpath template claims this attribute applies."""
        return bool(self.label.strip())

    @property
    def has_value(self) -> bool:
        return bool(self.value.strip())

    @property
    def is_declared_but_blank(self) -> bool:
        """Applies to the product, but the source did not establish it."""
        return self.is_declared and not self.has_value


class DeliveryRecord:
    """One output row, constrained to a schema."""

    def __init__(self, schema: DeliverySchema) -> None:
        self.schema = schema
        self._values: dict[str, str] = {}

    # -- assignment ----------------------------------------------------------

    def set(self, field: str, value: str | None) -> None:
        """Assign one field. `None` clears it; it never becomes the text "None"."""
        if not self.schema.has_field(field):
            raise UnknownDeliveryField(
                f"{field!r} is not a delivery field; the export contract declares "
                f"{self.schema.field_count} columns and cannot be extended here"
            )
        if value is None:
            self._values.pop(field, None)
            return
        self._values[field] = str(value)

    def update(self, values: Mapping[str, str | None]) -> None:
        for field, value in values.items():
            self.set(field, value)

    def get(self, field: str) -> str:
        """The assigned value, or an empty string. Unknown fields raise."""
        if not self.schema.has_field(field):
            raise UnknownDeliveryField(f"{field!r} is not a delivery field")
        return self._values.get(field, "")

    @property
    def assigned_fields(self) -> tuple[str, ...]:
        """Assigned fields, in schema order rather than assignment order."""
        return tuple(h for h in self.schema.headers if h in self._values)

    # -- attribute slots -----------------------------------------------------

    def set_attribute(
        self, index: int, label: str, value: str | None = None, uom: str | None = None
    ) -> None:
        """Fill one attribute slot. A declared label with a blank value is legitimate."""
        spec = next((s for s in self.schema.attribute_slots if s.index == index), None)
        if spec is None:
            raise UnknownDeliveryField(
                f"attribute slot {index} is not declared; the schema has "
                f"{self.schema.attribute_slot_count} slots"
            )
        self.set(spec.label_field, label)
        self.set(spec.value_field, value if value is not None else "")
        self.set(spec.uom_field, uom if uom is not None else "")

    def attribute_slots(self) -> tuple[AttributeSlot, ...]:
        """Every slot the schema declares, blanks included. Never compacted."""
        return tuple(
            AttributeSlot(
                index=spec.index,
                label=self._values.get(spec.label_field, ""),
                value=self._values.get(spec.value_field, ""),
                uom=self._values.get(spec.uom_field, ""),
            )
            for spec in self.schema.attribute_slots
        )

    def declared_attribute_slots(self) -> tuple[AttributeSlot, ...]:
        """Slots carrying a label — the classpath template's actual attribute list."""
        return tuple(s for s in self.attribute_slots() if s.is_declared)

    def apply_attribute_mapping(self, mapping: AttributeMapping) -> int:
        """Write an authority-gated mapping without changing schema or slot order.

        An unauthorized or out-of-scope profile exposes no delivery slots, so it writes
        nothing. Authorized profiles always write their labels in declared profile
        order; only committed candidate values supply VALUE/UOM cells.
        """
        slots = mapping.delivery_slots()
        declared = {spec.index for spec in self.schema.attribute_slots}
        unknown = tuple(slot.index for slot in slots if slot.index not in declared)
        if unknown:
            raise UnknownDeliveryField(
                f"attribute profile references slots outside the delivery schema: {unknown}"
            )
        for slot in slots:
            self.set_attribute(slot.index, slot.label, slot.value, slot.uom)
        return len(slots)

    # -- export --------------------------------------------------------------

    def to_row(self) -> list[str]:
        """Values in canonical schema order, unassigned fields as empty strings."""
        return [self._values.get(h, "") for h in self.schema.headers]

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return f"DeliveryRecord({len(self._values)}/{self.schema.field_count} assigned)"


def record_from_raw_row(
    row: RawProductRow,
    schema: DeliverySchema,
    *,
    normalization: RowNormalization | None = None,
    classification: ClassificationProposal | None = None,
    attributes: AttributeMapping | None = None,
) -> DeliveryRecord:
    """Carry across only the input columns whose delivery header is identical.

    The *raw* value is passed through, placeholders included: the delivery file's own
    examples echo `-- Unbranded --` back in the passthrough block, so cleaning here would
    disagree with the organizer's own output. Cleaned values remain available on
    `RawProductRow` for the stages that need them.
    """
    record = DeliveryRecord(schema)
    for field in PASSTHROUGH_FIELDS:
        if schema.has_field(field):
            record.set(field, row.raw_value(field))
    if normalization is not None:
        if normalization.row_number != row.row_number:
            raise ValueError(
                f"normalization belongs to row {normalization.row_number}, "
                f"not row {row.row_number}"
            )
        identity_values = {
            "MANUFACTURER_NAME": normalization.manufacturer.delivery_value,
            "BRAND_NAME": normalization.brand.delivery_value,
        }
        for field, value in identity_values.items():
            if schema.has_field(field) and value is not None:
                record.set(field, value)
    if classification is not None:
        if classification.row_number != row.row_number:
            raise ValueError(
                f"classification belongs to row {classification.row_number}, "
                f"not row {row.row_number}"
            )
        for field, value in classification.delivery.delivery_values:
            if schema.has_field(field):
                record.set(field, value)
    if attributes is not None:
        if row.mfg_part_num != attributes.record_key:
            raise ValueError(
                f"attribute mapping belongs to {attributes.record_key!r}, "
                f"not {row.mfg_part_num!r}"
            )
        record.apply_attribute_mapping(attributes)
    return record


def write_delivery_csv(
    records: Iterable[DeliveryRecord], schema: DeliverySchema, handle: IO[str]
) -> int:
    """Write the header then every record, in schema order. Returns rows written.

    The handle must be opened with `newline=''` so the csv module controls line endings;
    otherwise an embedded newline in a description corrupts the file on Windows.
    """
    writer = csv.writer(handle)
    writer.writerow(list(schema.headers))
    count = 0
    for record in records:
        if record.schema is not schema and not record.schema.matches(schema):
            raise UnknownDeliveryField(
                "record was built against a different delivery schema; its column order "
                "would not match the header being written"
            )
        writer.writerow(record.to_row())
        count += 1
    return count


__all__ = [
    "PASSTHROUGH_FIELDS",
    "AttributeSlot",
    "DeliveryRecord",
    "record_from_raw_row",
    "write_delivery_csv",
]
