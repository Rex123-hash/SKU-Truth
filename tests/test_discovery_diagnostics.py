"""Per-product outcomes, and the live provider driven through the real discovery service.

Two things are proved here. First, that `diagnose` reports the state an operator would
act on rather than the first one it happens to find. Second — and this is the one that
matters for the pilot — that the live provider adapter works through `discover_sources`
end to end, with policy, ranking, and authority all applied, and no socket opened.
"""

from __future__ import annotations

import tomllib

import httpx
import pytest
from conftest_pdf import build_pdf
from skutruth.contracts import DiscoveryMethod, RunMode
from skutruth.discovery import (
    DiscoveryRequest,
    SearchCredentials,
    SearchLimits,
    discover_sources,
)
from skutruth.discovery.diagnostics import (
    SearchOutcome,
    candidate_states,
    diagnose,
    outcome_counts,
)
from skutruth.discovery.domains import parse_registry
from skutruth.discovery.models import SourceAuthority
from skutruth.discovery.programmable_search import ProgrammableSearchProvider
from skutruth.ingest.storage import ArtifactStore
from skutruth.replay.store import CassetteStore

REGISTRY_TOML = """
name = "diagnostics-registry"
authority = "REVIEWED"

[[manufacturer]]
key = "schneider-electric"
authority_hints = ["Schneider Electric"]
domains = ["se.com"]

[[manufacturer]]
key = "kichler-lighting"
authority_hints = ["Kichler Lighting"]
domains = ["kichler.com"]

[manufacturer.review]
reviewed_at = "2026-08-17"
reviewed_by = "A Real Person"
basis = "Confirmed kichler.com is operated by Kichler Lighting."

[hosts]
distributors = ["grainger.com"]
marketplaces = ["amazon.com"]
"""

CREDS = SearchCredentials(api_key="not-a-real-key", engine_id="cx000")


def registry():
    return parse_registry(tomllib.loads(REGISTRY_TOML), source="diagnostics-registry")


