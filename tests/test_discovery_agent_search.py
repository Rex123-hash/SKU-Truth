"""Agent Search basic website search, exercised entirely offline.

The Discovery Engine client is a fake, but `SearchRequest` is the real SDK type, so the
request this provider builds is one the API would accept. No socket is opened.

Two themes carry the weight. First, that the provider is a *keyword search* and nothing
more: the caller's query goes out verbatim, no model is involved, and no generated text
exists to leak. Second, that the corpus is the human-reviewed set and only that set — a
provider result can never add a domain, and an unreviewed domain licenses nothing.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

import httpx
import pytest
from conftest_pdf import build_pdf
from skutruth.contracts import DiscoveryMethod, RunMode
from skutruth.discovery import (
    AgentSearchConfig,
    AgentSearchConfigError,
    AgentSearchLimits,
    AgentSearchProvider,
    DiscoveryRequest,
    SearchCall,
    SearchProviderTimeout,
    SearchProviderTransportError,
    build_filter,
    discover_sources,
    included_patterns_for,
)
from skutruth.discovery.agent_search import (
    ENV_ENGINE_ID,
    MAX_INCLUDED_PATTERNS,
    normalize_results,
)
from skutruth.discovery.domains import parse_registry
from skutruth.discovery.errors import MalformedSearchResponseError, SearchBudgetExceededError
from skutruth.discovery.models import MpnRelevance, SourceAuthority
from skutruth.ingest.storage import ArtifactStore
from skutruth.replay.errors import ReplayMissError
from skutruth.replay.store import CassetteStore

CONFIG = AgentSearchConfig(project="test-project", engine_id="skutruth-manufacturers")

REVIEWED_TOML = """
name = "agent-search-registry"
authority = "REVIEWED"

[[manufacturer]]
key = "kichler-lighting"
authority_hints = ["Kichler Lighting"]
domains = ["kichler.com"]

[manufacturer.review]
reviewed_at = "2026-08-17"
reviewed_by = "A Real Person"
basis = "Confirmed kichler.com is operated by Kichler Lighting."

[[manufacturer]]
key = "schneider-electric"
authority_hints = ["Schneider Electric"]
domains = ["se.com"]

