"""Mechanically verify a recorded extraction, deterministically and offline.

The claim "9 of 14 proposals verified" is worth nothing if the only way to check it is to
take someone's word for it. This script is the versioned procedure that produces such a
number, so the transformation is inspectable and the result is re-derivable by anyone
holding the same local inputs.

    recorded model response  +  ingested artifact
                    ↓
        deterministic re-validation (no model call)
                    ↓
              ProductClaim per candidate
                    ↓
             mechanical verification
                    ↓
            EXACT_SPAN / UNVERIFIED, by reason

**No provider call, ever.** There is no LIVE path here and no credential is read. A
cassette is a recording; re-deriving the run from it is arithmetic, not inference. If a
required local input is missing the script says exactly what is missing and stops, rather
than quietly reaching for the network to fill the gap.

## What is versioned and what is not

The code is committed. The inputs are not, and cannot be: manufacturer datasheets are
third-party copyrighted documents that we may read locally and may not redistribute, and
runtime cassettes have not been reviewed for licensed content. So on a fresh clone this
script runs and reports precisely which artifact hash it needs. That is the honest state
of affairs, and it is still worth far more than a number typed into a document — the
procedure, the thresholds, and the failure vocabulary are all open to inspection.

## Usage

    python scripts/verify_extraction_run.py --cassette data/replay/runtime/<key>.json
    python scripts/verify_extraction_run.py --run local/run.json --json

`--cassette` reconstructs the run from a recorded provider response, rebuilding the
extraction schema from the committed ETIM release and reviewed class configuration. The
rebuilt schema's fingerprint is compared against the one stored in the cassette, so a
reconstruction that does not match the recorded run is reported rather than used.

`--run` takes an already-serialised `ExtractionRun` and skips reconstruction entirely.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from skutruth.contracts import RunMode  # noqa: E402
from skutruth.etim import build_extraction_schema, load_demo_class, load_etim  # noqa: E402
from skutruth.extraction.models import (  # noqa: E402
    ExtractionRun,
    ExtractionTarget,
    RawModelExtraction,
)
from skutruth.extraction.service import validate_raw_extraction  # noqa: E402
from skutruth.ingest.errors import ArtifactStoreError  # noqa: E402
from skutruth.ingest.storage import DEFAULT_RUNTIME_DIR, ArtifactStore  # noqa: E402
from skutruth.replay.errors import ReplayError  # noqa: E402
from skutruth.replay.store import CassetteStore  # noqa: E402
from skutruth.verification import claims_from_run, verify_claim  # noqa: E402


class RunnerError(RuntimeError):
    """A local input is missing or unusable. Always actionable, never silent."""


def load_run_file(path: Path) -> ExtractionRun:
    """Read a serialised `ExtractionRun`."""
    if not path.is_file():
        raise RunnerError(f"no serialised run at {path}")
    try:
        return ExtractionRun.model_validate_json(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise RunnerError(f"{path} is not a valid ExtractionRun: {exc}") from exc


def reconstruct_from_cassette(path: Path, *, demo_config_dir: Path | None = None) -> ExtractionRun:
    """Re-derive an extraction run from a recorded provider response.

    Everything needed is either in the cassette (brand, reference, class, artifact hash,
    page count, prompt version, schema fingerprint) or committed in this repository (the
    ETIM release, the reviewed class configuration). Nothing is guessed: if the schema
    rebuilt from committed data does not fingerprint to what the cassette recorded, the
    reconstruction is refused.
    """
    if not path.is_file():
        raise RunnerError(f"no cassette at {path}")

    store = CassetteStore(path.parent, writable=False)
    try:
        cassette = store.load(path.stem)
    except ReplayError as exc:
        raise RunnerError(f"{path} could not be loaded as a cassette: {exc}") from exc

    request = cassette.request
    payload = request.payload
    missing = [k for k in ("brand", "exact_mpn", "etim_class_id", "page_count") if k not in payload]
    if missing:
        raise RunnerError(
            f"{path} is not an extraction cassette; its request payload lacks "
            f"{', '.join(missing)}"
        )
    if not request.artifact_hashes:
        raise RunnerError(f"{path} records no artifact hash, so no evidence can be checked")
    if not isinstance(cassette.response, dict):
        raise RunnerError(
            f"{path} recorded a {type(cassette.response).__name__} response; an extraction "
            f"response is an object"
        )

    class_id = payload["etim_class_id"]
    etim_class = load_etim().classes.get(class_id)
    if etim_class is None:
        raise RunnerError(f"{class_id} is not in the committed ETIM release")

    try:
        demo_config = load_demo_class(class_id, demo_config_dir)
    except FileNotFoundError:
        demo_config = None

    schema = build_extraction_schema(etim_class, demo_config)
    if schema.fingerprint() != request.schema_version:
        raise RunnerError(
            f"schema reconstruction does not match the recording: the cassette used "
            f"{request.schema_version[:12]}… and this repository builds "
            f"{schema.fingerprint()[:12]}… for {class_id}. The run cannot be re-derived "
            f"under a schema it was not produced with."
        )

    target = ExtractionTarget(
        brand=payload["brand"],
        exact_mpn=payload["exact_mpn"],
        etim_class_id=class_id,
        artifact_sha256=request.artifact_hashes[0],
        page_count=payload["page_count"],
    )
    raw = RawModelExtraction(
        model=cassette.model,
        prompt_version=request.prompt_version,
        schema_fingerprint=schema.fingerprint(),
        payload=cassette.response,
    )
    validated = validate_raw_extraction(
        raw, schema=schema, etim_class=etim_class, demo_config=demo_config, target=target
    )
    return ExtractionRun(
        target=target,
        raw=raw,
        validated=validated,
        mode=RunMode.REPLAY,
        replayed=True,
        cassette_key=cassette.key,
        usage=cassette.usage,
        latency_seconds=cassette.latency_seconds,
    )


def verify_run(run: ExtractionRun, *, artifacts: ArtifactStore) -> dict:
    """Verify every candidate in `run` against its artifact. Pure once inputs are read."""
    sha = run.target.artifact_sha256
    try:
        # Integrity is re-checked once here, not per claim: a 60-page catalogue would
        # otherwise be re-hashed for every candidate.
        artifact = artifacts.load(sha, verify_original=True)
    except ArtifactStoreError as exc:
        raise RunnerError(
            f"artifact {sha} is not available in {artifacts.root}.\n"
            f"  This run was recorded against a manufacturer document that is not "
            f"redistributable and is therefore not committed.\n"
            f"  Ingest your own local copy so it stores under this exact hash, then "
            f"re-run.\n"
            f"  Underlying error: {exc}"
        ) from exc

    outcomes = [
        verify_claim(claim, store=artifacts, artifact=artifact)
        for claim in claims_from_run(run)
    ]
    verified = [o for o in outcomes if o.verified]
    unverified = [o for o in outcomes if not o.verified]

    return {
        "exact_mpn": run.target.exact_mpn,
        "model": run.raw.model,
        "mode": run.mode.value,
        "replayed": run.replayed,
        "cassette_key": run.cassette_key,
        "artifact_sha256": sha,
        "page_count": artifact.page_count,
        "requested": len(run.validated.requested_feature_ids),
        "proposed_non_null": run.raw.non_null_count,
        "candidates": run.validated.candidate_count,
        "rejected": len(run.validated.rejected),
        "abstained": len(run.validated.abstained_feature_ids),
        "verified": len(verified),
        "unverified": len(unverified),
        "failure_counts": dict(
            sorted(Counter(o.failure.value for o in unverified if o.failure).items())
        ),
        "outcomes": [
            {
                "key": o.key,
                "status": o.status.value,
                "failure": o.failure.value if o.failure else None,
                "evidence_mode": o.evidence_mode.value,
                "page": o.page_number,
                "detail": o.failure_detail,
            }
            for o in outcomes
        ],
        "verifier_version": outcomes[0].verifier_version if outcomes else None,
    }


def render(report: dict) -> str:
    lines = [
        f"{report['exact_mpn']} · {report['model']} · {report['mode']}"
        f"{' (replayed)' if report['replayed'] else ''}",
        f"  artifact   {report['artifact_sha256'][:12]}… · {report['page_count']} pages",
        f"  verifier   {report['verifier_version']}",
        "",
        f"  {report['requested']} requested · {report['proposed_non_null']} proposed · "
        f"{report['candidates']} candidates · {report['rejected']} rejected · "
        f"{report['abstained']} abstained",
        "",
        f"  {report['candidates']} claims verified mechanically",
        f"    {report['verified']:>3} EXACT_SPAN",
        f"    {report['unverified']:>3} UNVERIFIED",
    ]
    if report["failure_counts"]:
        lines.append("")
        lines.append("  unverified by reason")
        width = max(len(k) for k in report["failure_counts"])
        for reason, count in report["failure_counts"].items():
            lines.append(f"    {reason:<{width}}  {count}")
    lines.append("")
    lines.append("  per claim")
    for row in report["outcomes"]:
        label = row["failure"] or row["status"]
        lines.append(f"    {row['key']:<10} p{row['page']:<3} {label}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--cassette", type=Path, help="recorded provider response to re-derive")
    source.add_argument("--run", type=Path, help="already-serialised ExtractionRun")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=DEFAULT_RUNTIME_DIR,
        help="artifact store root (default: data/artifacts/runtime)",
    )
    parser.add_argument(
        "--demo-classes", type=Path, default=None, help="reviewed class configuration directory"
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args(argv)

    try:
        run = (
            load_run_file(args.run)
            if args.run is not None
            else reconstruct_from_cassette(args.cassette, demo_config_dir=args.demo_classes)
        )
        report = verify_run(run, artifacts=ArtifactStore(args.artifacts, writable=False))
    except RunnerError as exc:
        print(f"cannot verify: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
