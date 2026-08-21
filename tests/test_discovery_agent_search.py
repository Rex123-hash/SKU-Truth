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
    corpus_pattern_for,
    discover_sources,
    execute_search,
    included_patterns_for,
    query_site_pattern_for,
    reviewed_patterns_for_hint,
)
from skutruth.discovery.agent_search import (
    ENV_ENGINE_ID,
    MAX_INCLUDED_PATTERNS,
    MAX_RESULTS_PER_QUERY,
    normalize_results,
    with_limits,
)
from skutruth.discovery.domains import parse_registry
from skutruth.discovery.errors import MalformedSearchResponseError, SearchBudgetExceededError
from skutruth.discovery.models import MpnRelevance, SourceAuthority
from skutruth.discovery.provider import declared_request_options, search_request
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

TWO_MANUFACTURERS = REVIEWED_TOML + """
[[manufacturer]]
key = "freud"
authority_hints = ["Freud Inc"]
domains = ["freudtools.com"]

[manufacturer.review]
reviewed_at = "2026-08-17"
reviewed_by = "A Real Person"
basis = "Confirmed freudtools.com is operated by Freud."
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
    """Basic website search grammar is `expression, { "AND", expression }`. No OR."""

    def test_the_pdf_filter_uses_the_documented_syntax(self):
        """N."""
        assert build_filter(pdf_only=True) == 'fileType:".pdf"'

    def test_site_search_uses_the_documented_url_pattern(self):
        """O. Google's examples are full URLs with a wildcard, not bare hostnames."""
        assert (
            build_filter(site_pattern="https://kichler.com/*")
            == 'siteSearch:"https://kichler.com/*"'
        )

    def test_query_site_pattern_for_builds_the_documented_filter_form(self):
        """B. The filter surface documents full URLs, so the scheme stays."""
        assert query_site_pattern_for("kichler.com") == "https://kichler.com/*"
        assert query_site_pattern_for("WWW.Kichler.com") == "https://kichler.com/*"

    def test_site_and_file_type_combine_with_and(self):
        """B."""
        assert build_filter(site_pattern="https://kichler.com/*", pdf_only=True) == (
            'siteSearch:"https://kichler.com/*" AND fileType:".pdf"'
        )

    def test_no_filter_is_an_empty_expression(self):
        assert build_filter() == ""

    def test_build_filter_cannot_emit_or(self):
        """C. The signature takes one pattern, so an OR filter is unrepresentable.

        `OR` belongs to the advanced-indexing grammar. With advanced indexing off the
        backend answers "Unsupported expression type in filter", so an OR we could
        construct would be a runtime parse failure rather than a type error.
        """
        import inspect

        assert "site_patterns" not in inspect.signature(build_filter).parameters
        for expression in (
            build_filter(site_pattern="https://a.com/*"),
            build_filter(site_pattern="https://a.com/*", pdf_only=True),
            build_filter(pdf_only=True),
            build_filter(),
        ):
            assert " OR " not in expression

    def test_several_domains_produce_several_filters_never_one_or(self):
        """D, I. One expression per domain."""
        provider = provider_for(
            [], sites=("https://makitatools.com/*", "https://makita.com/*")
        )
        expressions = provider.filter_expressions()
        assert expressions == (
            'siteSearch:"https://makitatools.com/*"',
            'siteSearch:"https://makita.com/*"',
        )
        assert all(" OR " not in e for e in expressions)

    def test_a_multi_domain_provider_refuses_to_give_one_filter(self):
        """There is no single valid expression, so none is invented."""
        provider = provider_for([], sites=("https://a.com/*", "https://b.com/*"))
        with pytest.raises(AgentSearchConfigError):
            provider.filter_expression()

    def test_the_filter_reaches_the_request(self):
        provider = provider_for([], sites=("https://kichler.com/*",), pdf_only=True)
        provider.search(SearchCall(query="45297BK", max_results=5))
        request, _ = provider._client.requests[0]
        assert request.filter == 'siteSearch:"https://kichler.com/*" AND fileType:".pdf"'

    def test_for_pdfs_returns_a_sibling_rather_than_mutating(self):
        base = provider_for([], sites=("https://kichler.com/*",))
        pdfs = base.for_pdfs()
        assert base.filter_expression() != pdfs.filter_expression()
        assert 'fileType:".pdf"' in pdfs.filter_expression()


