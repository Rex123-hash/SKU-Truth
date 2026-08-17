"""The discovery CLI's exit codes.

A caller that asked for a live run and did not get one must not see success. These are
the cases where the script prints "LIVE PILOT NOT EXECUTED", and automation has nothing
but the status code to go on — a zero there would make an unrun pilot indistinguishable
from a pilot that ran and found nothing.

Offline, and network-free: every case here fails before any provider is constructed.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import discover_sources  # noqa: E402

REVIEWED_TOML = """
name = "cli-registry"
authority = "REVIEWED"

[[manufacturer]]
key = "kichler-lighting"
authority_hints = ["Kichler Lighting"]
domains = ["kichler.com"]

[manufacturer.review]
reviewed_at = "2026-08-17"
reviewed_by = "A Real Person"
basis = "Confirmed kichler.com is operated by Kichler Lighting."
"""

UNREVIEWED_TOML = """
name = "cli-registry"
authority = "REVIEWED"

[[manufacturer]]
key = "kichler-lighting"
authority_hints = ["Kichler Lighting"]
domains = ["kichler.com"]
"""


@pytest.fixture
def organizer_csv(tmp_path):
    path = tmp_path / "input.csv"
    from skutruth.unilog.input import REQUIRED_COLUMNS

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(REQUIRED_COLUMNS))
        writer.writeheader()
        writer.writerow(
            dict.fromkeys(REQUIRED_COLUMNS, "")
            | {"Mfg_Part_Num": "45297BK", "Part_Manuf": "Kichler Lighting (KICLI)"}
        )
    return path


def registry_file(tmp_path, text):
    path = tmp_path / "registry.toml"
    path.write_text(text, encoding="utf-8")
    return path


def run(argv):
    return discover_sources.main(argv)


class TestLiveNotExecutedIsNotSuccess:
    def test_an_empty_reviewed_corpus_exits_nonzero(self, tmp_path, organizer_csv, capsys):
        """N. Nothing is reviewed, so there is no corpus and no live run."""
        code = run(
            [
                "--input",
                str(organizer_csv),
                "--registry",
                str(registry_file(tmp_path, UNREVIEWED_TOML)),
                "--live",
            ]
        )
        assert code == 2
        assert "LIVE PILOT NOT EXECUTED" in capsys.readouterr().err

    def test_missing_agent_search_config_exits_nonzero(
        self, tmp_path, organizer_csv, capsys, monkeypatch
    ):
        """M. A reviewed corpus exists, but the app is not configured."""
        monkeypatch.delenv("SKUTRUTH_AGENT_SEARCH_ENGINE_ID", raising=False)
        monkeypatch.setenv("SKUTRUTH_GCP_PROJECT", "some-project")
        code = run(
            [
                "--input",
                str(organizer_csv),
                "--registry",
                str(registry_file(tmp_path, REVIEWED_TOML)),
                "--live",
            ]
        )
        assert code == 2
        assert "LIVE PILOT NOT EXECUTED" in capsys.readouterr().err

    def test_missing_project_exits_nonzero(
        self, tmp_path, organizer_csv, capsys, monkeypatch
    ):
        monkeypatch.delenv("SKUTRUTH_GCP_PROJECT", raising=False)
        monkeypatch.setenv("SKUTRUTH_AGENT_SEARCH_ENGINE_ID", "engine")
        assert (
            run(
                [
                    "--input",
                    str(organizer_csv),
                    "--registry",
                    str(registry_file(tmp_path, REVIEWED_TOML)),
                    "--live",
                ]
            )
            == 2
        )
        assert "LIVE PILOT NOT EXECUTED" in capsys.readouterr().err

    def test_no_provider_is_constructed_when_the_corpus_is_empty(
        self, tmp_path, organizer_csv, monkeypatch
    ):
        """The refusal happens before any client exists, so nothing can reach a network."""
        called: list[int] = []
        monkeypatch.setattr(
            discover_sources.AgentSearchProvider,
            "from_env",
            classmethod(lambda cls, **kw: called.append(1)),
        )
        run(
            [
                "--input",
                str(organizer_csv),
                "--registry",
                str(registry_file(tmp_path, UNREVIEWED_TOML)),
                "--live",
            ]
        )
        assert called == []


class TestOfflinePlanningStillSucceeds:
    def test_plan_mode_exits_zero(self, tmp_path, organizer_csv):
        """A planning run is a real answer, and says so with a zero status."""
        assert (
            run(
                [
                    "--input",
                    str(organizer_csv),
                    "--registry",
                    str(registry_file(tmp_path, UNREVIEWED_TOML)),
                ]
            )
            == 0
        )

    def test_plan_mode_json_exits_zero(self, tmp_path, organizer_csv):
        assert (
            run(
                [
                    "--input",
                    str(organizer_csv),
                    "--registry",
                    str(registry_file(tmp_path, REVIEWED_TOML)),
                    "--json",
                ]
            )
            == 0
        )

    def test_a_missing_input_file_exits_nonzero(self, tmp_path):
        assert (
            run(
                [
                    "--input",
                    str(tmp_path / "absent.csv"),
                    "--registry",
                    str(registry_file(tmp_path, REVIEWED_TOML)),
                ]
            )
            == 2
        )
