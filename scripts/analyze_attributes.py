"""Report the organizer-example attribute contract and verify exact block round trips.

Usage:

    python scripts/analyze_attributes.py --delivery-format <expected-output.csv>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from skutruth.unilog import (  # noqa: E402
    DeliveryRecord,
    load_organizer_attribute_catalog,
    map_organizer_attribute_example,
)


def _value_comparison(first: str, second: str) -> str:
    if not first and not second:
        return "BOTH VALUE BLANK"
    if not first or not second:
        return "ONE VALUE BLANK"
    if first == second:
        return "IDENTICAL VALUE"
    return "DIFFERENT VALUE"


def analyze(delivery_path: Path) -> dict:
    catalog = load_organizer_attribute_catalog(delivery_path)
    if len(catalog.examples) != 2:
        raise ValueError(
            f"organizer example analysis expects 2 rows, found {len(catalog.examples)}"
        )
    profile = catalog.derive_profile(internal_family="DISHWASHER")
    first, second = catalog.examples

    comparisons = []
    for left, right in zip(first.slots, second.slots, strict=True):
        if not (left.label or right.label or left.value or right.value or left.uom or right.uom):
            continue
        comparisons.append(
            {
                "slot": left.index,
                "label": left.label,
                "row_1_value": left.value,
                "row_1_uom": left.uom,
                "row_2_value": right.value,
                "row_2_uom": right.uom,
                "label_comparison": (
                    "IDENTICAL LABEL" if left.label == right.label else "DIFFERENT LABEL"
                ),
                "value_comparison": _value_comparison(left.value, right.value),
                "uom_comparison": (
                    "UOM DIFFERENCE" if left.uom != right.uom else "IDENTICAL UOM"
                ),
            }
        )

    round_trips = {}
    for example in catalog.examples:
        record = DeliveryRecord(catalog.schema)
        mapping = map_organizer_attribute_example(example, profile)
        record.apply_attribute_mapping(mapping)
        expected = tuple(
            (slot.label, slot.value, slot.uom) for slot in example.slots
        )
        actual = tuple(
            (slot.label, slot.value, slot.uom) for slot in record.attribute_slots()
        )
        round_trips[example.record_key] = {
            "exact_50_triplets": actual == expected,
            "mapping_decision": mapping.decision.value,
        }

    value_states = Counter(item["value_comparison"] for item in comparisons)
    differing_slots = [
        item["slot"]
        for item in comparisons
        if item["row_1_value"] != item["row_2_value"]
        or item["row_1_uom"] != item["row_2_uom"]
    ]
    empty_slots = [
        spec.index
        for spec in catalog.schema.attribute_slots
        if all(
            not next(slot for slot in row.slots if slot.index == spec.index).label
            and not next(slot for slot in row.slots if slot.index == spec.index).value
            and not next(slot for slot in row.slots if slot.index == spec.index).uom
            for row in catalog.examples
        )
    ]
    return {
        "contract": {
            "fields": catalog.schema.field_count,
            "attribute_slots": catalog.schema.attribute_slot_count,
            "triplet_naming": "ATTRIBUTE_LABEL n / ATTRIBUTE_VALUE n / ATTRIBUTE_UOM n",
            "slot_order": [slot.index for slot in catalog.schema.attribute_slots],
        },
        "examples": [
            {
                "record_key": row.record_key,
                "labels_populated": row.labels_populated,
                "values_populated": row.values_populated,
                "uoms_populated": row.uoms_populated,
            }
            for row in catalog.examples
        ],
        "shared_ordered_labels": {
            "count": len(profile.slots),
            "labels": [slot.label for slot in profile.slots],
        },
        "later_empty_slots": empty_slots,
        "differences": {
            "slot_count": len(differing_slots),
            "slots": differing_slots,
            "value_states": dict(value_states),
            "uom_difference_slots": [
                item["slot"]
                for item in comparisons
                if item["uom_comparison"] == "UOM DIFFERENCE"
            ],
        },
        "comparisons": comparisons,
        "profile": {
            "id": profile.profile_id,
            "authority": profile.authority.value,
            "scope": profile.scope.detail,
            "exact_record_keys": list(profile.scope.exact_record_keys),
            "internal_family_context": profile.scope.internal_family,
            "candidate_classpath_context": profile.scope.candidate_classpath,
            "proves": "shared ordered labels in the two supplied organizer examples",
            "does_not_prove": "a universal or official dishwasher attribute schema or LOV",
        },
        "round_trips": round_trips,
    }


def render(report: dict) -> str:
    contract = report["contract"]
    lines = [
        "UNILOG ATTRIBUTE CONTRACT REPORT",
        f"delivery schema      {contract['fields']} fields",
        f"attribute triplets  {contract['attribute_slots']}",
        f"triplet naming      {contract['triplet_naming']}",
        "",
        "examples",
    ]
    for row in report["examples"]:
        lines.append(
            f"  {row['record_key']}: labels={row['labels_populated']} "
            f"values={row['values_populated']} UOMs={row['uoms_populated']}"
        )
    shared = report["shared_ordered_labels"]
    lines += [
        "",
        f"shared ordered labels ({shared['count']})",
        *[f"  {index:02d}  {label}" for index, label in enumerate(shared["labels"], 1)],
        "",
        "slot comparison",
        "  slot | label | row 1 value | UOM | row 2 value | UOM | classifications",
    ]
    for item in report["comparisons"]:
        states = [item["label_comparison"], item["value_comparison"]]
        if item["uom_comparison"] == "UOM DIFFERENCE":
            states.append(item["uom_comparison"])
        lines.append(
            f"  {item['slot']:02d} | {item['label']} | {item['row_1_value']} | "
            f"{item['row_1_uom']} | {item['row_2_value']} | {item['row_2_uom']} | "
            f"{', '.join(states)}"
        )
    differences = report["differences"]
    profile = report["profile"]
    lines += [
        "",
        f"differing value/UOM slots  {differences['slot_count']}: {differences['slots']}",
        f"value states               {differences['value_states']}",
        f"UOM difference slots       {differences['uom_difference_slots']}",
        "later empty slots          "
        + (
            f"{report['later_empty_slots'][0]}-{report['later_empty_slots'][-1]}"
            if report["later_empty_slots"]
            else "none"
        ),
        "",
        "profile scope",
        f"  authority       {profile['authority']}",
        f"  exact records   {profile['exact_record_keys']}",
        f"  proves          {profile['proves']}",
        f"  does not prove  {profile['does_not_prove']}",
        "",
        "round trip",
    ]
    lines.extend(
        f"  {key}: exact_50_triplets={result['exact_50_triplets']} "
        f"decision={result['mapping_decision']}"
        for key, result in report["round_trips"].items()
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--delivery-format", type=Path, required=True)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = analyze(args.delivery_format)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
