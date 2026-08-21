"""What the provisioning script tells an operator to paste.

The output of this script is copied by hand into the Google Cloud console, so a wrong
string here does not fail a test somewhere else — it silently configures a data store
that matches nothing. The data store's `TargetSite.provided_uri_pattern` is documented as
excluding the http/https protocol, while the query-time `siteSearch` filter is documented
as a full URL. Both appear in this output, and this file pins which is which.

Network-free: the script reads a registry file and prints.
"""

from __future__ import annotations

import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import setup_agent_search  # noqa: E402

REGISTRY = ROOT / "data" / "discovery" / "manufacturer_domains.demo.toml"

CORPUS_PATTERN = "kichler.com/*"
QUERY_PATTERN = "https://kichler.com/*"


@pytest.fixture(scope="module")
def plan() -> str:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = setup_agent_search.main(["--registry", str(REGISTRY)])
    assert code == 0
    return buffer.getvalue()


@pytest.fixture(scope="module")
def plan_json() -> dict:
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        code = setup_agent_search.main(["--registry", str(REGISTRY), "--json"])
    assert code == 0
    return json.loads(buffer.getvalue())


def _sites_to_include(plan: str) -> list[str]:
    """The indented lines under SITES TO INCLUDE, up to the first blank line.

    Read positionally rather than by substring search, because the point of the test is
    *where* a pattern appears: the query form is printed elsewhere in this same output on
    purpose, so `in plan` would prove nothing.
    """
    lines = plan.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("SITES TO INCLUDE"))
    body = lines[start + 1 :]
    while body and not body[0].strip():
        body.pop(0)
    end = next(i for i, line in enumerate(body) if not line.strip())
    return [line.strip() for line in body[:end]]


class TestSitesToInclude:
    def test_the_data_store_pattern_is_scheme_less(self, plan):
        """E."""
        assert _sites_to_include(plan) == [CORPUS_PATTERN]

    def test_the_query_form_is_not_offered_as_the_data_store_value(self, plan):
        """F. It appears in the output, but never under Sites to include."""
        assert QUERY_PATTERN not in _sites_to_include(plan)
        assert not any(site.startswith("http") for site in _sites_to_include(plan))

    def test_the_query_form_is_still_documented_separately(self, plan):
        assert f'siteSearch:"{QUERY_PATTERN}"' in plan

    def test_the_counts_match_the_registry(self, plan):
        assert "reviewed entries    1" in plan
        assert "unreviewed entries  8" in plan
        assert "URL patterns        1 / 50" in plan


class TestJsonPlan:
    def test_included_patterns_are_the_corpus_representation(self, plan_json):
        """E."""
        assert plan_json["included_patterns"] == [CORPUS_PATTERN]

    def test_query_patterns_are_reported_separately(self, plan_json):
        """F."""
        assert plan_json["query_time_site_patterns"] == [QUERY_PATTERN]

    def test_only_kichler_is_reviewed(self, plan_json):
        assert plan_json["reviewed_entries"] == ["kichler-lighting"]
        assert len(plan_json["unreviewed_entries"]) == 8

    def test_advanced_indexing_stays_off(self, plan_json):
        assert plan_json["advanced_website_indexing"] is False
        assert plan_json["generative_features"] is False
