"""The delivery output contract: exact headers, in exact order.

The portal is explicit — *"Please do not change or modify the headers."* So the header
sequence is treated as an immutable contract: never sorted, never renamed, never
reordered for tidiness. Internal Python names may be friendlier; the exported file is
byte-for-byte the organizer's shape.

## Why the schema is derived at runtime

The header list is not checked into this repository. The organizer pack carries no stated
redistribution grant, and while a list of column *names* is far less sensitive than data
rows, "probably fine" is not a licence. Deriving the contract from the local organizer
file at runtime avoids the question entirely, and it buys a real engineering property as
well: `fingerprint()` detects the organizer quietly changing the expected format, which a
checked-in copy would instead silently disagree with.

Tests therefore build synthetic schemas and never read the organizer file.

## Attribute slots

The schema declares repeating `ATTRIBUTE_LABEL n` / `ATTRIBUTE_VALUE n` /
`ATTRIBUTE_UOM n` triplets. The count is *discovered*, not assumed: the sample has 50, but
a future template with a different depth must load without a code change. A triplet
missing one of its three members makes the schema invalid — a label with nowhere to put
its value is a broken contract, not a tolerable quirk.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from .errors import DeliverySchemaError

_ATTRIBUTE = re.compile(r"^ATTRIBUTE_(?P<part>LABEL|VALUE|UOM) (?P<index>\d+)$")

_ATTRIBUTE_PARTS = ("LABEL", "VALUE", "UOM")

#: Deterministic groupings over the delivery headers. Presentation and analysis only —
#: membership never affects export order, which stays the schema's own sequence.
GROUP_PATTERNS: tuple[tuple[str, str], ...] = (
    ("source_urls", r"^(MFR URL|Ref URL \d+)$"),
    (
        "input_passthrough",
        r"^(PART_NUMBER|Dept|Class|Fine|SKU - MY_PART_NUMBER|Mfg_Part_Num|Part_Desc|"
        r"E1_Brand|Unilog_Brand|DIB_Brand|Part_Manuf)$",
    ),
    (
        "identity",
        r"^(MANUFACTURER_NAME|BRAND_NAME|TRADE_NAME|MANUFACTURER_PART_NUMBER|"
        r"ALTERNATE_PART_NUMBER)$",
    ),
    ("classification", r"^(Classpath|UNSPSC)$"),
    (
        "content",
        r"^(MOBILE_DESC|INVOICE_DESC|SHORT_DESC|LONG_DESC\d*|RETAIL_DESC|"
        r"MARKETING_DESCRIPTION|Product Name)$",
    ),
    ("item_features", r"^ITEM_FEATURES_\d+$"),
    ("content_extras", r"^(With|Standard/Approvals|Prop 65|Application|Includes)$"),
    ("attributes", r"^ATTRIBUTE_(LABEL|VALUE|UOM) \d+$"),
    ("identifiers", r"^(UPC|EAN|GTIN)$"),
    (
        "commercial",
        r"^(Warranty|List Price|Selling Qty|Selling UOM|Standard Packaging Information)$",
    ),
    ("package_dimensions", r"^(LENGTH|HEIGHT|WIDTH|WEIGHT|VOLUME)(_UOM)?$"),
    (
        "digital_assets",
        r"^(Product Image|Alternate Image \d+|SDS(_\d+)?|Warranty Information|Catalog|"
        r"Specification Sheet|Instruction/Installation Manual|Service Manual|"
        r"Owners/User Manual|Line Drawing|MTR|RoHS|Full Engineering Drawing|"
        r"Energy Star Guide|Technical Bulletin|Submittal|Compatibility Chart|Size Chart|"
        r"Product Label/Insert|Video Link( \d+)?)$",
    ),
    ("flags", r"^(Country Of Origin|Discontinued|Actual Image \(Yes/No\))$"),
)


@dataclass(frozen=True, slots=True)
class AttributeSlotSpec:
    """The three header names making up one attribute slot."""

    index: int
    label_field: str
    value_field: str
    uom_field: str


class DeliverySchema:
    """An ordered, validated delivery header contract."""

    def __init__(self, headers: Iterable[str]) -> None:
        self._headers: tuple[str, ...] = tuple(headers)
        if not self._headers:
            raise DeliverySchemaError("delivery schema has no columns")

        duplicates = sorted({h for h in self._headers if self._headers.count(h) > 1})
        if duplicates:
            raise DeliverySchemaError(
                f"delivery header repeats {duplicates}; the export contract requires "
                f"each column to be addressable by name"
            )

        self._index = {name: i for i, name in enumerate(self._headers)}
        self._slots = self._discover_slots()

    # -- construction --------------------------------------------------------

    @classmethod
    def from_csv(cls, path: str | Path) -> DeliverySchema:
        """Derive the contract from the organizer's expected-output file's header row."""
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration as exc:
                raise DeliverySchemaError(f"{path} is empty") from exc
        return cls(header)

    def _discover_slots(self) -> tuple[AttributeSlotSpec, ...]:
        found: dict[int, dict[str, str]] = {}
        for name in self._headers:
            match = _ATTRIBUTE.match(name)
            if match:
                index = int(match.group("index"))
                found.setdefault(index, {})[match.group("part")] = name

        slots: list[AttributeSlotSpec] = []
        for index in sorted(found):
            parts = found[index]
            missing = [p for p in _ATTRIBUTE_PARTS if p not in parts]
            if missing:
                raise DeliverySchemaError(
                    f"attribute slot {index} is incomplete: missing "
                    f"{', '.join('ATTRIBUTE_' + m + ' ' + str(index) for m in missing)}. "
                    f"A label with nowhere to put its value is a broken contract."
                )
            slots.append(
                AttributeSlotSpec(
                    index=index,
                    label_field=parts["LABEL"],
                    value_field=parts["VALUE"],
                    uom_field=parts["UOM"],
                )
            )
        return tuple(slots)

    # -- accessors -----------------------------------------------------------

    @property
    def headers(self) -> tuple[str, ...]:
        """The canonical export order. Never sorted."""
        return self._headers

    @property
    def field_count(self) -> int:
        return len(self._headers)

    @property
    def attribute_slots(self) -> tuple[AttributeSlotSpec, ...]:
        return self._slots

    @property
    def attribute_slot_count(self) -> int:
        return len(self._slots)

    def has_field(self, name: str) -> bool:
        return name in self._index

    def position(self, name: str) -> int:
        if name not in self._index:
            raise DeliverySchemaError(f"{name!r} is not a delivery field")
        return self._index[name]

    def groups(self) -> dict[str, tuple[str, ...]]:
        """Headers bucketed for analysis. Every header lands somewhere or in `other`."""
        buckets: dict[str, list[str]] = {name: [] for name, _ in GROUP_PATTERNS}
        buckets["other"] = []
        for header in self._headers:
            for name, pattern in GROUP_PATTERNS:
                if re.match(pattern, header):
                    buckets[name].append(header)
                    break
            else:
                buckets["other"].append(header)
        return {k: tuple(v) for k, v in buckets.items()}

    # -- integrity -----------------------------------------------------------

    def canonical_json(self) -> str:
        """Byte-stable serialisation of the ordered header names, and nothing else."""
        return json.dumps(
            {"version": 1, "headers": list(self._headers)},
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def fingerprint(self) -> str:
        """Content address of the ordered headers.

        Order-sensitive by construction, so a reordered contract fingerprints
        differently. Sample row *values* are deliberately not hashed: the schema is the
        contract, and hashing data would make the fingerprint change for the wrong reason.
        """
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def matches(self, other: DeliverySchema) -> bool:
        return self.fingerprint() == other.fingerprint()

    def __len__(self) -> int:
        return len(self._headers)

    def __contains__(self, name: object) -> bool:
        return name in self._index

    def __repr__(self) -> str:  # pragma: no cover - diagnostics
        return (
            f"DeliverySchema({self.field_count} fields, "
            f"{self.attribute_slot_count} attribute slots, "
            f"{self.fingerprint()[:12]}…)"
        )


__all__ = ["GROUP_PATTERNS", "AttributeSlotSpec", "DeliverySchema"]
