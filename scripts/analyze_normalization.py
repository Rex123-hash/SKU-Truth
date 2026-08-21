"""Deterministically analyze and normalize an organizer manufacturer/brand dataset.

No network, model, fuzzy match, or built-in manufacturer list is used.  Human-approved
manufacturer rules are derived only from reviewed entries in the supplied domain
registry; all other names remain review candidates.

Usage:

    python scripts/analyze_normalization.py --input <organizer.csv> \
        --slice-manufacturer "Kichler Lighting"
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from skutruth.discovery.domains import load_registry, normalize_manufacturer  # noqa: E402
from skutruth.unilog import (  # noqa: E402
    DeterministicNormalizer,
    NormalizationDecision,
    read_unilog_input,
    reviewed_manufacturer_catalog,
)

DEFAULT_REGISTRY = ROOT / "data" / "discovery" / "manufacturer_domains.demo.toml"


def _decision_counts(values) -> dict[str, int]:
    counts = Counter(value.decision.value for value in values)
    return {decision.value: counts[decision.value] for decision in NormalizationDecision}


def analyze(input_path: Path, registry_path: Path, *, slice_name: str | None) -> dict:
    rows = list(read_unilog_input(input_path))
    registry = load_registry(registry_path)
    manufacturer_catalog = reviewed_manufacturer_catalog(
        registry, source=registry_path.as_posix()
    )
    normalizer = DeterministicNormalizer(manufacturers=manufacturer_catalog)
    normalized = [normalizer.normalize(row) for row in rows]

    raw_manufacturers = Counter(row.raw_value("Part_Manuf") for row in rows)
    names = Counter(
        row.manufacturer.display_name
        for row in rows
        if row.manufacturer.display_name is not None
    )
    codes = Counter(
        row.manufacturer.supplier_code
        for row in rows
        if row.manufacturer.supplier_code is not None
    )
    name_codes: dict[str, Counter[str]] = defaultdict(Counter)
    code_names: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        parsed = row.manufacturer
        if parsed.display_name and parsed.supplier_code:
            name_codes[parsed.display_name][parsed.supplier_code] += 1
            code_names[parsed.supplier_code][parsed.display_name] += 1

    brand_values: dict[str, Counter[str]] = {}
    for field in ("E1_Brand", "Unilog_Brand", "DIB_Brand"):
        brand_values[field] = Counter(
            value for row in rows if (value := row.cleaned(field)) is not None
        )

    manufacturer_decisions = _decision_counts(
        item.manufacturer for item in normalized
    )
    brand_decisions = _decision_counts(item.brand for item in normalized)
    manufacturer_reasons = Counter(item.manufacturer.reason.value for item in normalized)
    brand_reasons = Counter(item.brand.reason.value for item in normalized)

    canonical_proposals = Counter(
        item.manufacturer.canonical_proposal
        for item in normalized
        if item.manufacturer.canonical_proposal is not None
    )
    committed_manufacturers = Counter(
        item.manufacturer.delivery_value
        for item in normalized
        if item.manufacturer.delivery_value is not None
    )

    candidate_groups: dict[str, Counter[str]] = defaultdict(Counter)
    for name, count in names.items():
        candidate_groups[normalize_manufacturer(name)][name] += count

    brand_source_patterns = Counter()
    manufacturer_brand_pairs = Counter()
    for row in rows:
        present = tuple(
            field
            for field in ("E1_Brand", "Unilog_Brand", "DIB_Brand")
            if row.cleaned(field) is not None
        )
        brand_source_patterns["+".join(present) if present else "NONE"] += 1
        for field in present:
            manufacturer_brand_pairs[
                (
                    row.manufacturer.display_name or "<UNRESOLVED>",
                    field,
                    row.cleaned(field),
                )
            ] += 1

    slice_report = None
    if slice_name:
        slice_key = normalize_manufacturer(slice_name)
        selected = [
            item
            for row, item in zip(rows, normalized, strict=True)
            if row.manufacturer.display_name
            and normalize_manufacturer(row.manufacturer.display_name) == slice_key
        ]
        slice_report = {
            "name": slice_name,
            "rows": len(selected),
            "manufacturer_decisions": _decision_counts(
                item.manufacturer for item in selected
            ),
            "manufacturer_reasons": dict(
                Counter(item.manufacturer.reason.value for item in selected)
            ),
            "brand_decisions": _decision_counts(item.brand for item in selected),
            "brand_reasons": dict(Counter(item.brand.reason.value for item in selected)),
        }

    return {
        "total_rows": len(rows),
        "manufacturer_parse_status": dict(
            Counter(row.manufacturer.status.value for row in rows)
        ),
        "manufacturer_decisions": manufacturer_decisions,
        "manufacturer_reasons": dict(manufacturer_reasons),
        "brand_decisions": brand_decisions,
        "brand_reasons": dict(brand_reasons),
        "unique_raw_manufacturers": len(raw_manufacturers),
        "unique_parsed_manufacturer_names": len(names),
        "unique_supplier_codes": len(codes),
        "unique_canonical_proposals": len(canonical_proposals),
        "unique_committed_canonical_manufacturers": len(committed_manufacturers),
        "top_canonical_manufacturer_proposals": canonical_proposals.most_common(15),
        "committed_canonical_manufacturers": committed_manufacturers.most_common(),
        "raw_manufacturer_variants": raw_manufacturers.most_common(),
        "name_to_multiple_codes": {
            name: dict(values) for name, values in name_codes.items() if len(values) > 1
        },
        "code_to_multiple_names": {
            code: dict(values) for code, values in code_names.items() if len(values) > 1
        },
        "brand_values": {
            field: {"rows": sum(values.values()), "values": values.most_common()}
            for field, values in brand_values.items()
        },
        "brand_source_patterns": dict(brand_source_patterns),
        "manufacturer_brand_pairs": [
            {
                "manufacturer": manufacturer,
                "field": field,
                "brand": brand,
                "rows": count,
            }
            for (manufacturer, field, brand), count in manufacturer_brand_pairs.most_common()
        ],
        "exact_duplicate_manufacturer_strings": [
            [value, count]
            for value, count in raw_manufacturers.most_common()
            if count > 1
        ],
        "candidate_canonical_groups": [
            {"key": key, "variants": values.most_common(), "rows": sum(values.values())}
            for key, values in sorted(candidate_groups.items())
        ],
        "slice": slice_report,
    }


def render(report: dict) -> str:
    lines = [
        "MANUFACTURER + BRAND NORMALIZATION REPORT",
        f"total rows                         {report['total_rows']}",
        f"manufacturer parses                {report['manufacturer_parse_status']}",
        f"manufacturer decisions             {report['manufacturer_decisions']}",
        f"brand decisions                    {report['brand_decisions']}",
        f"unique raw manufacturers           {report['unique_raw_manufacturers']}",
        f"unique parsed manufacturer names   {report['unique_parsed_manufacturer_names']}",
        f"unique supplier codes              {report['unique_supplier_codes']}",
        f"unique canonical proposals         {report['unique_canonical_proposals']}",
        "unique committed manufacturers   "
        f"{report['unique_committed_canonical_manufacturers']}",
        "",
        "top canonical manufacturer proposals",
    ]
    lines.extend(
        f"  {count:>4}  {name}"
        for name, count in report["top_canonical_manufacturer_proposals"]
    )
    lines += ["", "real brand values"]
    for field, summary in report["brand_values"].items():
        lines.append(
            f"  {field:<13} {summary['rows']:>4} rows / "
            f"{len(summary['values'])} values"
        )
    lines.append(f"  source patterns {report['brand_source_patterns']}")

    lines += ["", "manufacturer name/code conflicts"]
    lines.append(f"  one name -> multiple codes {report['name_to_multiple_codes'] or 'none'}")
    lines.append(f"  one code -> multiple names {report['code_to_multiple_names'] or 'none'}")

    if report["slice"]:
        selected = report["slice"]
        lines += [
            "",
            f"slice: {selected['name']}",
            f"  rows                   {selected['rows']}",
            f"  manufacturer decisions {selected['manufacturer_decisions']}",
            f"  manufacturer reasons   {selected['manufacturer_reasons']}",
            f"  brand decisions        {selected['brand_decisions']}",
            f"  brand reasons          {selected['brand_reasons']}",
        ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--domain-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--slice-manufacturer")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = analyze(
        args.input,
        args.domain_registry,
        slice_name=args.slice_manufacturer,
    )
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
