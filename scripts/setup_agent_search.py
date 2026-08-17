"""What to provision in Agent Search, derived from the reviewed manufacturer domains.

This script **creates nothing**. It reads the domain registry, takes the entries a human
has actually reviewed, and prints the URL patterns and settings the data store needs. A
runtime that provisioned cloud resources on its own would create billable infrastructure
as a side effect of a search, and would make the search corpus depend on whichever run
happened to go first.

## The corpus is downstream of human review, deliberately

Only entries carrying a `DomainReview` appear here. That ordering is the point: Agent
Search cannot be used to establish that a manufacturer owns a domain, because a domain
does not enter the corpus until someone has already established it. With no reviews, this
prints an empty corpus and says so — which is the correct state today.

## Basic website search only

Advanced website indexing requires verifying the domains, which we cannot do for
manufacturers' sites; Google's own guidance is to leave it off when "you don't own the
domains that you specify". Basic search reads Google's existing index instead, and caps
the corpus at 50 included URL patterns — a real limit this script enforces rather than
silently truncating.

## Usage

    python scripts/setup_agent_search.py
    python scripts/setup_agent_search.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from skutruth.discovery import (  # noqa: E402
    AgentSearchConfigError,
    MalformedRegistryError,
    load_registry,
)
from skutruth.discovery.agent_search import (  # noqa: E402
    DEFAULT_LOCATION,
    ENV_ENGINE_ID,
    ENV_LOCATION,
    MAX_INCLUDED_PATTERNS,
    included_patterns_for,
)
from skutruth.extraction.config import ENV_PROJECT  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY = ROOT / "data" / "discovery" / "manufacturer_domains.demo.toml"


def render(registry, patterns: tuple[str, ...]) -> str:
    lines = [
        "AGENT SEARCH PROVISIONING PLAN",
        f"  registry            {registry.name} ({registry.authority.value})",
        f"  reviewed entries    {len(registry.licensing_entries)}",
        f"  unreviewed entries  {len(registry.unreviewed_entries)}",
        f"  URL patterns        {len(patterns)} / {MAX_INCLUDED_PATTERNS}",
        "",
        "This script creates nothing. Provision the resources yourself, then export the",
        "ids below.",
        "",
    ]

    if not patterns:
        lines += [
            "NO REVIEWED DOMAINS — THERE IS NOTHING TO PROVISION YET.",
            "",
            "  A manufacturer domain enters the search corpus only after a person has",
            "  reviewed it. None has been reviewed, so the corpus is empty and searching",
            "  would be pointless rather than merely unproductive.",
            "",
            "  Prepare a review packet first:",
            "    python scripts/review_manufacturer_domains.py packet --input <organizer csv>",
            "",
            "  Then record the domains you personally checked, and re-run this script.",
        ]
        return "\n".join(lines)

    lines += ["SITES TO INCLUDE (paste into the website data store):", ""]
    lines += [f"    {pattern}" for pattern in patterns]
    lines += [
        "",
        "  Each pattern comes from an entry with a signed DomainReview:",
    ]
    for entry in registry.licensing_entries:
        review = entry.review
        lines.append(
            f"    {entry.key:<28} {', '.join(entry.domains)}"
            + (f"  — reviewed by {review.reviewed_by} on {review.reviewed_at}" if review else "")
        )

    lines += [
        "",
        "DATA STORE SETTINGS",
        "  type                        Website content",
        "  Advanced website indexing   OFF  (we do not own these domains and cannot",
        "                                    verify them; basic search needs no claim)",
        "  Generative features         OFF  (no summaries, no answers, no follow-ups)",
        "",
        "SEARCH APP SETTINGS",
        "  edition                     Enterprise (required for website search)",
        "  serving config              default_search",
        "",
        "THEN EXPORT",
        f"  {ENV_PROJECT}=<your gcp project>",
        f"  {ENV_ENGINE_ID}=<the search app id>",
        f"  {ENV_LOCATION}={DEFAULT_LOCATION}    (optional; this is the default)",
        "",
        "  Authentication is Application Default Credentials:",
        "    gcloud auth application-default login",
        "",
        "A domain appearing in another provider's output is NOT a reason to add it here.",
        "Only a human review puts a domain in this list.",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        registry = load_registry(args.registry)
        patterns = included_patterns_for(registry)
    except (MalformedRegistryError, AgentSearchConfigError, OSError) as exc:
        print(f"cannot plan Agent Search setup: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(
            json.dumps(
                {
                    "registry": registry.name,
                    "registry_authority": registry.authority.value,
                    "advanced_website_indexing": False,
                    "generative_features": False,
                    "max_included_patterns": MAX_INCLUDED_PATTERNS,
                    "included_patterns": list(patterns),
                    "reviewed_entries": [e.key for e in registry.licensing_entries],
                    "unreviewed_entries": [e.key for e in registry.unreviewed_entries],
                },
                indent=2,
            )
        )
    else:
        print(render(registry, patterns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
