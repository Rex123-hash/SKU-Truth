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
    """The README with runs of whitespace collapsed.

    Assertions here are about what the document *says*, and the document is hard-wrapped
    at 90 characters. Matching raw text would make these tests fail whenever a sentence
    is rewrapped, which is noise rather than signal.
    """
    return " ".join(README.read_text(encoding="utf-8").split())


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
            "Adjudication and mapping",
            "Evaluation framework",
            "Unilog input/output",
        ],
    )
    def test_implemented_subsystems_are_listed(self, readme, subsystem):
        implemented = readme.split("**Next**")[0]
        assert subsystem in implemented

    def test_compliance_is_not_claimed(self, readme):
        """The attribute path works. That is not the same as conforming to Unilog's rules.

        The mapping rules deciding where a fact goes are hand-written, because the
        official LOV, UOM master, and category rules are not in the supplied pack. The
        README has to keep saying so for as long as that is true.
        """
        assert "cannot yet claim those attributes are Unilog-compliant" in readme
        assert "non-authoritative" in readme

    def test_unilog_is_the_competition_facing_vocabulary(self, readme):
        assert "Unilog-ready" in readme
        assert "AI proposes. SKUTruth verifies." in readme
