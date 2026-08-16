"""Adjudicate a recorded verification run into Unilog attribute slots.

The second half of the offline reproduction path. `verify_extraction_run.py` says which
proposals the manufacturer document actually supports; this says which of those are safe
to commit to a delivery record, where they go, and what is deliberately left out.

    recorded extraction  →  mechanical verification  →  adjudication  →  DeliveryRecord

No provider call, no network, no organizer data required for the default run.

## The mapping is not authoritative

We hold no official Unilog LOV, UOM master, or category attribute rules. The registry
loaded here is hand-written and marked `DEMO`, and the script says so in its output every
time. It proves the mechanism works; it is not evidence that any label, spelling, or unit
below is what Unilog uses.

## Schema

With no `--delivery-format`, a small synthetic schema is generated so the script runs on
a fresh clone. Point `--delivery-format` at the organizer's expected-output CSV to
assemble against the real 252-column contract. That file is third-party material and
stays out of the repository, so the flag is how you supply your own copy.

## Usage

    python scripts/assemble_delivery_record.py --cassette data/replay/runtime/<key>.json
    python scripts/assemble_delivery_record.py --cassette <path> \\
        --delivery-format "data/unilog_source/Unihack_ Expected Output - Delivery Format.csv"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from skutruth.adjudication import (  # noqa: E402
    AdjudicationDecision,
    MalformedMappingError,
    assemble_verified_attributes,
    load_registry,
)
from skutruth.ingest.storage import DEFAULT_RUNTIME_DIR, ArtifactStore  # noqa: E402
from skutruth.unilog.errors import DeliverySchemaError  # noqa: E402
from skutruth.unilog.schema import DeliverySchema  # noqa: E402
from skutruth.verification import claims_from_run, verify_claim  # noqa: E402
from verify_extraction_run import RunnerError, reconstruct_from_cassette  # noqa: E402

DEFAULT_REGISTRY = Path(__file__).resolve().parents[1] / "data" / "mappings" / "lc1d18-demo.toml"

#: Slot depth of the synthetic fallback schema. Matches the organizer sample, so a run
#: without the real file exercises the same capacity arithmetic.
FALLBACK_SLOTS = 50


def fallback_schema(slots: int = FALLBACK_SLOTS) -> DeliverySchema:
    """A minimal stand-in so the script runs without the organizer's file."""
    headers = ["Mfg_Part_Num", "Part_Desc", "MANUFACTURER_PART_NUMBER"]
    for index in range(1, slots + 1):
        headers += [
            f"ATTRIBUTE_LABEL {index}",
            f"ATTRIBUTE_VALUE {index}",
            f"ATTRIBUTE_UOM {index}",
        ]
    return DeliverySchema(headers)


def verified_outcomes(cassette: Path, artifacts: ArtifactStore):
    """Re-derive the recorded run and verify every candidate. Deterministic, offline."""
    run = reconstruct_from_cassette(cassette)
    artifact = artifacts.load(run.target.artifact_sha256, verify_original=True)
    return run, tuple(
        verify_claim(claim, store=artifacts, artifact=artifact)
        for claim in claims_from_run(run)
    )


def render(run, result, schema_label: str) -> str:
    summary = result.summary
    mark = "AUTHORITATIVE" if result.authoritative_mapping else "NON-AUTHORITATIVE (demo)"
    lines = [
        f"{run.target.exact_mpn} · {run.raw.model} · {run.mode.value}",
        f"  mapping    {result.registry_name} — {mark}",
        f"  schema     {schema_label}",
        "",
        f"  {summary.render()}",
        "",
        "  decisions",
    ]
    for fact in result.facts:
        target = f" -> {fact.spec.target_label}" if fact.spec else ""
        lines.append(
            f"    {fact.source_key:<10} {fact.decision.value:<9} {fact.reason.value}{target}"
        )

    lines += ["", "  attribute slots written"]
    for attribute in result.attributes:
        uom = f"  [{attribute.uom_text}]" if attribute.uom_text else ""
        lines.append(
            f"    {attribute.order:>2}  {attribute.label} = {attribute.value_text}{uom}"
        )
        lines.append(
            f"        from {attribute.source_key} · {attribute.artifact_sha256[:12]}… "
            f"p{attribute.page_number} · {attribute.verifier_version}"
        )

    unmapped = result.unmapped
    if unmapped:
        lines += ["", "  verified but no mapping rule (not an error)"]
        lines += [f"    {f.source_key}" for f in unmapped]

    withheld = [f for f in result.facts if f.decision is AdjudicationDecision.WITHHOLD]
    if withheld:
        lines += ["", "  withheld"]
        for fact in withheld:
            failure = fact.outcome.failure.value if fact.outcome.failure else "-"
            lines.append(f"    {fact.source_key:<10} {fact.reason.value} ({failure})")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cassette", type=Path, required=True, help="recorded extraction")
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_RUNTIME_DIR)
    parser.add_argument("--mapping", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument(
        "--delivery-format",
        type=Path,
        default=None,
        help="organizer expected-output CSV; a synthetic schema is used without it",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.mapping)
        if args.delivery_format is not None:
            schema = DeliverySchema.from_csv(args.delivery_format)
            schema_label = (
                f"{args.delivery_format.name} · {schema.field_count} columns · "
                f"{schema.attribute_slot_count} slots · {schema.fingerprint()[:12]}…"
            )
        else:
            schema = fallback_schema()
            schema_label = (
                f"synthetic fallback · {schema.field_count} columns · "
                f"{schema.attribute_slot_count} slots"
            )
        artifacts = ArtifactStore(args.artifacts, writable=False)
        run, outcomes = verified_outcomes(args.cassette, artifacts)
    except (RunnerError, MalformedMappingError, DeliverySchemaError) as exc:
        print(f"cannot assemble: {exc}", file=sys.stderr)
        return 2

    result = assemble_verified_attributes(outcomes, registry, schema)

    if args.json:
        print(
            json.dumps(
                {
                    "exact_mpn": run.target.exact_mpn,
                    "registry": result.registry_name,
                    "authoritative_mapping": result.authoritative_mapping,
                    "schema_fingerprint": schema.fingerprint(),
                    "summary": result.summary.model_dump(),
                    "decisions": [
                        {
                            "source_key": f.source_key,
                            "decision": f.decision.value,
                            "reason": f.reason.value,
                            "target": f.spec.target_label if f.spec else None,
                            "detail": f.detail,
                        }
                        for f in result.facts
                    ],
                    "provenance": list(result.provenance()),
                },
                indent=2,
            )
        )
    else:
        print(render(run, result, schema_label))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
