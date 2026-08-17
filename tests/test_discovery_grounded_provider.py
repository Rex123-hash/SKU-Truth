"""Vertex Google Search grounding as a locator source, exercised entirely offline.

The Gemini client is a fake object shaped like the real response; `google.genai.types` is
imported for real, so the request this provider builds is the one the SDK accepts. No
socket is opened and no credential is read.

Two properties carry the most weight here, because getting either wrong would put model
output into the evidence chain:

* the generated answer is discarded — `response.text`, grounding-support prose, and search
  suggestion HTML must never reach a `SearchResult` or an artifact;
* a provider-reported publisher domain buys a *fetch attempt* and nothing more. The host
  the bytes actually arrive from is what decides whether anything may be stored.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field

import httpx
import pytest
from conftest_pdf import build_pdf
from skutruth.contracts import DiscoveryMethod, RunMode
from skutruth.discovery import (
    DiscoveryRequest,
    SearchCall,
    SearchProviderTimeout,
    SearchProviderTransportError,
    discover_sources,
    execute_search_with_provenance,
)
from skutruth.discovery.domains import parse_registry
from skutruth.discovery.errors import MalformedSearchResponseError, SearchBudgetExceededError
from skutruth.discovery.grounded_search import (
    PROVIDER_NAME,
    GroundingConfig,
    GroundingLimits,
    VertexGroundedSearchProvider,
    extract_locators,
    search_entry_point_of,
)
from skutruth.discovery.models import SourceAuthority
from skutruth.discovery.policy import candidate_host, host_of
from skutruth.ingest.storage import ArtifactStore
from skutruth.replay.errors import ReplayMissError
from skutruth.replay.store import CassetteStore

REDIRECT = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/AbC123xyz"
REDIRECT_2 = "https://vertexaisearch.cloud.google.com/grounding-api-redirect/Def456uvw"

#: Prose the model generated. If any of this ever appears downstream, a test fails.
GENERATED_ANSWER = (
    "The Kichler 45297BK is a 3-light chandelier rated for 60 W bulbs with a "
    "black finish and a 12 inch diameter."
)
SUPPORT_PROSE = "rated for 60 W bulbs"
SUGGESTIONS_HTML = '<div class="container"><a href="https://google.com/search?q=x">45297BK</a></div>'

REGISTRY_TOML = """
name = "grounding-registry"
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


def registry():
    return parse_registry(tomllib.loads(REGISTRY_TOML), source="grounding-registry")


# -- a fake shaped like the real grounding response ---------------------------


@dataclass
class FakeWeb:
    uri: str
    title: str = ""
    domain: str | None = None


@dataclass
class FakeChunk:
    web: FakeWeb | None


@dataclass
class FakeEntryPoint:
    rendered_content: str = ""


@dataclass
class FakeGroundingMetadata:
    grounding_chunks: list[FakeChunk] = field(default_factory=list)
    web_search_queries: list[str] = field(default_factory=list)
    search_entry_point: FakeEntryPoint | None = None
    grounding_supports: list[str] = field(default_factory=list)


@dataclass
class FakeCandidate:
    grounding_metadata: FakeGroundingMetadata | None


class FakeResponse:
    def __init__(self, metadata, text=GENERATED_ANSWER):
        self.candidates = [FakeCandidate(metadata)]
        self._text = text

    @property
    def text(self):
        # If the provider ever reads the generated answer, this records it.
        FakeResponse.text_was_read = True
        return self._text


class FakeModels:
    def __init__(self, response, error=None):
        self._response = response
        self._error = error
        self.calls: list[dict] = []

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._response


class FakeClient:
    def __init__(self, response=None, error=None):
        self.models = FakeModels(response, error)


def metadata_for(
    chunks=(("https://kichler.com/p/45297BK.pdf", "45297BK datasheet", "kichler.com"),),
    *,
    queries=("kichler 45297BK datasheet",),
    suggestions=SUGGESTIONS_HTML,
    redirect=True,
):
    """Grounding metadata with redirect URIs and separate publisher domains."""
    return FakeGroundingMetadata(
        grounding_chunks=[
            FakeChunk(
                FakeWeb(
                    uri=(REDIRECT if redirect and i == 0 else REDIRECT_2 if redirect else url),
                    title=title,
                    domain=domain,
                )
            )
            for i, (url, title, domain) in enumerate(chunks)
        ],
        web_search_queries=list(queries),
        search_entry_point=FakeEntryPoint(suggestions),
        grounding_supports=[SUPPORT_PROSE],
    )


