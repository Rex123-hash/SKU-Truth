"""Plan or acquire one human-supplied official-manufacturer source locator.

The URL is only a locator. This command resolves the real organizer row, uses its own
manufacturer hint, applies the reviewed-domain and exact-MPN policy, and only then may
use the shared safe acquisition path. ``DRY_RUN`` is the default and performs no DNS,
HTTP, search-provider, artifact-store write, or replay-cassette operation.

Usage:

    python scripts/ingest_manual_source.py --input <organizer.csv> \
        --mpn 45297BK --url <operator-supplied-url> --mode DRY_RUN
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from skutruth.contracts import DiscoveryMethod, canonical_mpn  # noqa: E402
from skutruth.discovery import (  # noqa: E402
    DiscoveryError,
    ManualSourceInput,
    ManualSourceMode,
    ManualSourceResult,
    ingest_manual_source,
    load_registry,
    plan_manual_source,
)
from skutruth.discovery.models import DiscoveryRequest  # noqa: E402
from skutruth.ingest.storage import ArtifactStore  # noqa: E402
from skutruth.unilog import RawProductRow, read_unilog_input  # noqa: E402
from skutruth.unilog.errors import UnilogError  # noqa: E402

DEFAULT_REGISTRY = ROOT / "data" / "discovery" / "manufacturer_domains.demo.toml"
DEFAULT_ARTIFACTS = ROOT / "data" / "artifacts" / "runtime"


def find_row(path: Path, mpn: str) -> RawProductRow:
    """Resolve exactly one organizer row by the existing canonical-MPN equality rule."""
    target = canonical_mpn(mpn)
    if not target:
        raise ValueError("--mpn must contain a usable manufacturer part number")
    matches = [
        row
        for row in read_unilog_input(path)
        if canonical_mpn(row.mfg_part_num or "") == target
    ]
    if not matches:
        raise ValueError(f"no organizer row matches MPN {mpn!r}")
    if len(matches) > 1:
        rows = ", ".join(str(row.row_number) for row in matches)
        raise ValueError(
            f"MPN {mpn!r} matches multiple organizer rows ({rows}); choose a unique row"
        )
    return matches[0]


def request_from_row(row: RawProductRow) -> DiscoveryRequest:
    """Use only identity hints already present on the selected organizer row."""
    if not row.mfg_part_num:
        raise ValueError(f"organizer row {row.row_number} has no usable MPN")
    manufacturer = row.manufacturer
    return DiscoveryRequest(
        mpn=row.mfg_part_num,
        raw_mpn=row.raw_value("Mfg_Part_Num"),
        manufacturer_hint=manufacturer.display_name,
        manufacturer_code=manufacturer.supplier_code,
        brand_signals=row.brand_signals,
        description=row.part_desc,
        row_number=row.row_number,
    )


def report_for(result: ManualSourceResult, store: ArtifactStore | None = None) -> dict:
    candidate = result.candidate
    artifact = None
    if result.artifact_sha256 and store is not None:
        stored = store.load(result.artifact_sha256)
        artifact = {
            "sha256": stored.sha256,
            "artifact_id": stored.artifact_id,
            "artifact_kind": stored.artifact_kind.value,
            "media_type": stored.media_type,
            "byte_size": stored.byte_size,
            "page_count": getattr(stored, "page_count", None),
            "text_status": (
                stored.text_status.value if hasattr(stored, "text_status") else None
            ),
            "html_title": (
                stored.content.title if hasattr(stored, "content") else None
            ),
            "html_canonical_url": (
                stored.content.canonical_url if hasattr(stored, "content") else None
            ),
            "html_text_fragments": (
                len(stored.content.text_fragments) if hasattr(stored, "content") else None
            ),
            "html_jsonld_blocks": (
                len(stored.content.jsonld_blocks) if hasattr(stored, "content") else None
            ),
            "discovery_method": stored.source.discovery_method.value,
            "discovery_url": stored.source.discovery_url,
            "final_artifact_url": stored.source.final_artifact_url,
            "identity_scope": (
                stored.source.identity_scope.value if stored.source.identity_scope else None
            ),
            "covers_mpn": stored.source.covers_mpn,
        }
    return {
        "mode": result.mode.value,
        "source_locator_kind": result.locator_kind.value,
        "source_locator_provenance": DiscoveryMethod.OPERATOR_SUPPLIED.value,
        "row": result.source.request.row_number,
        "mpn": result.source.request.mpn,
        "manufacturer": result.source.request.manufacturer_hint,
        "manufacturer_key": result.manufacturer_key,
        "manufacturer_code": result.source.request.manufacturer_code,
        "domain_review": result.domain_review,
        "reviewed_domain": result.reviewed_domain,
        "supplied_url": result.source.url,
        "human_note": result.source.note,
        "input_host": result.input_host,
        "authority": candidate.authority.value,
        "mpn_relevance": candidate.relevance.value,
        "candidate_status": candidate.status.value,
        "rejections": list(candidate.rejections),
        "static_url_valid": result.static_url_valid,
        "dns_check_deferred": result.dns_check_deferred,
        "acquisition_would_be_attempted": result.acquisition_would_be_attempted,
        "network_attempted": result.network_attempted,
        "final_url": candidate.final_url,
        "final_authority": (
            candidate.final_authority.value if candidate.final_authority else None
        ),
        "content_type": candidate.content_type,
        "bytes_downloaded": result.bytes_downloaded,
        "artifact_deduplicated": result.artifact_deduplicated,
        "artifact": artifact,
    }


def render(report: dict) -> str:
    lines = [
        "MANUAL MANUFACTURER SOURCE INTAKE",
        f"mode                    {report['mode']}",
        f"row                     {report['row']}",
        f"MPN                     {report['mpn']}",
        f"manufacturer            {report['manufacturer'] or 'unresolved'}",
        f"manufacturer key        {report['manufacturer_key'] or 'unresolved'}",
        f"reviewed domain         {report['reviewed_domain']}",
        f"input host              {report['input_host'] or 'invalid'}",
        f"authority               {report['authority']}",
        f"MPN relevance           {report['mpn_relevance']}",
        f"candidate status        {report['candidate_status']}",
        f"rejections              {report['rejections'] or 'none'}",
        f"static URL valid        {report['static_url_valid']}",
        f"DNS check deferred      {report['dns_check_deferred']}",
        "acquisition permitted   "
        f"{report['acquisition_would_be_attempted']}",
        f"network attempted       {report['network_attempted']}",
        f"locator provenance      {report['source_locator_provenance']}",
    ]
    if report["final_url"]:
        lines.extend(
            (
                f"final URL               {report['final_url']}",
                f"final authority         {report['final_authority']}",
                f"content type            {report['content_type']}",
            )
        )
    if report["artifact"]:
        artifact = report["artifact"]
        lines.extend(
            (
                f"artifact SHA-256         {artifact['sha256']}",
                f"artifact kind           {artifact['artifact_kind']}",
                f"artifact identity scope {artifact['identity_scope'] or 'unset'}",
            )
        )
        if artifact["artifact_kind"] == "PDF":
            lines.extend(
                (
                    f"artifact pages          {artifact['page_count']}",
                    f"artifact text status    {artifact['text_status']}",
                )
            )
        else:
            lines.extend(
                (
                    f"HTML title              {artifact['html_title'] or 'unset'}",
                    f"HTML text fragments     {artifact['html_text_fragments']}",
                    f"HTML JSON-LD blocks     {artifact['html_jsonld_blocks']}",
                )
            )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--mpn", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--note", default="")
    parser.add_argument(
        "--mode",
        type=str.upper,
        choices=tuple(mode.value for mode in ManualSourceMode),
        default=ManualSourceMode.DRY_RUN.value,
    )
    parser.add_argument("--domain-registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        row = find_row(args.input, args.mpn)
        source = ManualSourceInput(
            request=request_from_row(row),
            url=args.url,
            note=args.note,
        )
        registry = load_registry(args.domain_registry)
        mode = ManualSourceMode(args.mode)
        if mode is ManualSourceMode.DRY_RUN:
            result = plan_manual_source(source, registry=registry)
            store = None
        else:
            store = ArtifactStore(args.artifacts)
            result = ingest_manual_source(source, registry=registry, store=store)
        report = report_for(result, store)
    except (DiscoveryError, OSError, UnilogError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2) if args.json else render(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