class TestMultiDomainFanOut:
    """D, E, F. Several reviewed domains mean several bounded requests."""

    def _fan_out(self):
        provider = provider_for(
            [result_for("https://www.makitatools.com/XLC10ZW.pdf", "XLC10ZW")],
            sites=("https://makitatools.com/*", "https://makita.com/*"),
        )
        rows = provider.search(SearchCall(query="XLC10ZW", max_results=5))
        return provider, rows

    def test_one_request_is_issued_per_domain(self):
        provider, _ = self._fan_out()
        assert len(provider._client.requests) == 2
        assert [r.filter for r, _ in provider._client.requests] == [
            'siteSearch:"https://makitatools.com/*"',
            'siteSearch:"https://makita.com/*"',
        ]

    def test_every_request_carries_the_same_verbatim_query(self):
        provider, _ = self._fan_out()
        assert {r.query for r, _ in provider._client.requests} == {"XLC10ZW"}

    def test_duplicate_urls_dedupe_across_domains(self):
        """F. The fake returns the same document for both domains."""
        _, rows = self._fan_out()
        assert len(rows) == 1

    def test_distinct_urls_merge_in_domain_order(self):
        """E. Deterministic: domains in configured order, results in provider order."""

        class TwoDomainClient:
            def __init__(self):
                self.requests = []

            def search(self, request=None, timeout=None):
                self.requests.append((request, timeout))
                host = (
                    "makitatools.com" if "makitatools" in request.filter else "makita.com"
                )
                return FakeResponse(
                    [
                        result_for(f"https://{host}/a-XLC10ZW.pdf"),
                        result_for(f"https://{host}/b-XLC10ZW.pdf"),
                    ]
                )

        provider = AgentSearchProvider(
            CONFIG,
            site_patterns=("https://makitatools.com/*", "https://makita.com/*"),
            client=TwoDomainClient(),
        )
        rows = provider.search(SearchCall(query="XLC10ZW", max_results=5))
        assert [r["url"] for r in rows] == [
            "https://makitatools.com/a-XLC10ZW.pdf",
            "https://makitatools.com/b-XLC10ZW.pdf",
            "https://makita.com/a-XLC10ZW.pdf",
            "https://makita.com/b-XLC10ZW.pdf",
        ]

    def test_the_fan_out_is_bounded_by_the_call_budget(self):
        provider = provider_for(
            [],
            sites=("https://a.com/*", "https://b.com/*", "https://c.com/*"),
            limits=AgentSearchLimits(max_calls=2),
        )
        with pytest.raises(SearchBudgetExceededError):
            provider.search(SearchCall(query="q", max_results=5))
        assert provider.calls_made == 2

    def test_each_domain_costs_one_call(self):
        provider, _ = self._fan_out()
        assert provider.calls_made == 2


class TestPerManufacturerFilter:
    """G, H. A row searches its own manufacturer's domains, and no one else's."""

    def test_a_reviewed_manufacturer_yields_only_its_own_domains(self):
        assert reviewed_patterns_for_hint(registry(), "Kichler Lighting") == (
            "https://kichler.com/*",
        )

    def test_an_unreviewed_manufacturer_yields_nothing(self):
        """H. Empty means: make no Agent Search call for this row."""
        assert reviewed_patterns_for_hint(registry(), "Schneider Electric") == ()

    def test_an_unknown_hint_yields_nothing(self):
        assert reviewed_patterns_for_hint(registry(), "Nobody At All") == ()

    def test_a_locator_only_spelling_yields_nothing(self):
        """A locator hint may find a page; it may never target an evidence search."""
        text = REVIEWED_TOML.replace(
            'authority_hints = ["Kichler Lighting"]',
            'authority_hints = ["Kichler Lighting"]\nlocator_hints = ["Kichlar"]',
            1,
        )
        assert reviewed_patterns_for_hint(registry(text), "Kichlar") == ()

    def test_a_kichler_query_does_not_search_freuds_domain(self):
        """G, I. The corpus holds both; one row searches one."""
        reg = registry(TWO_MANUFACTURERS)
        assert set(included_patterns_for(reg)) == {"kichler.com/*", "freudtools.com/*"}
        patterns = reviewed_patterns_for_hint(reg, "Kichler Lighting")
        assert patterns == ("https://kichler.com/*",)

        provider = provider_for([], sites=patterns)
        provider.search(SearchCall(query="45297BK", max_results=5))
        filters = [r.filter for r, _ in provider._client.requests]
        assert filters == ['siteSearch:"https://kichler.com/*"']
        assert not any("freudtools" in f for f in filters)