[hosts]
distributors = ["grainger.com"]
"""


def registry(text: str = REVIEWED_TOML):
    return parse_registry(tomllib.loads(text), source="agent-search-registry")


# -- a fake shaped like a Discovery Engine response ---------------------------


@dataclass
class FakeDocument:
    derived_struct_data: dict = field(default_factory=dict)


@dataclass
class FakeResult:
    document: FakeDocument


@dataclass
class FakeResponse:
    results: list


class FakeSearchClient:
    def __init__(self, results=None, error=None):
        self._results = results or []
        self._error = error
        self.requests: list = []

    def search(self, request=None, timeout=None):
        self.requests.append((request, timeout))
        if self._error is not None:
            raise self._error
        return FakeResponse(self._results)


def result_for(link, title="", snippets=None):
    derived = {"link": link, "title": title}
    if snippets is not None:
        derived["snippets"] = snippets
    return FakeResult(FakeDocument(derived))


def provider_for(results=None, *, error=None, limits=None, sites=(), pdf_only=False):
    return AgentSearchProvider(
        CONFIG,
        limits=limits or AgentSearchLimits(),
        site_patterns=sites,
        pdf_only=pdf_only,
        client=FakeSearchClient(results, error),
    )


KICHLER_PDF = result_for(
    "https://www.kichler.com/documents/spec/45297BK.pdf",
    "45297BK Specification Sheet",
    [{"snippet": "45297BK · 3-light chandelier · 60 W max"}],
)


class TestProvenance:
    def test_the_provider_declares_site_restricted_search(self):
        """A."""
        assert (
            provider_for().discovery_method is DiscoveryMethod.SITE_RESTRICTED_SEARCH
        )

    def test_it_does_not_claim_grounding_or_a_curated_corpus(self):
        method = provider_for().discovery_method
        assert method is not DiscoveryMethod.GOOGLE_SEARCH_GROUNDING
        assert method is not DiscoveryMethod.CURATED_CORPUS
        assert method is not DiscoveryMethod.DIRECT_URL

    def test_the_new_enum_value_is_additive(self):
        """Existing members keep their names and values."""
        assert {m.value for m in DiscoveryMethod} >= {
            "CURATED_CORPUS",
            "GOOGLE_SEARCH_GROUNDING",
            "URL_CONTEXT",
            "DIRECT_URL",
            "OPERATOR_SUPPLIED",
        }
        assert DiscoveryMethod.SITE_RESTRICTED_SEARCH.value == "SITE_RESTRICTED_SEARCH"

    def test_the_declaration_reaches_stored_provenance(self, tmp_path):
        result = acquiring_run(build_pdf(["45297BK"]), "application/pdf", tmp_path=tmp_path)
        stored = ArtifactStore(tmp_path / "artifacts").load(
            result.acquired[0].artifact_sha256
        )
        assert stored.source.discovery_method is DiscoveryMethod.SITE_RESTRICTED_SEARCH


class TestQueryIsExecutedVerbatim:
    def test_the_exact_caller_query_is_sent_unchanged(self):
        """B, R. No prompt, no rewriting, no normalisation of the reference."""
        provider = provider_for([KICHLER_PDF])
        provider.search(SearchCall(query="45297BK", max_results=5))
        request, _ = provider._client.requests[0]
        assert request.query == "45297BK"

    def test_a_reference_that_looks_like_a_typo_is_not_repaired(self):
        provider = provider_for([])
        provider.search(SearchCall(query="DCB518ASTS06G", max_results=5))
        assert provider._client.requests[0][0].query == "DCB518ASTS06G"

    def test_the_serving_config_path_is_fully_qualified(self):
        provider = provider_for([])
        provider.search(SearchCall(query="q", max_results=5))
        assert provider._client.requests[0][0].serving_config == (
            "projects/test-project/locations/global/collections/default_collection"
            "/engines/skutruth-manufacturers/servingConfigs/default_search"
        )

    def test_the_result_cap_is_passed_as_page_size(self):
        provider = provider_for([], limits=AgentSearchLimits(max_results_per_query=4))
        provider.search(SearchCall(query="q", max_results=10))
        assert provider._client.requests[0][0].page_size == 4

    def test_an_empty_query_is_refused_before_a_call(self):
        provider = provider_for([])
        with pytest.raises(MalformedSearchResponseError):
            provider.search(SearchCall(query="   "))
        assert provider.calls_made == 0

    def test_no_generated_answer_or_suggestions_handling_exists(self):
        """X, Y. There is no model, so there is nothing to discard or display.

        Checks code, not prose: the module's docstring explains at length why grounding
        was dropped, and a raw substring scan would trip over its own explanation.
        """
        import ast

        from skutruth.discovery import agent_search

        with open(agent_search.__file__, encoding="utf-8") as handle:
            tree = ast.parse(handle.read())
        names = {
            node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)
        } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        literals = {
            node.value
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        for banned in ("generate_content", "search_entry_point", "renderedContent"):
            assert banned not in names, banned
            assert banned not in literals, banned
        # And no summary/answer feature is requested anywhere.
        for banned in ("summary_spec", "SummarySpec", "answer", "content_search_spec"):
            assert banned not in names, banned


class TestFilters:
    def test_the_pdf_filter_uses_the_documented_syntax(self):
        """N."""
        assert build_filter(pdf_only=True) == 'fileType:".pdf"'

    def test_site_search_uses_the_documented_syntax(self):
        """O."""
        assert build_filter(site_patterns=("kichler.com/*",)) == 'siteSearch:"kichler.com/*"'

    def test_several_sites_are_combined_with_or(self):
        expression = build_filter(site_patterns=("a.com/*", "b.com/*"))
        assert expression == '(siteSearch:"a.com/*" OR siteSearch:"b.com/*")'

    def test_site_and_file_type_combine_with_and(self):
        expression = build_filter(site_patterns=("kichler.com/*",), pdf_only=True)
        assert expression == 'siteSearch:"kichler.com/*" AND fileType:".pdf"'

    def test_no_filter_is_an_empty_expression(self):
        assert build_filter() == ""

    def test_the_filter_reaches_the_request(self):
        provider = provider_for([], sites=("kichler.com/*",), pdf_only=True)
        provider.search(SearchCall(query="45297BK", max_results=5))
        request, _ = provider._client.requests[0]
        assert request.filter == 'siteSearch:"kichler.com/*" AND fileType:".pdf"'

    def test_for_pdfs_returns_a_sibling_rather_than_mutating(self):
        base = provider_for([], sites=("kichler.com/*",))
        pdfs = base.for_pdfs()
        assert base.filter_expression() != pdfs.filter_expression()
        assert 'fileType:".pdf"' in pdfs.filter_expression()


class TestCorpusIsTheReviewedSet:
    def test_only_reviewed_domains_become_url_patterns(self):
        """O, Q. Schneider is in the registry, unreviewed, and stays out."""
        assert included_patterns_for(registry()) == ("kichler.com/*",)

    def test_an_unreviewed_registry_yields_no_patterns(self):
        text = REVIEWED_TOML.replace(
            '[manufacturer.review]\nreviewed_at = "2026-08-17"\n'
            'reviewed_by = "A Real Person"\n'
            'basis = "Confirmed kichler.com is operated by Kichler Lighting."\n',
            "",
        )
        assert included_patterns_for(registry(text)) == ()

    def test_provider_output_cannot_add_a_domain(self):
        """Q. A result from an unlisted host changes nothing about the corpus."""
        before = included_patterns_for(registry())
        provider_for([result_for("https://kichler-outlet.example/45297BK")]).search(
            SearchCall(query="45297BK", max_results=5)
        )
        assert included_patterns_for(registry()) == before

    def test_the_fifty_pattern_limit_is_enforced_rather_than_truncated(self):
        """P. Silently dropping one would make a reviewed domain unsearchable."""
        entries = "\n".join(
            f'[[manufacturer]]\nkey = "m{i}"\nauthority_hints = ["M{i}"]\n'
            f'domains = ["m{i}.example"]\n\n'
            f'[manufacturer.review]\nreviewed_at = "2026-08-17"\n'
            f'reviewed_by = "A Real Person"\nbasis = "Checked m{i}.example."\n'
            for i in range(MAX_INCLUDED_PATTERNS + 1)
        )
        big = f'name = "big"\nauthority = "REVIEWED"\n\n{entries}'
        with pytest.raises(AgentSearchConfigError) as exc:
            included_patterns_for(registry(big))
        assert str(MAX_INCLUDED_PATTERNS) in str(exc.value)

    def test_exactly_fifty_patterns_is_allowed(self):
        entries = "\n".join(
            f'[[manufacturer]]\nkey = "m{i}"\nauthority_hints = ["M{i}"]\n'
            f'domains = ["m{i}.example"]\n\n'
            f'[manufacturer.review]\nreviewed_at = "2026-08-17"\n'
            f'reviewed_by = "A Real Person"\nbasis = "Checked m{i}.example."\n'
            for i in range(MAX_INCLUDED_PATTERNS)
        )
        big = f'name = "big"\nauthority = "REVIEWED"\n\n{entries}'
        assert len(included_patterns_for(registry(big))) == MAX_INCLUDED_PATTERNS


class TestNormalization:
    def test_derived_struct_data_link_becomes_the_result_url(self):
        """D. The real publisher URL, with no redirect abstraction."""
        rows = normalize_results([KICHLER_PDF], limit=10)
        assert rows[0]["url"] == "https://www.kichler.com/documents/spec/45297BK.pdf"

    def test_title_is_retained(self):
        """E."""
        assert normalize_results([KICHLER_PDF], limit=10)[0]["title"] == (
            "45297BK Specification Sheet"
        )

    def test_snippet_is_retained_as_locator_metadata(self):
        """F."""
        assert "3-light chandelier" in normalize_results([KICHLER_PDF], limit=10)[0]["snippet"]

    def test_publisher_host_is_not_set_by_this_provider(self):
        """The URL is already the publisher's; nothing is special-cased."""
        rows = normalize_results([KICHLER_PDF], limit=10)
        assert "publisher_host" not in rows[0]

    def test_a_result_without_a_link_is_skipped(self):
        """W."""
        assert normalize_results([result_for("", "no link")], limit=10) == []

    def test_a_result_with_no_derived_data_is_skipped(self):
        assert normalize_results([FakeResult(FakeDocument({}))], limit=10) == []

    def test_missing_snippets_become_empty(self):
        rows = normalize_results([result_for("https://x.example/a")], limit=10)
        assert rows[0]["snippet"] == ""

    def test_rank_follows_result_order(self):
        rows = normalize_results(
            [result_for(f"https://x.example/{i}") for i in range(1, 4)], limit=10
        )
        assert [r["rank"] for r in rows] == [1, 2, 3]

    def test_the_limit_is_honoured(self):
        rows = normalize_results(
            [result_for(f"https://x.example/{i}") for i in range(20)], limit=3
        )
        assert len(rows) == 3

    def test_an_empty_response_is_not_an_error(self):
        assert provider_for([]).search(SearchCall(query="q", max_results=5)) == []


