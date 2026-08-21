"""Report deterministic internal families and fail-closed delivery classification.

The organizer output file supplies record-scoped examples only.  It is never loaded as a
universal taxonomy LOV, and only exact six-field passthrough matches may populate delivery
classification columns.

Usage:

    python scripts/analyze_classification.py --input <organizer.csv> \
        --delivery-format <expected-output.csv>
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from skutruth.discovery.domains import load_registry  # noqa: E402
from skutruth.unilog import (  # noqa: E402
    ClassificationDecision,
    DeliverySchema,
    DeterministicNormalizer,
    DeterministicProductClassifier,
    InternalProductFamily,
    load_organizer_example_catalog,
    read_unilog_input,
    reviewed_manufacturer_catalog,
    tokenize,
)

DEFAULT_REGISTRY = ROOT / "data" / "discovery" / "manufacturer_domains.demo.toml"


def _decision_counts(values) -> dict[str, int]:
    counts = Counter(value.decision.value for value in values)
    return {decision.value: counts[decision.value] for decision in ClassificationDecision}


def _content_tokens(row) -> tuple[str, ...]:
    description = tokenize(row.part_desc)
    mpn = tokenize(row.mfg_part_num)
    if mpn and description[: len(mpn)] == mpn:
        return description[len(mpn) :]
    return description


def analyze(input_path: Path, delivery_path: Path, registry_path: Path) -> dict:
    rows = list(read_unilog_input(input_path))
    schema = DeliverySchema.from_csv(delivery_path)
    registry = load_registry(registry_path)
    normalizer = DeterministicNormalizer(
        manufacturers=reviewed_manufacturer_catalog(
            registry, source=registry_path.as_posix()
        )
    )
    classifier = DeterministicProductClassifier(
        organizer_examples=load_organizer_example_catalog(delivery_path)
    )
    normalized = [normalizer.normalize(row) for row in rows]
    proposals = [
        classifier.classify(row, normalization=normalization)
        for row, normalization in zip(rows, normalized, strict=True)
    ]

    families = Counter(proposal.internal_family.value for proposal in proposals)
    representatives: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row, proposal in zip(rows, proposals, strict=True):
        if len(representatives[proposal.internal_family.value]) < 3:
            representatives[proposal.internal_family.value].append(
                {"mpn": row.mfg_part_num or "", "description": row.part_desc or ""}
            )

    ambiguous = []
    for row, proposal in zip(rows, proposals, strict=True):
        if proposal.decision is ClassificationDecision.REVIEW:
            ambiguous.append(
                {
                    "row": row.row_number,
                    "mpn": row.mfg_part_num,
                    "description": row.part_desc,
                    "candidate_families": [
                        family.value for family in proposal.candidate_families
                    ],
                    "cues": list(proposal.normalized_cues),
                }
            )

    short = [
        {
            "row": row.row_number,
            "mpn": row.mfg_part_num,
            "description": row.part_desc,
            "content_tokens": len(_content_tokens(row)),
        }
        for row in rows
        if len(_content_tokens(row)) <= 3
    ]

    dishwashers = []
    for row, normalization, proposal in zip(rows, normalized, proposals, strict=True):
        if proposal.internal_family is not InternalProductFamily.DISHWASHER:
            continue
        dishwashers.append(
            {
                "mpn": row.mfg_part_num,
                "description": row.part_desc,
                "manufacturer": normalization.manufacturer.canonical_proposal,
                "family": proposal.internal_family.value,
                "decision": proposal.decision.value,
                "reason": proposal.reason.value,
                "decision_state": (
                    "HIGH_CONFIDENCE" if proposal.is_high_confidence else "NOT_COMMITTED"
                ),
                "delivery_decision": proposal.delivery.decision.value,
                "delivery_authority": proposal.delivery.authority.value,
                "delivery_classpath": proposal.delivery.classpath,
            }
        )

    kichler = [
        proposal
        for row, proposal in zip(rows, proposals, strict=True)
        if row.manufacturer.display_name == "Kichler Lighting"
    ]
    delivery_populated = sum(bool(proposal.delivery.delivery_values) for proposal in proposals)
    delivery_review = sum(
        proposal.delivery.decision is ClassificationDecision.REVIEW
        for proposal in proposals
    )

    return {
        "total_rows": len(rows),
        "rows_with_useful_description": sum(row.part_desc is not None for row in rows),
        "unique_descriptions": len({row.part_desc for row in rows if row.part_desc}),
        "very_short_or_cryptic_rows": len(short),
        "very_short_or_cryptic_examples": short[:15],
        "internal_decisions": _decision_counts(proposals),
        "internal_families": dict(families.most_common()),
        "representative_descriptions": dict(representatives),
        "ambiguity_count": len(ambiguous),
        "ambiguous_rows": ambiguous,
        "delivery_classification": {
            "populated": delivery_populated,
            "review": delivery_review,
            "blank": len(rows) - delivery_populated,
        },
        "delivery_contract": {
            "field_count": schema.field_count,
            "attribute_triplets": schema.attribute_slot_count,
            "classification_fields": [
                field
                for field in ("Dept", "Class", "Fine", "Classpath", "UNSPSC")
                if schema.has_field(field)
            ],
        },
        "dishwasher_slice": {
            "rows": len(dishwashers),
            "family_outcomes": dict(
                Counter(item["decision"] for item in dishwashers)
            ),
            "delivery_outcomes": dict(
                Counter(item["delivery_decision"] for item in dishwashers)
            ),
            "items": dishwashers,
        },
        "kichler_slice": {
            "rows": len(kichler),
            "family_distribution": dict(
                Counter(proposal.internal_family.value for proposal in kichler)
            ),
            "decisions": _decision_counts(kichler),
            "review_or_unknown": sum(
                proposal.decision is not ClassificationDecision.COMMIT
                or proposal.internal_family is InternalProductFamily.UNKNOWN
                for proposal in kichler
            ),
            "delivery_populated": sum(
                bool(proposal.delivery.delivery_values) for proposal in kichler
            ),
        },
    }


def render(report: dict) -> str:
    delivery = report["delivery_classification"]
    contract = report["delivery_contract"]
    lines = [
        "PRODUCT CLASSIFICATION REPORT",
        f"total rows                         {report['total_rows']}",
        f"rows with useful description       {report['rows_with_useful_description']}",
        f"unique descriptions                {report['unique_descriptions']}",
        f"very short/cryptic (<=3 tokens)    {report['very_short_or_cryptic_rows']}",
        f"internal decisions                 {report['internal_decisions']}",
        f"ambiguity count                    {report['ambiguity_count']}",
        "delivery classification             "
        f"populated={delivery['populated']} review={delivery['review']} "
        f"blank={delivery['blank']}",
        "delivery contract                   "
        f"{contract['field_count']} fields / {contract['attribute_triplets']} triplets",
        "",
        "internal families",
    ]
    lines.extend(
        f"  {count:>4}  {family}"
        for family, count in report["internal_families"].items()
    )
    lines += ["", "representative descriptions"]
    for family, examples in report["representative_descriptions"].items():
        lines.append(f"  {family}")
        lines.extend(
            f"    {item['mpn']} | {item['description']}" for item in examples
        )

    lines += ["", "ambiguous rows"]
    if report["ambiguous_rows"]:
        for item in report["ambiguous_rows"]:
            lines.append(
                f"  {item['mpn']} | {item['description']} | "
                f"{','.join(item['candidate_families'])} | {','.join(item['cues'])}"
            )
    else:
        lines.append("  none")

    dish = report["dishwasher_slice"]
    lines += [
        "",
        "dishwasher slice",
        f"  rows              {dish['rows']}",
        f"  family outcomes   {dish['family_outcomes']}",
        f"  delivery outcomes {dish['delivery_outcomes']}",
    ]
    for item in dish["items"]:
        lines.append(
            f"  {item['mpn']} | {item['description']} | {item['manufacturer']} | "
            f"{item['decision']}/{item['reason']} | delivery={item['delivery_decision']} "
            f"({item['delivery_classpath'] or 'blank'})"
        )

    kichler = report["kichler_slice"]
    lines += [
        "",
        "Kichler slice",
        f"  rows                {kichler['rows']}",
        f"  family distribution {kichler['family_distribution']}",
        f"  decisions           {kichler['decisions']}",
        f"  review/unknown      {kichler['review_or_unknown']}",
        f"  delivery populated  {kichler['delivery_populated']}",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--delivery-format", type=Path, required=True)
    parser.add_argument("--domain-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    report = analyze(args.input, args.delivery_format, args.domain_registry)
    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