class TestCopyPreservesSearchSemantics:
    """J. A helper that changes limits must not drop a filter."""

    def test_with_limits_preserves_pdf_only(self):
        pdf_provider = provider_for([], sites=("https://kichler.com/*",)).for_pdfs()
        copy = with_limits(pdf_provider, max_calls=5)
        assert copy.filter_expression() == pdf_provider.filter_expression()
        assert 'fileType:".pdf"' in copy.filter_expression()

    def test_with_limits_preserves_site_patterns_and_config(self):
        base = provider_for([], sites=("https://kichler.com/*",))
        copy = with_limits(base, max_calls=7)
        assert copy.site_patterns == base.site_patterns
        assert copy.config == base.config
        assert copy.limits.max_calls == 7

    def test_with_limits_resets_the_call_budget(self):
        base = provider_for([], sites=("https://kichler.com/*",))
        base.search(SearchCall(query="q", max_results=5))
        assert with_limits(base, max_calls=9).calls_made == 0

    def test_request_options_are_identical_across_a_limits_copy(self):
        """The replay key must not move because the budget changed."""
        base = provider_for([], sites=("https://kichler.com/*",)).for_pdfs()
        assert with_limits(base, max_calls=3).request_options() == base.request_options()


class TestPageSizeBound:
    """K, L. Basic website search documents pageSize max 25 (default 10)."""

    def test_one_is_accepted(self):
        assert AgentSearchLimits(max_results_per_query=1).max_results_per_query == 1

    def test_twenty_five_is_accepted(self):
        assert AgentSearchLimits(max_results_per_query=25).max_results_per_query == 25

    def test_twenty_six_is_rejected(self):
        with pytest.raises(ValueError) as exc:
            AgentSearchLimits(max_results_per_query=26)
        assert "25" in str(exc.value)

    def test_zero_is_rejected(self):
        with pytest.raises(ValueError):
            AgentSearchLimits(max_results_per_query=0)

    def test_the_default_matches_the_documented_default(self):
        assert AgentSearchLimits().max_results_per_query == 10

    def test_the_page_size_bound_is_not_the_corpus_bound(self):
        assert MAX_RESULTS_PER_QUERY == 25
        assert MAX_INCLUDED_PATTERNS == 50


