"""The root README is the first thing a reader sees, so it has to be true.

It drifted once already: it went on describing ingestion, span verification, the identity
resolver, model-backed extraction, and the evaluation harness as unbuilt for five
milestones after they were built and tested. Understating the work is not a safe error —
it is just as wrong as overstating it, and it is the kind of wrong that only a test
catches, because nobody re-reads a file they wrote first.
"""

from __future__ import annotations

from pathlib import Path

import pytest

README = Path(__file__).resolve().parents[1] / "README.md"


@pytest.fixture(scope="module")
def readme() -> str:
    return README.read_text(encoding="utf-8")


class TestStatusIsCurrent:
    @pytest.mark.parametrize(
        "stale_claim",
        [
            "Not yet implemented: document ingestion",
            "the identity resolver",
            "model-backed extraction",
            "the evaluation harness",
            "span verification, the identity resolver",
        ],
    )
    def test_built_subsystems_are_not_described_as_missing(self, readme, stale_claim):
        """S. Each of these named a shipped subsystem as unbuilt."""
        assert stale_claim not in readme

    @pytest.mark.parametrize(
        "subsystem",
        [
            "Identity resolution",
            "Artifact ingestion",
            "Table extraction",
            "Gemini structured extraction",
            "Record and replay",
            "Mechanical verification",
            "Evaluation framework",
            "Unilog input/output",
        ],
    )
    def test_implemented_subsystems_are_listed(self, readme, subsystem):
        implemented = readme.split("**Next**")[0]
        assert subsystem in implemented

    def test_the_two_halves_are_not_claimed_to_be_wired(self, readme):
        """The pipeline diagram would otherwise read as a working end-to-end product."""
        assert "not yet wired to each other" in readme

    def test_unilog_is_the_competition_facing_vocabulary(self, readme):
        assert "Unilog-ready" in readme
        assert "AI proposes. SKUTruth verifies." in readme