def provider_for(metadata, *, limits=None, error=None):
    response = None if error else FakeResponse(metadata)
    return VertexGroundedSearchProvider(
        GroundingConfig(project="test-project", location="us-central1", model="gemini-2.5-flash"),
        limits=limits or GroundingLimits(),
        client=FakeClient(response, error),
    )


@pytest.fixture(autouse=True)
def _reset_text_probe():
    FakeResponse.text_was_read = False
    yield


# -- A, B, C: publisher_host vs the redirect URI ------------------------------


class TestPublisherHost:
    def test_web_domain_becomes_publisher_host(self):
        """A."""
        rows, _ = extract_locators(metadata_for(), limit=10)
        assert rows[0]["publisher_host"] == "kichler.com"

    def test_the_grounding_uri_remains_the_result_url(self):
        """B. The URL is what the provider returned, unmodified."""
        rows, _ = extract_locators(metadata_for(), limit=10)
        assert rows[0]["url"] == REDIRECT

    def test_the_google_redirect_host_does_not_erase_publisher_host(self, tmp_path):
        """C. Both hosts survive onto the candidate."""
        result = run_discovery(metadata_for(), tmp_path=tmp_path)
        candidate = result.candidates[0]
        assert candidate.result.publisher_host == "kichler.com"
        assert candidate.host == "kichler.com"
        assert candidate.locator_host == "vertexaisearch.cloud.google.com"
        assert host_of(candidate.url) == "vertexaisearch.cloud.google.com"

    def test_candidate_host_prefers_the_publisher_and_falls_back_to_the_url(self):
        from skutruth.discovery.models import SearchResult

        grounded = SearchResult(
            url=REDIRECT, rank=1, query="q", provider="p", publisher_host="kichler.com"
        )
        plain = SearchResult(url="https://kichler.com/x", rank=1, query="q", provider="p")
        assert candidate_host(grounded) == "kichler.com"
        assert candidate_host(plain) == "kichler.com"

    def test_publisher_host_makes_a_candidate_fetch_eligible(self, tmp_path):
        """D. Without it the redirect host would be UNKNOWN and nothing would be tried."""
        result = run_discovery(metadata_for(), tmp_path=tmp_path)
        candidate = result.candidates[0]
        assert candidate.authority is SourceAuthority.APPROVED_MANUFACTURER
        assert candidate.is_eligible

    def test_a_chunk_without_a_domain_is_handled_conservatively(self, tmp_path):
        """R. No domain means the redirect host is all we have, and that is UNKNOWN."""
        metadata = metadata_for(
            chunks=(("https://kichler.com/p/45297BK.pdf", "45297BK", None),)
        )
        result = run_discovery(metadata, tmp_path=tmp_path)
        candidate = result.candidates[0]
        assert candidate.result.publisher_host is None
        assert candidate.authority is SourceAuthority.UNKNOWN
        assert not candidate.is_eligible

    def test_a_chunk_with_no_uri_is_skipped_not_invented(self):
        metadata = FakeGroundingMetadata(
            grounding_chunks=[FakeChunk(FakeWeb(uri="", domain="kichler.com")), FakeChunk(None)]
        )
        rows, _ = extract_locators(metadata, limit=10)
        assert rows == []

    def test_publisher_host_is_locator_metadata_not_a_licence(self, tmp_path):
        """E. A reported domain alone stores nothing when the entry is unreviewed."""
        metadata = metadata_for(
            chunks=(("https://se.com/LC1D18P7.pdf", "LC1D18P7", "se.com"),)
        )
        result = run_discovery(
            metadata, mpn="LC1D18P7", hint="Schneider Electric", tmp_path=tmp_path
        )
        candidate = result.candidates[0]
        assert candidate.result.publisher_host == "se.com"
        assert candidate.authority is SourceAuthority.UNVERIFIED_MANUFACTURER
        assert not candidate.may_store_as_manufacturer_evidence

    def test_a_claimed_domain_for_the_wrong_manufacturer_is_refused(self):
        """A provider cannot promote a host by naming a manufacturer it does not serve."""
        from skutruth.discovery.models import SearchResult
        from skutruth.discovery.policy import classify_authority

        result = SearchResult(
            url=REDIRECT, rank=1, query="q", provider="p", publisher_host="se.com"
        )
        authority = classify_authority(
            candidate_host(result), registry=registry(), manufacturer_hint="Kichler Lighting"
        )
        assert authority is SourceAuthority.OTHER_MANUFACTURER


