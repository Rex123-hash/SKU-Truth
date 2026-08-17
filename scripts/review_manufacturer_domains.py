"""Prepare manufacturer-domain reviews for a human, and record the ones they confirm.

Domain authority is the gate that decides whether anything discovered can ever be stored
as manufacturer evidence, and the only thing that opens it is a person checking that a
manufacturer publishes from a domain and signing their name to it. This tool does every
part of that job except the signing.

## Two subcommands

    packet    gather what a reviewer needs, decide nothing
    confirm   record a decision the reviewer states on the command line

`packet` is read-only and never touches the registry. `confirm` refuses to run unless the
reviewer's name, the basis, and every domain on the entry are supplied explicitly; it
prints the exact TOML it would add, and only writes when `--write` is passed.

## What this tool will not do

It will not infer a reviewer. Not from `git config`, not from the OS username, not from
the environment. The repository has already had a review attributed to someone who never
performed one, inferred from git authorship; `--reviewed-by` exists so that a name in the
registry means a person typed it.

It will not confirm a domain on the reviewer's behalf, and there is no `--yes-all`, no
heuristic, and no threshold of search results that promotes an entry.

## Usage

    python scripts/review_manufacturer_domains.py packet \\
        --input "data/unilog_source/Unihack_ Sample Dataset - Input.csv"

    python scripts/review_manufacturer_domains.py packet --input <csv> --search --live

    python scripts/review_manufacturer_domains.py confirm \\
        --manufacturer kichler-lighting \\
        --confirm-domain kichler.com \\
        --reviewed-by "Your Name" \\
        --basis "Opened kichler.com and confirmed it is operated by Kichler Lighting." \\
        --consulted-url https://www.kichler.com/ \\
        --write
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from skutruth.contracts import RunMode  # noqa: E402
from skutruth.discovery import (  # noqa: E402
    DiscoveryRequest,
    MalformedRegistryError,
    SearchCall,
    VertexGroundedSearchProvider,
    build_queries,
    execute_search,
    load_registry,
)
from skutruth.discovery.domains import parse_registry  # noqa: E402
from skutruth.discovery.errors import SearchProviderError  # noqa: E402
from skutruth.discovery.models import SearchResult  # noqa: E402
from skutruth.discovery.review import (  # noqa: E402
    HumanDomainReview,
    ReviewCandidate,
    ReviewError,
    ReviewPacket,
    apply_review,
    build_packet,
    render_review_block,
)
from skutruth.replay.store import CassetteStore  # noqa: E402
from skutruth.unilog.errors import UnilogError  # noqa: E402
from skutruth.unilog.input import read_unilog_input  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data" / "discovery" / "manufacturer_domains.demo.toml"
DEFAULT_CASSETTES = ROOT / "data" / "replay" / "runtime"


def _search_for_candidates(
    candidates: tuple[ReviewCandidate, ...],
    *,
    mode: RunMode,
    cassettes: Path,
    max_results: int,
) -> dict[str, tuple[SearchResult, ...]]:
    """Run the deterministic queries for one sample product per candidate.

    Queries come from `build_queries`, the same builder discovery uses. Nothing here
    invents a query, and the results are locator metadata for a human to read — they do
    not feed any decision this tool makes, because it makes none.
    """
    provider = VertexGroundedSearchProvider.from_env()
    store = CassetteStore(cassettes)
    found: dict[str, tuple[SearchResult, ...]] = {}

    for candidate in candidates:
        sample = next(iter(candidate.sample_mpns), None)
        if sample is None:
            continue
        hint = next(
            (s.display_name for s in candidate.spellings if s.display_name),
            None,
        )
        request = DiscoveryRequest(mpn=sample, manufacturer_hint=hint)
        queries = build_queries(request, approved_domains=candidate.domains)
        results: list[SearchResult] = []
        for query in queries:
            try:
                results.extend(
                    execute_search(
                        SearchCall(query=query, max_results=max_results),
                        provider=provider,
                        store=store,
                        mode=mode,
                    )
                )
            except SearchProviderError as exc:
                print(f"  search failed for {candidate.key}: {exc}", file=sys.stderr)
                break
        found[candidate.key] = tuple(results)
    return found


def render_packet(packet: ReviewPacket) -> str:
    """The human-facing packet. Every candidate ends with an unticked decision box."""
    lines = [
        "MANUFACTURER DOMAIN REVIEW PACKET",
        f"  registry        {packet.registry_name} ({packet.registry_authority})",
        f"  organizer rows  {packet.rows_scanned} scanned",
        f"  candidates      {len(packet.candidates)} "
        f"({len(packet.pending)} awaiting a human decision)",
        f"  live search     {'executed' if packet.searched else 'not run'}",
        "",
        "Nothing below is confirmed. This tool does not decide domain ownership; it",
        "gathers what you need in order to decide. A domain licenses evidence only after",
        "you personally check it and record that with the `confirm` subcommand.",
        "",
    ]

    for candidate in packet.candidates:
        lines.append("=" * 78)
        lines.append(f"manufacturer   {candidate.key}")
        lines.append(f"  domains      {', '.join(candidate.domains)}")
        lines.append(f"  organizer    {candidate.row_count} rows")
        if candidate.already_reviewed:
            lines.append(f"  REVIEWED     {candidate.existing_basis}")
        else:
            lines.append("  REVIEWED     no — this entry licenses nothing today")

        lines.append("  spellings observed in the organizer input:")
        for spelling in candidate.spellings:
            grade = "authority hint" if spelling.grants_authority else "LOCATOR ONLY"
            code = f" code={spelling.supplier_code}" if spelling.supplier_code else ""
            lines.append(
                f"    {spelling.raw!r} -> {spelling.display_name!r}{code} "
                f"· {spelling.row_count} rows · {grade}"
            )
            if spelling.sample_mpns:
                lines.append(f"      sample MPNs  {', '.join(spelling.sample_mpns)}")

        if candidate.search_results:
            lines.append("  live search results (locators only — never evidence):")
            for result in candidate.search_results[:10]:
                # The publisher domain leads: for a grounded provider the URL is an
                # opaque redirect, and a page of those tells a reviewer nothing.
                publisher = result.publisher_host or "(no domain reported)"
                lines.append(f"    [{result.rank}] {publisher}")
                if result.title and result.title != result.publisher_host:
                    lines.append(f"        {result.title}")
                lines.append(f"        locator {result.url[:96]}")
            hosts = candidate.observed_hosts
            if hosts:
                lines.append(f"  publisher domains named by search: {', '.join(hosts)}")
                unlisted = [h for h in hosts if h not in candidate.domains]
                if unlisted:
                    lines.append(
                        f"  NOT in the registry — worth a look: {', '.join(unlisted)}"
                    )

        if candidate.needs_review:
            lines += [
                "",
                "  YOUR DECISION — check the manufacturer's own site, then choose one:",
                f"    [ ] CONFIRM  {', '.join(candidate.domains)} "
                f"is/are operated by this manufacturer",
                "    [ ] REJECT   one or more of those domains is not manufacturer-owned",
                "    [ ] UNSURE   leave unreviewed; it stays usable for locating only",
                "",
                "  To record a CONFIRM, run:",
                "    python scripts/review_manufacturer_domains.py confirm \\",
                f"      --manufacturer {candidate.key} \\",
                *[f"      --confirm-domain {d} \\" for d in candidate.domains],
                '      --reviewed-by "<your name>" \\',
                '      --basis "<what you actually checked>" \\',
                "      --consulted-url <url you opened> \\",
                "      --write",
            ]
        lines.append("")

    lines += [
        "=" * 78,
        "REMINDER: confirming manufacturer <-> domain ownership does NOT canonicalise a",
        "manufacturer name. A spelling marked LOCATOR ONLY above stays locator-only after",
        "the review; resolving those needs the manufacturer master, not this tool.",
    ]
    return "\n".join(lines)


def _packet_json(packet: ReviewPacket) -> dict:
    return {
        "version": packet.version,
        "registry": packet.registry_name,
        "registry_authority": packet.registry_authority,
        "rows_scanned": packet.rows_scanned,
        "searched": packet.searched,
        "candidates": [
            {
                "manufacturer": c.key,
                "domains": list(c.domains),
                "authority_hints": list(c.authority_hints),
                "locator_hints": list(c.locator_hints),
                "organizer_rows": c.row_count,
                "already_reviewed": c.already_reviewed,
                "existing_basis": c.existing_basis,
                "needs_review": c.needs_review,
                "spellings": [
                    {
                        "raw": s.raw,
                        "display_name": s.display_name,
                        "supplier_code": s.supplier_code,
                        "rows": s.row_count,
                        "sample_mpns": list(s.sample_mpns),
                        "grants_authority": s.grants_authority,
                    }
                    for s in c.spellings
                ],
                "search_results": [
                    {"rank": r.rank, "url": r.url, "title": r.title, "query": r.query}
                    for r in c.search_results
                ],
                "hosts_named_by_search": list(c.observed_hosts),
                # Deliberately absent: any field a consumer could read as a decision.
                # A packet cannot express confirmation.
            }
            for c in packet.candidates
        ],
    }


def cmd_packet(args: argparse.Namespace) -> int:
    registry = load_registry(args.registry)
    rows = list(read_unilog_input(args.input))

    preliminary = build_packet(
        rows,
        registry,
        only=args.manufacturer or None,
        include_unobserved=args.include_unobserved,
    )

    results: dict[str, tuple[SearchResult, ...]] = {}
    if args.search:
        mode = RunMode.LIVE if args.live else RunMode.REPLAY
        results = _search_for_candidates(
            preliminary.candidates,
            mode=mode,
            cassettes=args.cassettes,
            max_results=args.max_results,
        )

    packet = build_packet(
        rows,
        registry,
        only=args.manufacturer or None,
        include_unobserved=args.include_unobserved,
        search_results=results,
        searched=args.search,
    )

    print(json.dumps(_packet_json(packet), indent=2) if args.json else render_packet(packet))
    return 0


def cmd_confirm(args: argparse.Namespace) -> int:
    """Record a decision the operator stated. Every value below came from a flag."""
    review = HumanDomainReview(
        manufacturer_key=args.manufacturer,
        confirmed_domains=tuple(args.confirm_domain),
        reviewed_by=args.reviewed_by,
        basis=args.basis,
        # The date this confirmation was recorded. Not an identity, and overridable.
        reviewed_at=args.reviewed_at or datetime.now(UTC).date().isoformat(),
        consulted_urls=tuple(args.consulted_url or ()),
        note=args.note or "",
    )

    path = Path(args.registry)
    text = path.read_text(encoding="utf-8")
    registry = parse_registry(tomllib.loads(text), source=path.name)
    updated = apply_review(text, review, registry)

    print(f"review prepared for {review.manufacturer_key}:")
    print()
    print(render_review_block(review))
    print()

    if not args.write:
        print(f"NOT WRITTEN. Re-run with --write to add this to {path}.")
        return 0

    # Verify against the edited text before overwriting: a text insertion that produced
    # valid TOML meaning something else would otherwise look exactly like success.
    verified = parse_registry(tomllib.loads(updated), source=path.name)
    entry = next((e for e in verified.entries if e.key == review.manufacturer_key), None)
    if entry is None or entry.review is None:
        raise ReviewError("the edited registry does not carry the review; nothing was written")
    if entry.review.reviewed_by != review.reviewed_by.strip():
        raise ReviewError("the written reviewer does not match the one supplied; refusing")

    promoted = [e.key for e in verified.licensing_entries]
    path.write_text(updated, encoding="utf-8")
    print(f"written to {path}")
    print(f"  {review.manufacturer_key} now licenses evidence for: {', '.join(entry.domains)}")
    print(f"  entries licensing evidence in this registry: {', '.join(promoted)}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    packet = sub.add_parser("packet", help="gather review material; decides nothing")
    packet.add_argument("--input", type=Path, required=True, help="organizer input CSV")
    packet.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    packet.add_argument(
        "--manufacturer", action="append", help="limit to this registry key (repeatable)"
    )
    packet.add_argument(
        "--include-unobserved",
        action="store_true",
        help="also list registry entries the organizer input never references",
    )
    packet.add_argument("--search", action="store_true", help="include live search results")
    packet.add_argument(
        "--live",
        action="store_true",
        help="with --search, actually call the provider; otherwise replay only",
    )
    packet.add_argument("--cassettes", type=Path, default=DEFAULT_CASSETTES)
    packet.add_argument("--max-results", type=int, default=5)
    packet.add_argument("--json", action="store_true")
    packet.set_defaults(func=cmd_packet)

    confirm = sub.add_parser(
        "confirm",
        help="record a domain review you personally performed",
        description=(
            "Every value is supplied by you. Nothing is defaulted from git config, the "
            "OS username, or the environment."
        ),
    )
    confirm.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    confirm.add_argument("--manufacturer", required=True, help="registry key to confirm")
    confirm.add_argument(
        "--confirm-domain",
        action="append",
        required=True,
        help="a domain you confirmed (repeat for every domain on the entry)",
    )
    confirm.add_argument("--reviewed-by", required=True, help="your name — typed by you")
    confirm.add_argument("--basis", required=True, help="what you actually checked")
    confirm.add_argument(
        "--consulted-url", action="append", help="a URL you opened while reviewing"
    )
    confirm.add_argument("--reviewed-at", help="ISO date; defaults to today (UTC)")
    confirm.add_argument("--note", help="anything else worth recording")
    confirm.add_argument("--write", action="store_true", help="apply to the registry file")
    confirm.set_defaults(func=cmd_confirm)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ReviewError, MalformedRegistryError, UnilogError, SearchProviderError, OSError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
