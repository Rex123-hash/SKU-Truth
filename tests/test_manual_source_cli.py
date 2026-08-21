"""Manual source CLI resolves organizer rows and defaults to zero-network dry-run."""

from __future__ import annotations

import csv
import json
import socket
import sys
from pathlib import Path

import pytest
from skutruth.unilog.input import REQUIRED_COLUMNS

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import ingest_manual_source as manual_cli  # noqa: E402

REGISTRY = """
name = "synthetic-manual-cli"
authority = "REVIEWED"

[[manufacturer]]
key = "kichler-lighting"
authority_hints = ["Kichler Lighting"]
domains = ["kichler.com"]

[manufacturer.review]
reviewed_at = "2026-08-21"
reviewed_by = "fixture-reviewer"
basis = "Synthetic test record; no live review was performed."
"""

FIXTURE_URL = "https://www.kichler.com/test-only/manual-source/45297BK-spec.pdf"


@pytest.fixture
def organizer_csv(tmp_path):
    path = tmp_path / "input.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerow(
            dict.fromkeys(REQUIRED_COLUMNS, "")
            | {
                "Mfg_Part_Num": "45297BK",
                "Part_Desc": "synthetic test fixture",
                "Part_Manuf": "Kichler Lighting (KICLI)",
            }
        )
    return path


@pytest.fixture
def registry_file(tmp_path):
    path = tmp_path / "registry.toml"
    path.write_text(REGISTRY, encoding="utf-8")
    return path


def test_default_dry_run_resolves_row_and_makes_no_network_or_store_write(
    tmp_path, organizer_csv, registry_file, monkeypatch, capsys
):
    def no_dns(*_args, **_kwargs):
        raise AssertionError("manual CLI dry-run attempted DNS")

    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    artifacts = tmp_path / "artifacts"
    code = manual_cli.main(
        [
            "--input",
            str(organizer_csv),
            "--mpn",
            " 45297bk ",
            "--url",
            FIXTURE_URL,
            "--note",
            "synthetic test-only",
            "--domain-registry",
            str(registry_file),
            "--artifacts",
            str(artifacts),
            "--json",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert code == 0
    assert report["mode"] == "DRY_RUN"
    assert report["row"] == 1
    assert report["mpn"] == "45297BK"
    assert report["manufacturer"] == "Kichler Lighting"
    assert report["reviewed_domain"] is True
    assert report["authority"] == "APPROVED_MANUFACTURER"
    assert report["mpn_relevance"] == "EXACT"
    assert report["acquisition_would_be_attempted"] is True
    assert report["network_attempted"] is False
    assert report["source_locator_kind"] == "MANUAL"
    assert report["source_locator_provenance"] == "OPERATOR_SUPPLIED"
    assert not artifacts.exists()


def test_missing_mpn_row_fails_before_any_network(
    organizer_csv, registry_file, monkeypatch, capsys
):
    def no_dns(*_args, **_kwargs):
        raise AssertionError("manual CLI attempted DNS")

    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    code = manual_cli.main(
        [
            "--input",
            str(organizer_csv),
            "--mpn",
            "NOT-PRESENT",
            "--url",
            FIXTURE_URL,
            "--domain-registry",
            str(registry_file),
        ]
    )
    assert code == 2
    assert "no organizer row matches" in capsys.readouterr().err