# -- F, G: the final host is what governs storage ------------------------------


def acquiring_run(final_host: str, *, body=None, tmp_path, publisher="kichler.com"):
    """Fetch a grounded candidate whose redirect lands on `final_host`."""
    document = body if body is not None else build_pdf(["45297BK spec"])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "vertexaisearch.cloud.google.com":
            return httpx.Response(302, headers={"location": f"https://{final_host}/doc.pdf"})
        return httpx.Response(
            200, content=document, headers={"content-type": "application/pdf"}
        )

    transport = httpx.MockTransport(handler)
    metadata = metadata_for(chunks=(("ignored", "45297BK datasheet", publisher),))
    return discover_sources(
        DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
        provider=provider_for(metadata),
        registry=registry(),
        cassettes=CassetteStore(tmp_path / "cassettes"),
        artifacts=ArtifactStore(tmp_path / "artifacts"),
        mode=RunMode.LIVE,
        transport=transport,
        resolver=lambda host: ["93.184.216.34"],
    )


class TestFinalHostAuthorityGoverns:
    def test_a_redirect_to_the_manufacturer_retains_authority_and_ingests(self, tmp_path):
        """F. The permitted path: Google's redirect lands on the reviewed domain."""
        result = acquiring_run("kichler.com", tmp_path=tmp_path)
        candidate = result.candidates[0]
        assert candidate.final_authority is SourceAuthority.APPROVED_MANUFACTURER
        assert candidate.may_store_as_manufacturer_evidence
        assert result.acquired and candidate.artifact_sha256

    def test_a_redirect_to_a_third_party_is_refused(self, tmp_path):
        """G. Google says kichler.com; the bytes come from somewhere else."""
        result = acquiring_run("random-third-party.example", tmp_path=tmp_path)
        candidate = result.candidates[0]
        assert candidate.result.publisher_host == "kichler.com"
        assert candidate.final_authority is not SourceAuthority.APPROVED_MANUFACTURER
        assert not candidate.may_store_as_manufacturer_evidence
        assert "REDIRECT_AUTHORITY_LOST" in candidate.rejections
        assert not result.acquired

    def test_a_redirect_to_a_distributor_is_refused(self, tmp_path):
        result = acquiring_run("grainger.com", tmp_path=tmp_path)
        assert not result.acquired
        assert not result.candidates[0].may_store_as_manufacturer_evidence

    def test_the_reported_domain_never_overrides_the_final_host(self, tmp_path):
        """The whole point: a provider claim cannot outrank observed bytes."""
        good = acquiring_run("kichler.com", tmp_path=tmp_path / "a")
        bad = acquiring_run("elsewhere.example", tmp_path=tmp_path / "b")
        assert good.candidates[0].result.publisher_host == "kichler.com"
        assert bad.candidates[0].result.publisher_host == "kichler.com"
        assert bool(good.acquired) and not bad.acquired


# -- H, I, J, U: model output is discarded -------------------------------------


class TestGeneratedTextIsDiscarded:
    def test_the_generated_answer_never_becomes_a_search_result(self, tmp_path):
        """H."""
        result = run_discovery(metadata_for(), tmp_path=tmp_path)
        serialized = result.model_dump_json()
        assert GENERATED_ANSWER not in serialized
        for candidate in result.candidates:
            assert candidate.result.snippet == ""
            assert GENERATED_ANSWER not in candidate.result.title

    def test_the_provider_does_not_even_read_response_text(self):
        """The safest form of "discarded": never touched at all."""
        provider_for(metadata_for()).search(SearchCall(query="q", max_results=5))
        assert FakeResponse.text_was_read is False

    def test_grounding_support_prose_never_becomes_evidence(self, tmp_path):
        """J."""
        result = run_discovery(metadata_for(), tmp_path=tmp_path)
        assert SUPPORT_PROSE not in result.model_dump_json()

    def test_search_suggestion_html_never_reaches_a_candidate(self, tmp_path):
        """U."""
        result = run_discovery(metadata_for(), tmp_path=tmp_path)
        assert SUGGESTIONS_HTML not in result.model_dump_json()
        assert "<div" not in result.model_dump_json()

    def test_generated_text_never_reaches_the_artifact_store(self, tmp_path):
        """I. Grep every stored byte."""
        result = acquiring_run("kichler.com", tmp_path=tmp_path)
        assert result.acquired
        for path in (tmp_path / "artifacts").rglob("*"):
            if path.is_file():
                blob = path.read_bytes()
                assert GENERATED_ANSWER.encode() not in blob
                assert SUGGESTIONS_HTML.encode() not in blob

    def test_suggestions_are_retained_on_the_provider_for_a_future_ui(self):
        """Captured for the display obligation, kept out of the domain layer."""
        provider = provider_for(metadata_for())
        provider.search(SearchCall(query="q", max_results=5))
        assert provider.last_search_entry_point == SUGGESTIONS_HTML

    def test_search_entry_point_reads_rendered_content(self):
        assert search_entry_point_of(metadata_for()) == SUGGESTIONS_HTML
        assert search_entry_point_of(FakeGroundingMetadata()) == ""


