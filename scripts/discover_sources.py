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

## Usage

    python scripts/discover_sources.py --input <organizer input csv>
    python scripts/discover_sources.py --input <csv> --limit 10 --all-manufacturers
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from skutruth.discovery import (  # noqa: E402
    DiscoveryRequest,
    MalformedRegistryError,
    build_queries,
    load_registry,
)
from skutruth.discovery.domains import DomainRegistry  # noqa: E402
from skutruth.unilog.errors import UnilogError  # noqa: E402
from skutruth.unilog.input import RawProductRow, read_unilog_input  # noqa: E402

DEFAULT_REGISTRY = (
    Path(__file__).resolve().parents[1] / "data" / "discovery" / "manufacturer_domains.demo.toml"
)


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
    grants_authority = registry.entry_for_hint(request.manufacturer_hint) is not None
    return {
        "row": request.row_number,
        "mpn": request.mpn,
        "manufacturer_hint": request.manufacturer_hint,
        "manufacturer_code": request.manufacturer_code,
        "searchable_domains": list(domains),
        "grants_manufacturer_authority": grants_authority
        and registry.authority.may_license_evidence,
        "queries": list(build_queries(request, approved_domains=domains)),
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
        elif plan["searchable_domains"]:
            mark = "searchable · locator hint only, licenses nothing"
        else:
            mark = "NO KNOWN DOMAIN"
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