class TestRelevanceGateUnchanged:
    """H, I, J, G. The gate is untouched; direct URLs simply make EXACT reachable."""

    def _relevance(self, link, title="", mpn="45297BK", snippet=None, tmp_path=None):
        result = run_discovery(
            [result_for(link, title, [{"snippet": snippet}] if snippet else None)],
            mpn=mpn,
            tmp_path=tmp_path,
        )
        return result.candidates[0].relevance

    def test_exact_mpn_in_the_url_is_exact(self, tmp_path):
        """H. The thing grounding could not do."""
        assert (
            self._relevance(
                "https://www.kichler.com/spec/45297BK.pdf", tmp_path=tmp_path
            )
            is MpnRelevance.EXACT
        )

    def test_exact_mpn_in_the_title_is_exact(self, tmp_path):
        assert (
            self._relevance(
                "https://www.kichler.com/p/12345", "45297BK spec sheet", tmp_path=tmp_path
            )
            is MpnRelevance.EXACT
        )

    def test_a_family_stem_remains_family_only(self, tmp_path):
        """I."""
        assert (
            self._relevance("https://www.kichler.com/spec/45297.pdf", tmp_path=tmp_path)
            is MpnRelevance.FAMILY_ONLY
        )

    def test_a_sibling_remains_sibling(self, tmp_path):
        """J."""
        assert (
            self._relevance("https://www.kichler.com/spec/45297AZ.pdf", tmp_path=tmp_path)
            is MpnRelevance.SIBLING
        )

    def test_a_snippet_cannot_establish_relevance(self, tmp_path):
        """G. The MPN appears only in the snippet; the gate must not see it."""
        assert (
            self._relevance(
                "https://www.kichler.com/p/12345",
                "Chandelier",
                snippet="Model 45297BK, 3-light chandelier",
                tmp_path=tmp_path,
            )
            is MpnRelevance.ABSENT
        )


