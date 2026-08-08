"""Reproducible ETIM statistics.

Any ETIM count that appears in the README, the pitch, or the demo video must come
from this script. Counts are parsed records with CSV headers excluded, which is the
distinction that produced an off-by-one in an earlier draft (5,641 vs 5,640 classes).

Usage:
    python scripts/etim_stats.py
    python scripts/etim_stats.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from skutruth.etim import archive_sha256, load_etim  # noqa: E402
from skutruth.etim.loader import DEFAULT_ARCHIVE, EXPECTED_ARCHIVE_SHA256  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable output")
    args = parser.parse_args()

    digest = archive_sha256(DEFAULT_ARCHIVE)
    model = load_etim()
    stats = model.stats
    assert stats is not None

    feature_types = Counter(
        f.feature_type.value for cls in model.classes.values() for f in cls.features
    )
    per_class = sorted(len(cls.features) for cls in model.classes.values())
    median = per_class[len(per_class) // 2] if per_class else 0

    payload = {
        "archive": DEFAULT_ARCHIVE.name,
        "sha256": digest,
        "sha256_matches_pin": digest == EXPECTED_ARCHIVE_SHA256,
        "release": model.version_label,
        "parsed_records_excluding_headers": stats.as_dict(),
        "feature_type_distribution": dict(sorted(feature_types.items())),
        "features_per_class": {
            "median": median,
            "mean": round(sum(per_class) / len(per_class), 2) if per_class else 0,
            "max": per_class[-1] if per_class else 0,
        },
        "integrity_issues": len(model.integrity_issues),
        "integrity_issue_kinds": dict(Counter(i.kind for i in model.integrity_issues)),
    }

    if args.json:
        print(json.dumps(payload, indent=2))
        return 0

    print(f"{payload['release']}  ({payload['archive']})")
    print(f"  sha256                {digest}")
    print(f"  matches pinned hash   {payload['sha256_matches_pin']}")
    print("  parsed records (headers excluded):")
    for key, value in payload["parsed_records_excluding_headers"].items():
        print(f"    {key:28s} {value:>8,}")
    print(f"  feature types         {payload['feature_type_distribution']}")
    print(f"  features/class        {payload['features_per_class']}")
    print(
        f"  integrity issues      {payload['integrity_issues']} "
        f"{payload['integrity_issue_kinds']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