# -- K, L, M, N: requested vs executed queries ---------------------------------


class TestQueryProvenance:
    def test_web_search_queries_are_retained_as_provider_queries(self, tmp_path):
        """K."""
        metadata = metadata_for(queries=("kichler 45297BK spec", "45297BK datasheet pdf"))
        result = run_discovery(metadata, tmp_path=tmp_path)
        assert result.provider_executed_queries == (
            "kichler 45297BK spec",
            "45297BK datasheet pdf",
        )

    def test_requested_queries_stay_separate_and_deterministic(self, tmp_path):
        """L."""
        result = run_discovery(metadata_for(), tmp_path=tmp_path)
        assert result.requested_queries == (
            '"45297BK" site:kichler.com',
            '"45297BK" Kichler Lighting',
            '"45297BK" datasheet',
        )
        assert result.requested_queries == result.executed_queries

    def test_requested_and_provider_queries_may_differ(self, tmp_path):
        """M. The honest case: Google searched something we did not ask for."""
        metadata = metadata_for(queries=("kichler chandelier black 3 light",))
        result = run_discovery(metadata, tmp_path=tmp_path)
        assert result.provider_executed_queries == ("kichler chandelier black 3 light",)
        assert result.provider_executed_queries != result.requested_queries
        assert result.search_execution_was_provider_generated

    def test_a_provider_that_runs_our_query_reports_nothing_separate(self, tmp_path):
        metadata = metadata_for(queries=())
        result = run_discovery(metadata, tmp_path=tmp_path)
        assert result.provider_executed_queries == ()
        assert not result.search_execution_was_provider_generated

    def test_replay_reproduces_both_query_sets(self, tmp_path):
        """N."""
        metadata = metadata_for(queries=("google chose this",))
        live = run_discovery(metadata, tmp_path=tmp_path, mode=RunMode.LIVE)
        replayed = run_discovery(
            metadata, tmp_path=tmp_path, mode=RunMode.REPLAY, provider=exploding_provider()
        )
        assert replayed.requested_queries == live.requested_queries
        assert replayed.provider_executed_queries == live.provider_executed_queries
        assert replayed.provider_executed_queries == ("google chose this",)

    def test_provider_queries_are_deduplicated_across_our_queries(self, tmp_path):
        """Three intents, one repeated Google query, recorded once."""
        result = run_discovery(metadata_for(queries=("same",)), tmp_path=tmp_path)
        assert result.provider_executed_queries == ("same",)


# -- O: replay makes no provider call ------------------------------------------


def exploding_provider():
    class Exploding(VertexGroundedSearchProvider):
        def search(self, call):  # pragma: no cover - must never run
            raise AssertionError("REPLAY called the provider")

    return Exploding(
        GroundingConfig(project="test-project", location="us-central1", model="gemini-2.5-flash"),
        client=FakeClient(FakeResponse(metadata_for())),
    )


class TestReplay:
    def test_replay_performs_zero_provider_calls(self, tmp_path):
        """O."""
        run_discovery(metadata_for(), tmp_path=tmp_path, mode=RunMode.LIVE)
        replayed = run_discovery(
            metadata_for(), tmp_path=tmp_path, mode=RunMode.REPLAY, provider=exploding_provider()
        )
        assert replayed.candidates

    def test_a_replay_miss_fails_closed(self, tmp_path):
        with pytest.raises(ReplayMissError):
            execute_search_with_provenance(
                SearchCall(query="never recorded", max_results=5),
                provider=exploding_provider(),
                store=CassetteStore(tmp_path),
                mode=RunMode.REPLAY,
            )

    def test_the_model_is_part_of_the_replay_key(self, tmp_path):
        """A recording made by one model must not replay as another's."""
        from skutruth.discovery.provider import declared_request_options, search_request

        a = provider_for(metadata_for())
        b = VertexGroundedSearchProvider(
            GroundingConfig(project="p", location="us-central1", model="gemini-3-pro"),
            client=FakeClient(FakeResponse(metadata_for())),
        )
        key_a = search_request(
            "q", provider=a.name, max_results=5, options=declared_request_options(a)
        ).cassette_key()
        key_b = search_request(
            "q", provider=b.name, max_results=5, options=declared_request_options(b)
        ).cassette_key()
        assert key_a != key_b