class TestAuthorityGatesUnchanged:
    def test_a_result_on_an_unreviewed_domain_cannot_license(self, tmp_path):
        """K. Schneider is registered but unreviewed."""
        result = run_discovery(
            [result_for("https://se.com/docs/LC1D18P7.pdf")],
            mpn="LC1D18P7",
            hint="Schneider Electric",
            tmp_path=tmp_path,
        )
        candidate = result.candidates[0]
        assert candidate.authority is SourceAuthority.UNVERIFIED_MANUFACTURER
        assert not candidate.may_store_as_manufacturer_evidence

    def test_a_result_on_a_reviewed_domain_becomes_eligible_when_exact(self, tmp_path):
        """L."""
        result = run_discovery(
            [result_for("https://www.kichler.com/spec/45297BK.pdf")], tmp_path=tmp_path
        )
        candidate = result.candidates[0]
        assert candidate.authority is SourceAuthority.APPROVED_MANUFACTURER
        assert candidate.is_eligible

    def test_a_distributor_result_is_refused(self, tmp_path):
        result = run_discovery(
            [result_for("https://grainger.com/p/45297BK")], tmp_path=tmp_path
        )
        assert result.candidates[0].authority is SourceAuthority.KNOWN_DISTRIBUTOR

    def test_a_lookalike_host_is_not_the_manufacturer(self, tmp_path):
        result = run_discovery(
            [result_for("https://kichler.com.evil.example/45297BK.pdf")], tmp_path=tmp_path
        )
        assert result.candidates[0].authority is SourceAuthority.UNKNOWN

    def test_final_redirect_authority_remains_mandatory(self, tmp_path):
        """M. A reviewed domain that redirects off-host still stores nothing."""
        result = acquiring_run(
            build_pdf(["45297BK"]),
            "application/pdf",
            tmp_path=tmp_path,
            redirect_to="random-third-party.example",
        )
        candidate = result.candidates[0]
        assert "REDIRECT_AUTHORITY_LOST" in candidate.rejections
        assert not result.acquired

    def test_the_permitted_path_ingests(self, tmp_path):
        result = acquiring_run(build_pdf(["45297BK"]), "application/pdf", tmp_path=tmp_path)
        assert result.acquired and result.candidates[0].artifact_sha256