class TestCorpusAndFilterPatternsAreDifferentFormats:
    """A, B, C, D. Two Google API surfaces, two documented syntaxes, two helpers.

    The data store's `TargetSite.provided_uri_pattern` is documented as excluding the
    http/https protocol; the query-time `siteSearch` filter is documented with full URLs.
    Reusing one string for both would put a scheme where the docs forbid one — and the
    failure would only appear at provisioning time, in a console, to a person.
    """

    def test_the_corpus_pattern_carries_no_scheme(self):
        """A."""
        assert corpus_pattern_for("kichler.com") == "kichler.com/*"
        assert corpus_pattern_for("WWW.Kichler.com") == "kichler.com/*"

    def test_the_query_pattern_carries_the_scheme(self):
        """B."""
        assert query_site_pattern_for("kichler.com") == "https://kichler.com/*"

    def test_the_two_representations_are_not_the_same_string(self):
        assert corpus_pattern_for("kichler.com") != query_site_pattern_for("kichler.com")

    def test_the_corpus_uses_the_corpus_representation(self):
        """C."""
        assert included_patterns_for(registry()) == ("kichler.com/*",)

    def test_the_query_filter_uses_the_query_representation(self):
        """D."""
        assert reviewed_patterns_for_hint(registry(), "Kichler Lighting") == (
            "https://kichler.com/*",
        )

    def test_no_corpus_pattern_carries_a_protocol(self):
        assert not any(p.startswith("http") for p in included_patterns_for(registry()))

    def test_the_runtime_filter_is_built_from_the_query_representation(self):
        """G. Registry to filter expression, with nothing hand-written in between."""
        (pattern,) = reviewed_patterns_for_hint(registry(), "Kichler Lighting")
        assert build_filter(site_pattern=pattern) == 'siteSearch:"https://kichler.com/*"'

    def test_the_runtime_pdf_filter_is_unchanged(self):
        """H."""
        (pattern,) = reviewed_patterns_for_hint(registry(), "Kichler Lighting")
        assert build_filter(site_pattern=pattern, pdf_only=True) == (
            'siteSearch:"https://kichler.com/*" AND fileType:".pdf"'
        )

    def test_an_empty_domain_is_refused_by_both_helpers(self):
        for helper in (corpus_pattern_for, query_site_pattern_for):
            with pytest.raises(AgentSearchConfigError):
                helper("   ")


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

    def test_explicit_queries_replace_only_this_calls_query_strategy(self, tmp_path):
        provider = provider_for(
            [KICHLER_PDF],
            sites=reviewed_patterns_for_hint(registry(), "Kichler Lighting"),
        )
        result = discover_sources(
            DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
            provider=provider,
            registry=registry(),
            cassettes=CassetteStore(tmp_path),
            queries=("45297BK",),
            mode=RunMode.LIVE,
        )

        assert result.requested_queries == ("45297BK",)
        assert [request.query for request, _ in provider._client.requests] == ["45297BK"]


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
            site_patterns=reviewed_patterns_for_hint(registry(), "Kichler Lighting"),
            client=_ExplodingClient(),
        )
        replayed = run_discovery(
            [KICHLER_PDF], tmp_path=tmp_path, mode=RunMode.REPLAY, provider=exploding
        )
        assert replayed.candidates
        assert exploding.calls_made == 0

    def test_explicit_query_replay_makes_zero_provider_calls(self, tmp_path):
        patterns = reviewed_patterns_for_hint(registry(), "Kichler Lighting")
        live = discover_sources(
            DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
            provider=provider_for([KICHLER_PDF], sites=patterns, pdf_only=True),
            registry=registry(),
            cassettes=CassetteStore(tmp_path),
            queries=("45297BK",),
            mode=RunMode.LIVE,
        )
        replay_provider = AgentSearchProvider(
            CONFIG,
            site_patterns=patterns,
            pdf_only=True,
            client=_ExplodingClient(),
        )
        replayed = discover_sources(
            DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
            provider=replay_provider,
            registry=registry(),
            cassettes=CassetteStore(tmp_path),
            queries=("45297BK",),
            mode=RunMode.REPLAY,
        )

        assert [candidate.url for candidate in replayed.candidates] == [
            candidate.url for candidate in live.candidates
        ]
        assert replay_provider.calls_made == 0

    def test_explicit_query_text_is_part_of_cassette_identity(self, tmp_path):
        patterns = reviewed_patterns_for_hint(registry(), "Kichler Lighting")
        discover_sources(
            DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
            provider=provider_for([], sites=patterns, pdf_only=True),
            registry=registry(),
            cassettes=CassetteStore(tmp_path),
            queries=("45297BK",),
            mode=RunMode.LIVE,
        )

        with pytest.raises(ReplayMissError):
            discover_sources(
                DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
                provider=AgentSearchProvider(
                    CONFIG,
                    site_patterns=patterns,
                    pdf_only=True,
                    client=_ExplodingClient(),
                ),
                registry=registry(),
                cassettes=CassetteStore(tmp_path),
                queries=("different-query",),
                mode=RunMode.REPLAY,
            )

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
        provider=provider
        or provider_for(results, sites=reviewed_patterns_for_hint(registry(), hint)),
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
            sites=reviewed_patterns_for_hint(registry(), "Kichler Lighting"),
        ),
        registry=registry(),
        cassettes=CassetteStore(tmp_path / "cassettes"),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        mode=RunMode.LIVE,
        transport=transport,
        resolver=lambda host: ["93.184.216.34"],
    )