# -- P, Q: provenance declaration ----------------------------------------------


class TestProvenance:
    def test_the_provider_declares_google_search_grounding(self):
        """P."""
        assert (
            provider_for(metadata_for()).discovery_method
            is DiscoveryMethod.GOOGLE_SEARCH_GROUNDING
        )

    def test_a_name_cannot_mint_the_enum(self):
        """Q. Provenance comes from the implementation, never from branding."""
        from skutruth.discovery.provider import declared_discovery_method

        class PretendGoogle:
            name = "google-search-grounding"
            discovery_method = None

            def search(self, call):
                return []

        assert declared_discovery_method(PretendGoogle()) is None

    def test_the_declaration_reaches_stored_provenance(self, tmp_path):
        result = acquiring_run("kichler.com", tmp_path=tmp_path)
        store = ArtifactStore(tmp_path / "artifacts")
        stored = store.load(result.acquired[0].artifact_sha256)
        assert stored.source.discovery_method is DiscoveryMethod.GOOGLE_SEARCH_GROUNDING


# -- S, T: deduplication -------------------------------------------------------


class TestDeduplication:
    def test_duplicate_chunks_dedupe_deterministically(self):
        """S. Google frequently cites one source several times."""
        metadata = FakeGroundingMetadata(
            grounding_chunks=[
                FakeChunk(FakeWeb(uri=REDIRECT, domain="kichler.com")),
                FakeChunk(FakeWeb(uri=REDIRECT, domain="kichler.com")),
                FakeChunk(FakeWeb(uri=REDIRECT_2, domain="kichler.com")),
            ]
        )
        rows, _ = extract_locators(metadata, limit=10)
        assert [r["url"] for r in rows] == [REDIRECT, REDIRECT_2]

    def test_two_documents_on_one_domain_are_two_candidates(self, tmp_path):
        """T. Deduplication is by URL, never by host."""
        metadata = FakeGroundingMetadata(
            grounding_chunks=[
                FakeChunk(FakeWeb(uri=REDIRECT, title="45297BK datasheet", domain="kichler.com")),
                FakeChunk(
                    FakeWeb(uri=REDIRECT_2, title="45297BK manual", domain="kichler.com")
                ),
            ]
        )
        result = run_discovery(metadata, tmp_path=tmp_path)
        assert len(result.candidates) == 2
        assert {c.host for c in result.candidates} == {"kichler.com"}

    def test_the_result_cap_is_honoured(self):
        metadata = FakeGroundingMetadata(
            grounding_chunks=[
                FakeChunk(FakeWeb(uri=f"https://x.example/{i}", domain="kichler.com"))
                for i in range(20)
            ]
        )
        rows, _ = extract_locators(metadata, limit=3)
        assert len(rows) == 3


# -- request construction and typed failures -----------------------------------