class TestQueryProvenance:
    def test_requested_and_provider_queries_coincide(self, tmp_path):
        """S. Agent Search runs our query, so nothing is reported as rewritten."""
        result = run_discovery([KICHLER_PDF], tmp_path=tmp_path)
        assert result.requested_queries
        assert result.provider_executed_queries == ()
        assert not result.search_execution_was_provider_generated

    def test_queries_come_from_the_deterministic_builder(self, tmp_path):
        result = run_discovery([KICHLER_PDF], tmp_path=tmp_path)
        assert result.requested_queries == (
            '"45297BK" site:kichler.com',
            '"45297BK" Kichler Lighting',
            '"45297BK" datasheet',
        )


class TestTypedFailures:
    def test_a_timeout_is_typed(self):
        provider = provider_for(error=TimeoutError("deadline"))
        with pytest.raises(SearchProviderTimeout):
            provider.search(SearchCall(query="q"))

    def test_a_transport_failure_is_typed_without_echoing_its_text(self):
        """V."""
        provider = provider_for(error=RuntimeError("https://internal?token=sekrit"))
        with pytest.raises(SearchProviderTransportError) as exc:
            provider.search(SearchCall(query="q"))
        assert "sekrit" not in str(exc.value)
        assert exc.value.__cause__ is None

    def test_the_call_budget_is_enforced(self):
        provider = provider_for([], limits=AgentSearchLimits(max_calls=1))
        provider.search(SearchCall(query="a"))
        with pytest.raises(SearchBudgetExceededError):
            provider.search(SearchCall(query="b"))

    def test_a_failed_call_counts_against_the_budget(self):
        provider = provider_for(error=RuntimeError("boom"), limits=AgentSearchLimits(max_calls=1))
        with pytest.raises(SearchProviderTransportError):
            provider.search(SearchCall(query="a"))
        with pytest.raises(SearchBudgetExceededError):
            provider.search(SearchCall(query="b"))

    def test_limits_must_be_positive(self):
        with pytest.raises(ValueError):
            AgentSearchLimits(max_calls=0)


class TestConfig:
    def test_missing_engine_id_refuses(self, monkeypatch):
        monkeypatch.setenv("SKUTRUTH_GCP_PROJECT", "p")
        monkeypatch.delenv(ENV_ENGINE_ID, raising=False)
        with pytest.raises(AgentSearchConfigError) as exc:
            AgentSearchConfig.from_env()
        assert ENV_ENGINE_ID in str(exc.value)

    def test_missing_project_refuses(self, monkeypatch):
        monkeypatch.delenv("SKUTRUTH_GCP_PROJECT", raising=False)
        monkeypatch.setenv(ENV_ENGINE_ID, "e")
        with pytest.raises(AgentSearchConfigError):
            AgentSearchConfig.from_env()

    def test_configuration_is_read_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("SKUTRUTH_GCP_PROJECT", "proj")
        monkeypatch.setenv(ENV_ENGINE_ID, "engine")
        config = AgentSearchConfig.from_env()
        assert (config.project, config.engine_id, config.location) == (
            "proj",
            "engine",
            "global",
        )

    def test_no_project_id_is_hardcoded(self):
        from skutruth.discovery import agent_search

        with open(agent_search.__file__, encoding="utf-8") as handle:
            assert "project-" not in handle.read()