class TestMultiDomainReplayIdentity:
    """The replay key must be buildable and truthful for a multi-domain provider."""

    def _provider(self, sites, pdf_only=False, results=None):
        return provider_for(results or [], sites=sites, pdf_only=pdf_only)

    def test_request_options_work_for_one_domain(self):
        options = declared_request_options(self._provider(("https://kichler.com/*",)))
        assert options["filters"] == ['siteSearch:"https://kichler.com/*"']

    def test_request_options_work_for_two_domains(self):
        """The case that would break if the singular accessor were used here."""
        options = declared_request_options(
            self._provider(("https://makitatools.com/*", "https://makita.com/*"))
        )
        assert options["filters"] == [
            'siteSearch:"https://makitatools.com/*"',
            'siteSearch:"https://makita.com/*"',
        ]

    def test_request_options_never_call_the_singular_accessor(self):
        """A multi-domain provider raises from filter_expression(); options must not."""
        provider = self._provider(("https://a.com/*", "https://b.com/*"))
        calls: list[int] = []

        def exploding():
            calls.append(1)
            raise AssertionError("request_options used the singular filter accessor")

        provider.filter_expression = exploding  # type: ignore[method-assign]
        assert provider.request_options()["filters"]
        assert calls == []

    def test_a_two_domain_replay_key_is_constructible(self):
        provider = self._provider(("https://makitatools.com/*", "https://makita.com/*"))
        key = search_request(
            "XLC10ZW",
            provider=provider.name,
            max_results=5,
            version=provider.version,
            options=declared_request_options(provider),
        ).cassette_key()
        assert isinstance(key, str) and key

    def test_engine_location_and_serving_config_stay_in_the_identity(self):
        options = declared_request_options(self._provider(("https://a.com/*",)))
        assert options["engine"] == "skutruth-manufacturers"
        assert options["location"] == "global"
        assert options["serving_config"] == "default_search"

    def test_a_different_engine_changes_the_multi_domain_key(self):
        sites = ("https://a.com/*", "https://b.com/*")
        other = AgentSearchProvider(
            AgentSearchConfig(project="test-project", engine_id="another"),
            site_patterns=sites,
            client=FakeSearchClient([]),
        )
        keys = {
            search_request(
                "q", provider=p.name, max_results=5, options=declared_request_options(p)
            ).cassette_key()
            for p in (self._provider(sites), other)
        }
        assert len(keys) == 2

    def test_pdf_only_appears_in_every_physical_filter(self):
        options = declared_request_options(
            self._provider(("https://a.com/*", "https://b.com/*"), pdf_only=True)
        )
        assert options["filters"] == [
            'siteSearch:"https://a.com/*" AND fileType:".pdf"',
            'siteSearch:"https://b.com/*" AND fileType:".pdf"',
        ]
        assert all(f.endswith('fileType:".pdf"') for f in options["filters"])


class TestDomainOrderIsSemantic:
    """Order decides merged ordering and which results survive the cap, so it is keyed."""

    def test_reversed_domain_order_is_a_different_recording(self):
        forward = provider_for([], sites=("https://a.com/*", "https://b.com/*"))
        reverse = provider_for([], sites=("https://b.com/*", "https://a.com/*"))
        keys = {
            search_request(
                "q", provider=p.name, max_results=5, options=declared_request_options(p)
            ).cassette_key()
            for p in (forward, reverse)
        }
        assert len(keys) == 2, "domain order changes results but not the key"

    def test_order_is_preserved_rather_than_normalised(self):
        """Normalising the key alone would key two genuinely different runs the same."""
        reverse = provider_for([], sites=("https://b.com/*", "https://a.com/*"))
        assert declared_request_options(reverse)["filters"] == [
            'siteSearch:"https://b.com/*"',
            'siteSearch:"https://a.com/*"',
        ]

    def test_execution_order_matches_the_keyed_order(self):
        provider = provider_for([], sites=("https://b.com/*", "https://a.com/*"))
        provider.search(SearchCall(query="q", max_results=5))
        issued = [r.filter for r, _ in provider._client.requests]
        assert issued == declared_request_options(provider)["filters"]