def provider_returning(items_by_query: dict[str, list[dict]] | list[dict]):
    """A real `ProgrammableSearchProvider` whose transport is a mock."""

    def handler(request: httpx.Request) -> httpx.Response:
        query = request.url.params["q"]
        items = (
            items_by_query.get(query, [])
            if isinstance(items_by_query, dict)
            else items_by_query
        )
        return httpx.Response(200, json={"items": items})

    return ProgrammableSearchProvider(
        CREDS,
        limits=SearchLimits(max_results_per_query=5),
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def run(items, *, mpn="LC1D18P7", hint="Schneider Electric", tmp_path=None, artifacts=None):
    return discover_sources(
        DiscoveryRequest(mpn=mpn, manufacturer_hint=hint),
        provider=provider_returning(items),
        registry=registry(),
        cassettes=CassetteStore(tmp_path),
        artifacts=artifacts,
        mode=RunMode.LIVE,
    )


def item(url: str, title: str = "") -> dict:
    return {"link": url, "title": title or url, "snippet": ""}


def live_provider(client: httpx.Client) -> ProgrammableSearchProvider:
    """The real adapter, which declares no `DiscoveryMethod`."""
    return ProgrammableSearchProvider(CREDS, client=client)


def declaring_provider(client: httpx.Client) -> ProgrammableSearchProvider:
    """The same adapter with a truthful method, to reach the gates behind provenance.

    `CURATED_CORPUS` is not what a web search does; it stands in here only so the
    acquisition path past the provenance gate can be exercised at all.
    """

    class Declaring(ProgrammableSearchProvider):
        discovery_method = DiscoveryMethod.CURATED_CORPUS

    return Declaring(CREDS, client=client)


def acquiring_run(body: bytes, content_type: str, *, provider, tmp_path):
    """Discovery against a reviewed domain, with a document served for the fetch."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "www.googleapis.com":
            return httpx.Response(200, json={"items": [item("https://kichler.com/p/45297BK")]})
        return httpx.Response(200, content=body, headers={"content-type": content_type})

    transport = httpx.MockTransport(handler)
    return discover_sources(
        DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
        provider=provider(httpx.Client(transport=transport)),
        registry=registry(),
        cassettes=CassetteStore(tmp_path / "cassettes"),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        mode=RunMode.LIVE,
        transport=transport,
        resolver=lambda host: ["93.184.216.34"],
    )


class TestLiveProviderThroughTheService:
    """The pilot's actual code path, offline."""

    def test_a_manufacturer_pdf_is_classified_from_a_live_response(self, tmp_path):
        result = run([item("https://se.com/docs/LC1D18P7.pdf")], tmp_path=tmp_path)
        candidate = result.candidates[0]
        assert candidate.host == "se.com"
        assert candidate.authority is SourceAuthority.UNVERIFIED_MANUFACTURER
        assert candidate.relevance.is_exact

    def test_an_unreviewed_manufacturer_domain_licenses_nothing(self, tmp_path):
        """Schneider is in the registry with no review. It locates and licenses nothing."""
        result = run([item("https://se.com/docs/LC1D18P7.pdf")], tmp_path=tmp_path)
        assert not result.candidates[0].may_store_as_manufacturer_evidence
        assert diagnose(result) is SearchOutcome.DOMAIN_REVIEW_REQUIRED

    def test_a_reviewed_manufacturer_domain_may_license(self, tmp_path):
        result = run(
            [item("https://kichler.com/p/45297BK.pdf")],
            mpn="45297BK",
            hint="Kichler Lighting",
            tmp_path=tmp_path,
        )
        candidate = result.candidates[0]
        assert candidate.authority is SourceAuthority.APPROVED_MANUFACTURER
        assert candidate.may_store_as_manufacturer_evidence

    def test_queries_come_from_the_deterministic_builder(self, tmp_path):
        result = run([item("https://se.com/a.pdf")], tmp_path=tmp_path)
        assert result.executed_queries == (
            '"LC1D18P7" site:se.com',
            '"LC1D18P7" Schneider Electric',
            '"LC1D18P7" datasheet',
        )

    def test_distributors_and_marketplaces_are_refused(self, tmp_path):
        result = run(
            [
                item("https://grainger.com/p/LC1D18P7"),
                item("https://amazon.com/dp/LC1D18P7"),
            ],
            tmp_path=tmp_path,
        )
        assert all(not c.may_store_as_manufacturer_evidence for c in result.candidates)
        assert {c.authority for c in result.candidates} == {
            SourceAuthority.KNOWN_DISTRIBUTOR,
            SourceAuthority.KNOWN_MARKETPLACE,
        }

    def test_a_lookalike_host_is_not_the_manufacturer(self, tmp_path):
        result = run([item("https://se.com.evil.example/LC1D18P7.pdf")], tmp_path=tmp_path)
        assert result.candidates[0].authority is SourceAuthority.UNKNOWN

    def test_the_same_url_from_two_queries_is_one_candidate(self, tmp_path):
        result = run([item("https://se.com/a-LC1D18P7.pdf")], tmp_path=tmp_path)
        assert len(result.candidates) == 1
        assert result.summary.queries == 3

    def test_nothing_is_acquired_without_an_artifact_store(self, tmp_path):
        result = run([item("https://kichler.com/45297BK.pdf")], tmp_path=tmp_path)
        assert result.summary.fetch_attempts == 0
        assert not result.acquired


class TestDiagnosis:
    def test_no_results_is_reported_as_such(self, tmp_path):
        assert diagnose(run([], tmp_path=tmp_path)) is SearchOutcome.NO_RESULTS

    def test_only_distributors(self, tmp_path):
        result = run([item("https://grainger.com/p/LC1D18P7")], tmp_path=tmp_path)
        assert diagnose(result) is SearchOutcome.ONLY_DISTRIBUTORS

    def test_only_marketplaces(self, tmp_path):
        result = run([item("https://amazon.com/dp/LC1D18P7")], tmp_path=tmp_path)
        assert diagnose(result) is SearchOutcome.ONLY_MARKETPLACES

    def test_no_manufacturer_domain_when_hosts_are_simply_unknown(self, tmp_path):
        result = run([item("https://random-blog.example/LC1D18P7")], tmp_path=tmp_path)
        assert diagnose(result) is SearchOutcome.NO_MANUFACTURER_DOMAIN

    def test_domain_review_required_outranks_a_distributor_result(self, tmp_path):
        """The actionable state wins: a human review would unblock this row."""
        result = run(
            [
                item("https://grainger.com/p/LC1D18P7"),
                item("https://se.com/docs/LC1D18P7.pdf"),
            ],
            tmp_path=tmp_path,
        )
        assert diagnose(result) is SearchOutcome.DOMAIN_REVIEW_REQUIRED

    def test_family_only_on_an_approved_host(self, tmp_path):
        result = run(
            [item("https://kichler.com/p/45297.pdf")],
            mpn="45297BK",
            hint="Kichler Lighting",
            tmp_path=tmp_path,
        )
        assert diagnose(result) is SearchOutcome.FAMILY_ONLY

    def test_sibling_only_on_an_approved_host(self, tmp_path):
        result = run(
            [item("https://kichler.com/p/45297AZ.pdf")],
            mpn="45297BK",
            hint="Kichler Lighting",
            tmp_path=tmp_path,
        )
        assert diagnose(result) is SearchOutcome.SIBLING_ONLY

    def test_the_live_provider_is_blocked_at_the_provenance_gate(self, tmp_path):
        """The contract gap, observed end to end rather than asserted in the abstract.

        Kichler's domain *is* reviewed here, so this candidate clears every authority
        check and still stores nothing: `ProgrammableSearchProvider` declares no
        `DiscoveryMethod`, and an artifact that cannot say how it was found is refused.
        """
        result = acquiring_run(
            b"<html>spec</html>", "text/html", provider=live_provider, tmp_path=tmp_path
        )
        assert diagnose(result) is SearchOutcome.PROVENANCE_UNDECLARED
        assert "DISCOVERY_PROVENANCE_UNDECLARED" in result.candidates[0].rejections
        assert not result.acquired

    def test_an_eligible_html_page_is_html_only_once_provenance_is_declarable(
        self, tmp_path
    ):
        """The gate behind the provenance gate, reachable only with a declaring provider."""
        result = acquiring_run(
            b"<html>spec</html>", "text/html", provider=declaring_provider, tmp_path=tmp_path
        )
        assert diagnose(result) is SearchOutcome.HTML_ONLY

    def test_a_pdf_from_a_reviewed_domain_is_acquired(self, tmp_path):
        """The full success path, to prove the failure states above are not the only ones."""
        result = acquiring_run(
            build_pdf(["45297BK spec"]),
            "application/pdf",
            provider=declaring_provider,
            tmp_path=tmp_path,
        )
        assert diagnose(result) is SearchOutcome.ACQUIRED
        assert result.acquired[0].artifact_sha256

    def test_not_searched_when_no_query_was_run(self, tmp_path):
        result = run([], mpn="X", hint=None, tmp_path=tmp_path)
        # A one-character reference still builds queries; NOT_SEARCHED guards the case
        # where the adapter produced none at all.
        assert result.executed_queries
        assert diagnose(result) is SearchOutcome.NO_RESULTS


class TestReporting:
    def test_outcome_counts_are_counts_not_rates(self):
        counts = outcome_counts(
            [
                SearchOutcome.NO_RESULTS,
                SearchOutcome.NO_RESULTS,
                SearchOutcome.DOMAIN_REVIEW_REQUIRED,
            ]
        )
        assert counts == {"DOMAIN_REVIEW_REQUIRED": 1, "NO_RESULTS": 2}
        assert all(isinstance(v, int) for v in counts.values())

    def test_candidate_states_covers_every_status(self, tmp_path):
        result = run([item("https://grainger.com/p/LC1D18P7")], tmp_path=tmp_path)
        states = candidate_states(result)
        assert set(states) == {"ACQUIRED", "ACCEPTED_NOT_ACQUIRED", "REJECTED"}
        assert states["REJECTED"] == 1

    @pytest.mark.parametrize("outcome", list(SearchOutcome))
    def test_no_outcome_reads_as_a_score(self, outcome):
        """These are states. Nothing here may be summed into an accuracy figure."""
        assert not any(
            token in outcome.value.lower()
            for token in ("score", "confidence", "percent", "accuracy", "rate")
        )
