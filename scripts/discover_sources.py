"""Manufacturer source discovery over real organizer rows.

Two modes, and the difference between them is the point:

* **plan** (default) — select rows, build the queries discovery *would* run, and report
  which manufacturers have approved domains. Fully deterministic, no network, no provider
  needed. This is what runs when no search provider is configured.
* **live** — additionally execute those queries against a configured provider, apply
  policy, and acquire eligible manufacturer PDFs.

There is no third mode that invents results. If no provider is configured, the script
says so and stops at the plan; it never reports discovery outcomes it did not obtain.

## Sample selection is a rule, not a hand-pick

Rows are chosen by a documented filter — a real part number, a `Part_Manuf` that parses
to a usable name, and a manufacturer the domain registry recognises — then taken in file
order. The rule is applied before any result is seen, so the sample cannot be tuned to
flatter the outcome. `--all-manufacturers` drops the registry condition, which is the
honest way to see how often we have no approved domain at all.

## Phase 1 is search only

`--live` runs the provider and applies policy, and by default acquires nothing. Storing a
document is gated on a reviewed manufacturer domain, and with no reviewed entries there is
nothing to acquire; running the search anyway is what tells us whether the *locating* half
works. `--acquire` opts into the fetch stage for the rows that are genuinely eligible.

## Usage

    python scripts/discover_sources.py --input <organizer input csv>
    python scripts/discover_sources.py --input <csv> --limit 10 --all-manufacturers
    python scripts/discover_sources.py --input <csv> --live --limit 5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from skutruth.contracts import RunMode  # noqa: E402
from skutruth.discovery import (  # noqa: E402
    DiscoveryRequest,
    MalformedRegistryError,
    MissingSearchCredentialsError,
    ProgrammableSearchProvider,
    SearchLimits,
    build_queries,
    discover_sources,
    load_registry,
)
from skutruth.discovery.diagnostics import (  # noqa: E402
    SearchOutcome,
    diagnose,
    outcome_counts,
)
from skutruth.discovery.domains import DomainRegistry  # noqa: E402
from skutruth.discovery.errors import SearchProviderError  # noqa: E402
from skutruth.discovery.models import DiscoveryResult  # noqa: E402
from skutruth.ingest.storage import ArtifactStore  # noqa: E402
from skutruth.replay.store import CassetteStore  # noqa: E402
from skutruth.unilog.errors import UnilogError  # noqa: E402
from skutruth.unilog.input import RawProductRow, read_unilog_input  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data" / "discovery" / "manufacturer_domains.demo.toml"
DEFAULT_CASSETTES = ROOT / "data" / "replay" / "runtime"
DEFAULT_ARTIFACTS = ROOT / "data" / "artifacts" / "runtime"


def request_from_row(row: RawProductRow) -> DiscoveryRequest | None:
    """The adapter from an organizer row to discovery hints.

    Returns `None` when the row carries no usable reference. Nothing is canonicalised:
    the manufacturer hint is exactly what the row said, misspelling included.
    """
    mpn = row.mfg_part_num
    if not mpn:
        return None
    manufacturer = row.manufacturer
    return DiscoveryRequest(
        mpn=mpn,
        raw_mpn=row.raw_value("Mfg_Part_Num"),
        manufacturer_hint=manufacturer.display_name,
        manufacturer_code=manufacturer.supplier_code,
        brand_signals=row.brand_signals,
        description=row.part_desc,
        row_number=row.row_number,
    )


def select_rows(
    path: Path, registry: DomainRegistry, *, limit: int, require_known_manufacturer: bool
) -> list[DiscoveryRequest]:
    """The documented selection rule, applied in file order before any result is seen.

    A row qualifies when it has a real part number and a `Part_Manuf` that parses to a
    usable name. The **first qualifying row for each distinct manufacturer** is taken, in
    file order, until the limit is reached.

    One row per manufacturer rather than the first N rows: the input clusters heavily by
    supplier — six consecutive rows are all one brand — so a straight prefix would report
    one manufacturer's luck as a general result. Nothing here is shuffled, scored, or
    chosen after the fact.
    """
    chosen: list[DiscoveryRequest] = []
    seen: set[str] = set()
    for row in read_unilog_input(path):
        request = request_from_row(row)
        if request is None or not request.manufacturer_hint:
            continue
        key = request.manufacturer_hint.casefold()
        if key in seen:
            continue
        if require_known_manufacturer and not registry.domains_for_hint(request.manufacturer_hint):
            continue
        seen.add(key)
        chosen.append(request)
        if len(chosen) >= limit:
            break
    return chosen


def plan_for(request: DiscoveryRequest, registry: DomainRegistry) -> dict:
    """What discovery would do for one row, and how far its authority would reach.

    Two different questions, reported separately because they have different answers:
    searchable domains come from the broad locator match, while whether anything found
    there could be *stored as that manufacturer's evidence* needs a reviewed authority
    hint. A row can be fully searchable and still license nothing.
    """
    domains = registry.domains_for_hint(request.manufacturer_hint)
    entry = registry.entry_for_hint(request.manufacturer_hint)
    return {
        "row": request.row_number,
        "mpn": request.mpn,
        "manufacturer_hint": request.manufacturer_hint,
        "manufacturer_code": request.manufacturer_code,
        "searchable_domains": list(domains),
        #: Whether the spelling names this manufacturer under a reviewed authority hint.
        "identified_manufacturer": entry is not None,
        # Licensing needs the registry's provenance *and* this binding's audit record.
        "grants_manufacturer_authority": registry.licenses(entry),
        "reviewed_by": entry.review.describe() if entry and entry.review else None,
        "queries": list(build_queries(request, approved_domains=domains)),
    }


def run_live(
    requests: list[DiscoveryRequest],
    *,
    registry: DomainRegistry,
    cassettes: Path,
    artifacts: Path | None,
    max_results: int,
    mode: RunMode,
) -> list[DiscoveryResult]:
    """Execute discovery for each selected row. One provider, so budgets accumulate."""
    provider = ProgrammableSearchProvider.from_env(
        limits=SearchLimits(max_results_per_query=max_results)
    )
    store = CassetteStore(cassettes)
    artifact_store = ArtifactStore(artifacts) if artifacts else None

    results: list[DiscoveryResult] = []
    for request in requests:
        results.append(
            discover_sources(
                request,
                provider=provider,
                registry=registry,
                cassettes=store,
                artifacts=artifact_store,
                mode=mode,
            )
        )
    return results


def live_row(result: DiscoveryResult) -> dict:
    """Everything observed for one row, with each stage reported separately.

    Finding a URL, the host being manufacturer-owned, that binding being reviewed, and a
    document actually being stored are four different achievements. They are reported as
    four different fields so a summary cannot round the first up into the last.
    """
    request = result.request
    return {
        "row": request.row_number,
        "mpn": request.mpn,
        "manufacturer_hint": request.manufacturer_hint,
        "queries_executed": list(result.executed_queries),
        "search_results": result.summary.search_results,
        "outcome": diagnose(result).value,
        "candidates": [
            {
                "rank": c.result.rank,
                "url": c.url,
                "host": c.host,
                "kind": c.kind.value,
                "authority": c.authority.value,
                "relevance": c.relevance.value,
                "status": c.status.value,
                "may_store_as_manufacturer_evidence": c.may_store_as_manufacturer_evidence,
                "rejections": list(c.rejections),
            }
            for c in result.candidates
        ],
        "rejection_counts": result.rejection_counts(),
        "acquired_artifacts": [c.artifact_sha256 for c in result.acquired],
        "summary": result.summary.model_dump(),
    }


def render_live(rows: list[dict], *, registry: DomainRegistry, source: str, mode: str) -> str:
    """The pilot report. Every stage is counted separately and nothing is scored."""
    lines = [
        f"LIVE DISCOVERY PILOT · {source}",
        f"  mode       {mode}",
        f"  registry   {registry.name} — {registry.authority.value}",
        f"  rows       {len(rows)}",
        "",
    ]

    for row in rows:
        lines.append("=" * 78)
        lines.append(
            f"row {row['row']}  {row['mpn']}  ({row['manufacturer_hint']!r})  "
            f"-> {row['outcome']}"
        )
        for query in row["queries_executed"]:
            lines.append(f"    query    {query}")
        lines.append(f"    results  {row['search_results']}")
        for candidate in row["candidates"]:
            evidence = "MAY LICENSE" if candidate["may_store_as_manufacturer_evidence"] else "—"
            lines.append(
                f"    [{candidate['rank']:>2}] {candidate['host']:<28} "
                f"{candidate['authority']:<24} {candidate['relevance']:<12} "
                f"{candidate['kind']:<13} {candidate['status']:<22} {evidence}"
            )
            lines.append(f"         {candidate['url']}")
            if candidate["rejections"]:
                lines.append(f"         rejected: {', '.join(candidate['rejections'])}")
        if row["acquired_artifacts"]:
            for sha in row["acquired_artifacts"]:
                lines.append(f"    ARTIFACT {sha}")
        lines.append("")

    totals = _totals(rows)
    lines += [
        "=" * 78,
        "STAGE COUNTS — each line is a different achievement, not a running total",
        f"  rows attempted                {totals['rows']}",
        f"  queries executed              {totals['queries']}",
        f"  search results returned       {totals['results']}",
        f"  candidates classified         {totals['candidates']}",
        f"  manufacturer-associated hosts {totals['manufacturer_hosts']}",
        f"  exact-MPN candidates          {totals['exact']}",
        f"  candidates that MAY license   {totals['licensing']}",
        f"  PDF fetch attempts            {totals['fetch_attempts']}",
        f"  PDF fetch successes           {totals['fetch_successes']}",
        f"  artifacts ingested            {totals['artifacts']}",
        "",
        "OUTCOMES",
        *(f"  {name:<28} {count}" for name, count in totals["outcomes"].items()),
    ]
    if totals["rejections"]:
        lines += ["", "CANDIDATE REJECTIONS"]
        lines += [f"  {name:<32} {count}" for name, count in totals["rejections"].items()]

    if totals["licensing"] == 0:
        lines += [
            "",
            "SEARCH COMPLETE · DOMAIN REVIEW PENDING · ARTIFACT LICENSING BLOCKED",
            "  No candidate may be stored as manufacturer evidence, because no manufacturer",
            "  entry carries a human DomainReview. Search found what it found; nothing here",
            "  is a claim about a product. Run review_manufacturer_domains.py to prepare a",
            "  packet, and have a person confirm the domains they actually checked.",
        ]
    return "\n".join(lines)


def _totals(rows: list[dict]) -> dict:
    candidates = [c for row in rows for c in row["candidates"]]
    rejections: dict[str, int] = {}
    for row in rows:
        for name, count in row["rejection_counts"].items():
            rejections[name] = rejections.get(name, 0) + count
    return {
        "rows": len(rows),
        "queries": sum(len(r["queries_executed"]) for r in rows),
        "results": sum(r["search_results"] for r in rows),
        "candidates": len(candidates),
        "manufacturer_hosts": sum(
            1
            for c in candidates
            if c["authority"] in {"APPROVED_MANUFACTURER", "UNVERIFIED_MANUFACTURER"}
        ),
        "exact": sum(1 for c in candidates if c["relevance"] == "EXACT"),
        "licensing": sum(1 for c in candidates if c["may_store_as_manufacturer_evidence"]),
        "fetch_attempts": sum(r["summary"]["fetch_attempts"] for r in rows),
        "fetch_successes": sum(r["summary"]["fetch_successes"] for r in rows),
        "artifacts": sum(r["summary"]["artifacts_ingested"] for r in rows),
        "outcomes": outcome_counts(SearchOutcome(r["outcome"]) for r in rows),
        "rejections": dict(sorted(rejections.items())),
    }


def render(plans: list[dict], *, registry: DomainRegistry, source: str) -> str:
    lines = [
        f"discovery plan · {source}",
        f"  registry   {registry.name} — {registry.authority.value} "
        f"({'authoritative' if registry.is_authoritative else 'NOT authoritative'})",
        f"  rows       {len(plans)}",
        "",
    ]
    searchable = sum(1 for p in plans if p["searchable_domains"])
    licensing = sum(1 for p in plans if p["grants_manufacturer_authority"])
    for plan in plans:
        if plan["grants_manufacturer_authority"]:
            mark = "searchable · may license evidence"
        elif not plan["searchable_domains"]:
            mark = "NO KNOWN DOMAIN"
        elif plan["identified_manufacturer"]:
            # The spelling names the manufacturer; the domain binding is unreviewed.
            mark = "searchable · domain not reviewed, licenses nothing"
        else:
            mark = "searchable · locator hint only, licenses nothing"
        lines.append(
            f"  row {plan['row']:>4}  {plan['mpn']:<28} {plan['manufacturer_hint']!r} — {mark}"
        )
        for query in plan["queries"]:
            lines.append(f"        query  {query}")
    lines += [
        "",
        f"  {searchable}/{len(plans)} rows have at least one searchable manufacturer domain",
        f"  {licensing}/{len(plans)} rows could store what they find as manufacturer evidence",
        "",
        "  LIVE PILOT NOT EVALUATED — no search provider is configured.",
        "  Queries above are what discovery would execute; no result is claimed.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="organizer input CSV")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--limit", type=int, default=8, help="rows to select")
    parser.add_argument(
        "--all-manufacturers",
        action="store_true",
        help="drop the known-manufacturer condition, to see how often we have no domain",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--live",
        action="store_true",
        help="execute the queries against the configured search provider",
    )
    parser.add_argument(
        "--replay",
        action="store_true",
        help="with --live, serve from recorded cassettes and make no provider call",
    )
    parser.add_argument(
        "--acquire",
        action="store_true",
        help="with --live, also fetch eligible manufacturer PDFs (needs a reviewed domain)",
    )
    parser.add_argument("--cassettes", type=Path, default=DEFAULT_CASSETTES)
    parser.add_argument("--artifacts", type=Path, default=DEFAULT_ARTIFACTS)
    parser.add_argument("--max-results", type=int, default=10)
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
        requests = select_rows(
            args.input,
            registry,
            limit=args.limit,
            require_known_manufacturer=not args.all_manufacturers,
        )
    except (MalformedRegistryError, UnilogError, OSError) as exc:
        print(f"cannot plan discovery: {exc}", file=sys.stderr)
        return 2

    if args.live:
        mode = RunMode.REPLAY if args.replay else RunMode.LIVE
        try:
            results = run_live(
                requests,
                registry=registry,
                cassettes=args.cassettes,
                artifacts=args.artifacts if args.acquire else None,
                max_results=args.max_results,
                mode=mode,
            )
        except MissingSearchCredentialsError as exc:
            # Never degrade to the plan and call it a live run.
            print(f"LIVE PILOT NOT EXECUTED — {exc}", file=sys.stderr)
            return 3
        except (SearchProviderError, OSError) as exc:
            print(f"live discovery failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2

        rows = [live_row(r) for r in results]
        if args.json:
            print(json.dumps({"mode": mode.value, "rows": rows, "totals": _totals(rows)}, indent=2))
        else:
            print(
                render_live(
                    rows, registry=registry, source=args.input.name, mode=mode.value
                )
            )
        return 0

    plans = [plan_for(r, registry) for r in requests]
    if args.json:
        print(
            json.dumps(
                {
                    "registry": registry.name,
                    "registry_authority": registry.authority.value,
                    "authoritative": registry.is_authoritative,
                    "live_pilot_evaluated": False,
                    "plans": plans,
                },
                indent=2,
            )
        )
    else:
        print(render(plans, registry=registry, source=args.input.name))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