class TestRequestAndFailures:
    def test_the_request_enables_google_search_and_names_the_model(self):
        provider = provider_for(metadata_for())
        provider.search(SearchCall(query='"45297BK" site:kichler.com', max_results=5))
        call = provider._client.models.calls[0]
        assert call["model"] == "gemini-2.5-flash"
        assert call["config"].tools[0].google_search is not None
        assert '"45297BK" site:kichler.com' in call["contents"]

    def test_the_deterministic_query_is_visible_in_the_prompt(self):
        provider = provider_for(metadata_for())
        provider.search(SearchCall(query='"LC1D18P7" datasheet', max_results=5))
        assert '"LC1D18P7" datasheet' in provider._client.models.calls[0]["contents"]

    def test_an_empty_query_is_refused_before_a_call(self):
        provider = provider_for(metadata_for())
        with pytest.raises(MalformedSearchResponseError):
            provider.search(SearchCall(query="  "))
        assert provider.calls_made == 0

    def test_absent_grounding_metadata_is_an_empty_result_not_an_error(self):
        provider = provider_for(None)
        assert provider.search(SearchCall(query="q", max_results=5)) == []

    def test_a_timeout_is_typed(self):
        provider = provider_for(None, error=TimeoutError("deadline"))
        with pytest.raises(SearchProviderTimeout):
            provider.search(SearchCall(query="q"))

    def test_an_sdk_failure_is_typed_and_does_not_echo_its_text(self):
        provider = provider_for(None, error=RuntimeError("https://secret-endpoint?key=abc123"))
        with pytest.raises(SearchProviderTransportError) as exc:
            provider.search(SearchCall(query="q"))
        assert "abc123" not in str(exc.value)
        assert exc.value.__cause__ is None

    def test_the_call_budget_is_enforced(self):
        provider = provider_for(metadata_for(), limits=GroundingLimits(max_calls=1))
        provider.search(SearchCall(query="a"))
        with pytest.raises(SearchBudgetExceededError):
            provider.search(SearchCall(query="b"))

    def test_a_failed_call_still_counts_against_the_budget(self):
        provider = provider_for(
            None, error=RuntimeError("boom"), limits=GroundingLimits(max_calls=1)
        )
        with pytest.raises(SearchProviderTransportError):
            provider.search(SearchCall(query="a"))
        with pytest.raises(SearchBudgetExceededError):
            provider.search(SearchCall(query="b"))

    def test_limits_must_be_positive(self):
        with pytest.raises(ValueError):
            GroundingLimits(max_calls=0)

    def test_the_provider_name_is_recorded_on_results(self, tmp_path):
        result = run_discovery(metadata_for(), tmp_path=tmp_path)
        assert result.provider == PROVIDER_NAME
        assert result.candidates[0].result.provider == PROVIDER_NAME


# -- V, W: nothing here writes a review ----------------------------------------


class TestReviewsAreNotWritten:
    def test_running_discovery_writes_no_review(self, tmp_path):
        """V."""
        before = registry()
        run_discovery(metadata_for(), tmp_path=tmp_path)
        after = registry()
        assert [e.key for e in before.licensing_entries] == [
            e.key for e in after.licensing_entries
        ]

    def test_the_shipped_registry_still_licenses_nothing(self, tmp_path):
        """W. Grounding discovering a domain does not review it."""
        from pathlib import Path

        from skutruth.discovery import load_registry

        shipped = Path(__file__).resolve().parents[1] / "data" / "discovery"
        live = load_registry(shipped / "manufacturer_domains.demo.toml")
        assert live.licensing_entries == ()

        metadata = metadata_for(
            chunks=(("https://kichler.com/p/45297BK.pdf", "45297BK", "kichler.com"),)
        )
        result = discover_sources(
            DiscoveryRequest(mpn="45297BK", manufacturer_hint="Kichler Lighting"),
            provider=provider_for(metadata),
            registry=live,
            cassettes=CassetteStore(tmp_path),
            mode=RunMode.LIVE,
        )
        assert not any(c.may_store_as_manufacturer_evidence for c in result.candidates)
        assert load_registry(shipped / "manufacturer_domains.demo.toml").licensing_entries == ()


# -- the dead Custom Search adapter is gone ------------------------------------


class TestCustomSearchIsGone:
    def test_no_production_module_references_the_custom_search_adapter(self):
        """The API is closed to new customers; live code must not imply otherwise."""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[1]
        targets = [*(root / "backend").rglob("*.py"), *(root / "scripts").glob("*.py")]
        for path in targets:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module:
                    assert "programmable_search" not in node.module, path
                elif isinstance(node, ast.Import):
                    assert not any("programmable_search" in a.name for a in node.names), path

    def test_the_adapter_module_no_longer_exists(self):
        from pathlib import Path

        module = (
            Path(__file__).resolve().parents[1]
            / "backend"
            / "skutruth"
            / "discovery"
            / "programmable_search.py"
        )
        assert not module.exists()

    def test_the_package_exports_no_custom_search_names(self):
        import skutruth.discovery as discovery

        banned = {
            "ProgrammableSearchProvider",
            "SearchCredentials",
            "API_KEY_ENV",
            "ENGINE_ID_ENV",
        }
        assert not banned & set(discovery.__all__)
        assert not banned & set(dir(discovery))


# -- shared driver --------------------------------------------------------------


def run_discovery(
    metadata,
    *,
    mpn="45297BK",
    hint="Kichler Lighting",
    tmp_path,
    mode=RunMode.LIVE,
    provider=None,
):
    return discover_sources(
        DiscoveryRequest(mpn=mpn, manufacturer_hint=hint),
        provider=provider or provider_for(metadata),
        registry=registry(),
        cassettes=CassetteStore(tmp_path),
        mode=mode,
    )