class TestMultiDomainThroughReplay:
    """The whole public path: LIVE records, REPLAY serves, no provider call."""

    def _client_factory(self):
        class TwoDomainClient:
            def __init__(self):
                self.requests = []

            def search(self, request=None, timeout=None):
                self.requests.append((request, timeout))
                host = (
                    "makitatools.com" if "makitatools" in request.filter else "makita.com"
                )
                return FakeResponse(
                    [
                        result_for(f"https://{host}/XLC10ZW.pdf", "XLC10ZW"),
                        result_for(f"https://{host}/XLC10ZW-manual.pdf", "XLC10ZW manual"),
                    ]
                )

        return TwoDomainClient()

    def _provider(self, client):
        return AgentSearchProvider(
            CONFIG,
            site_patterns=("https://makitatools.com/*", "https://makita.com/*"),
            client=client,
        )

    def test_live_records_and_replay_serves_the_merged_result(self, tmp_path):
        store = CassetteStore(tmp_path)
        live_client = self._client_factory()
        live = execute_search(
            SearchCall(query="XLC10ZW", max_results=10),
            provider=self._provider(live_client),
            store=store,
            mode=RunMode.LIVE,
        )
        assert len(live_client.requests) == 2, "expected one physical request per domain"
        assert len(live) == 4

        replayed = execute_search(
            SearchCall(query="XLC10ZW", max_results=10),
            provider=self._provider(_ExplodingClient()),
            store=store,
            mode=RunMode.REPLAY,
        )
        assert [r.url for r in replayed] == [r.url for r in live]

    def test_replay_makes_zero_physical_calls(self, tmp_path):
        store = CassetteStore(tmp_path)
        execute_search(
            SearchCall(query="XLC10ZW", max_results=10),
            provider=self._provider(self._client_factory()),
            store=store,
            mode=RunMode.LIVE,
        )
        provider = self._provider(_ExplodingClient())
        execute_search(
            SearchCall(query="XLC10ZW", max_results=10),
            provider=provider,
            store=store,
            mode=RunMode.REPLAY,
        )
        assert provider.calls_made == 0

    def test_a_multi_domain_replay_miss_fails_closed(self, tmp_path):
        with pytest.raises(ReplayMissError):
            execute_search(
                SearchCall(query="never recorded", max_results=10),
                provider=self._provider(_ExplodingClient()),
                store=CassetteStore(tmp_path),
                mode=RunMode.REPLAY,
            )


class TestMaxResultsIsALogicalTotal:
    """`SearchCall.max_results` caps the call, not each physical request."""

    def _provider(self, per_domain=3, sites=("https://a.com/*", "https://b.com/*")):
        class PerDomainClient:
            def __init__(self):
                self.requests = []

            def search(self, request=None, timeout=None):
                self.requests.append((request, timeout))
                host = "a.com" if "a.com" in request.filter else "b.com"
                return FakeResponse(
                    [result_for(f"https://{host}/{i}-X.pdf") for i in range(per_domain)]
                )

        return AgentSearchProvider(CONFIG, site_patterns=sites, client=PerDomainClient())

    def test_two_domains_do_not_return_twice_the_requested_cap(self):
        provider = self._provider()
        rows = provider.search(SearchCall(query="X", max_results=4))
        assert len(rows) == 4, "6 results across two domains must be capped at 4"

    def test_the_cap_applies_after_deduplication(self):
        """A document both domains return must not consume two of the caller's slots."""
        shared = result_for("https://shared.example/X.pdf")

        class DuplicateClient:
            requests: list = []

            def search(self, request=None, timeout=None):
                self.requests.append((request, timeout))
                return FakeResponse([shared, result_for("https://other.example/X.pdf")])

        provider = AgentSearchProvider(
            CONFIG,
            site_patterns=("https://a.com/*", "https://b.com/*"),
            client=DuplicateClient(),
        )
        rows = provider.search(SearchCall(query="X", max_results=4))
        assert [r["url"] for r in rows] == [
            "https://shared.example/X.pdf",
            "https://other.example/X.pdf",
        ]

    def test_the_cap_keeps_the_deterministic_merged_prefix(self):
        provider = self._provider()
        rows = provider.search(SearchCall(query="X", max_results=4))
        assert [r["url"] for r in rows] == [
            "https://a.com/0-X.pdf",
            "https://a.com/1-X.pdf",
            "https://a.com/2-X.pdf",
            "https://b.com/0-X.pdf",
        ]

    def test_every_domain_is_still_queried_even_once_the_cap_is_full(self):
        """Stopping early would make the second domain invisible when the first is busy."""
        provider = self._provider(per_domain=10)
        provider.search(SearchCall(query="X", max_results=2))
        assert len(provider._client.requests) == 2

    def test_physical_calls_are_still_counted_against_max_calls(self):
        provider = self._provider()
        provider.search(SearchCall(query="X", max_results=1))
        assert provider.calls_made == 2

    def test_a_single_domain_provider_is_unaffected(self):
        provider = self._provider(sites=("https://a.com/*",))
        assert len(provider.search(SearchCall(query="X", max_results=10))) == 3

    def test_the_provider_limit_still_applies(self):
        provider = AgentSearchProvider(
            CONFIG,
            limits=AgentSearchLimits(max_results_per_query=2),
            site_patterns=("https://a.com/*",),
            client=FakeSearchClient(
                [result_for(f"https://a.com/{i}.pdf") for i in range(5)]
            ),
        )
        assert len(provider.search(SearchCall(query="X", max_results=10))) == 2