class TestReplay:
    def test_replay_makes_zero_provider_calls(self, tmp_path):
        """T."""
        run_discovery([KICHLER_PDF], tmp_path=tmp_path, mode=RunMode.LIVE)
        # Same configuration, so the same replay key: this proves replay served the
        # recording, not that a mismatched key quietly missed.
        exploding = AgentSearchProvider(
            CONFIG,
            site_patterns=included_patterns_for(registry()),
            client=_ExplodingClient(),
        )
        replayed = run_discovery(
            [KICHLER_PDF], tmp_path=tmp_path, mode=RunMode.REPLAY, provider=exploding
        )
        assert replayed.candidates
        assert exploding.calls_made == 0

    def test_a_replay_miss_fails_closed(self, tmp_path):
        """U."""
        from skutruth.discovery import execute_search

        with pytest.raises(ReplayMissError):
            execute_search(
                SearchCall(query="never recorded", max_results=5),
                provider=AgentSearchProvider(CONFIG, client=_ExplodingClient()),
                store=CassetteStore(tmp_path),
                mode=RunMode.REPLAY,
            )

    def test_the_engine_and_filter_are_part_of_the_replay_key(self):
        from skutruth.discovery.provider import declared_request_options, search_request

        a = provider_for([], sites=("kichler.com/*",))
        b = provider_for([], sites=("kichler.com/*",), pdf_only=True)
        keys = {
            search_request(
                "q", provider=p.name, max_results=5, options=declared_request_options(p)
            ).cassette_key()
            for p in (a, b)
        }
        assert len(keys) == 2

    def test_a_different_engine_is_a_different_recording(self):
        from skutruth.discovery.provider import declared_request_options, search_request

        other = AgentSearchProvider(
            AgentSearchConfig(project="test-project", engine_id="another-engine"),
            client=FakeSearchClient([]),
        )
        base = provider_for([])
        keys = {
            search_request(
                "q", provider=p.name, max_results=5, options=declared_request_options(p)
            ).cassette_key()
            for p in (base, other)
        }
        assert len(keys) == 2


class TestRemovedProvidersStayRemoved:
    def test_the_grounding_adapter_is_absent(self):
        """Z."""
        from pathlib import Path

        package = Path(__file__).resolve().parents[1] / "backend" / "skutruth" / "discovery"
        assert not (package / "grounded_search.py").exists()

        import skutruth.discovery as discovery

        assert "VertexGroundedSearchProvider" not in discovery.__all__
        assert not hasattr(discovery, "VertexGroundedSearchProvider")

    def test_the_custom_search_adapter_is_absent(self):
        """AA."""
        from pathlib import Path

        package = Path(__file__).resolve().parents[1] / "backend" / "skutruth" / "discovery"
        assert not (package / "programmable_search.py").exists()

        import skutruth.discovery as discovery

        assert "ProgrammableSearchProvider" not in discovery.__all__

    def test_no_active_code_references_either_removed_provider(self):
        """C, Z, AA. Historical docs and commit messages are untouched by design."""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        for path in [*(root / "backend").rglob("*.py"), *(root / "scripts").glob("*.py")]:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "grounded_search" not in node.module, path
                    assert "programmable_search" not in node.module, path
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        assert "grounded_search" not in alias.name, path
                        assert "programmable_search" not in alias.name, path


class _ExplodingClient:
    def search(self, request=None, timeout=None):  # pragma: no cover - must never run
        raise AssertionError("REPLAY reached the provider")


# -- shared drivers -------------------------------------------------------------


def run_discovery(
    results, *, mpn="45297BK", hint="Kichler Lighting", tmp_path, mode=RunMode.LIVE, provider=None
):
    return discover_sources(
        DiscoveryRequest(mpn=mpn, manufacturer_hint=hint),
        provider=provider or provider_for(results, sites=included_patterns_for(registry())),
        registry=registry(),
        cassettes=CassetteStore(tmp_path),
        mode=mode,
    )


def acquiring_run(body, content_type, *, tmp_path, redirect_to=None):
    """Discovery against the reviewed domain, with a document served for the fetch."""

    def handler(request: httpx.Request) -> httpx.Response:
        if redirect_to and request.url.host == "www.kichler.com":
            return httpx.Response(302, headers={"location": f"https://{redirect_to}/doc.pdf"})
        return httpx.Response(200, content=body, headers={"content-type": content_type})

    transport = httpx.MockTransport(handler)
    return discover_sources(
        DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
        provider=provider_for(
            [result_for("https://www.kichler.com/spec/45297BK.pdf", "45297BK spec")],
            sites=included_patterns_for(registry()),
        ),
        registry=registry(),
        cassettes=CassetteStore(tmp_path / "cassettes"),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        mode=RunMode.LIVE,
        transport=transport,
        resolver=lambda host: ["93.184.216.34"],
    )
