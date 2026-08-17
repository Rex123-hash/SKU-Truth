"""Discovery end to end, with a fake provider and a fake network.

    RawProductRow  →  DiscoveryRequest  →  fake search  →  policy  →  ranking
                                                                        ↓
                              ArtifactStore  ←  safe fetch  ←  eligible candidate

The run deliberately contains a marketplace listing, a distributor page, a sibling part,
and a family stem alongside the real manufacturer datasheet. Proving the datasheet is
found is half the test; proving the other four are not acquired is the half that matters.

No network, no model, no organizer file. The search provider is a fake and the HTTP
transport is a mock.
"""

from __future__ import annotations

import socket

import httpx
import pytest
from conftest_pdf import build_pdf
from skutruth.contracts import DiscoveryMethod, RunMode, SourceType
from skutruth.discovery import (
    CandidateStatus,
    DiscoveryRequest,
    MpnRelevance,
    SearchCall,
    SourceAuthority,
    SourceKind,
    classify_authority,
    discover_sources,
    parse_registry,
)
from skutruth.discovery.errors import RejectionReason
from skutruth.discovery.service import DiscoveryBudget
from skutruth.ingest.storage import ArtifactStore
from skutruth.replay.errors import ReplayMissError
from skutruth.replay.store import CassetteStore
from skutruth.unilog.input import RawProductRow

MPN = "LC1D18P7"
MAKER = "Schneider Electric"
DATASHEET_URL = f"https://download.se.com/files/{MPN}_datasheet.pdf"
PDF_BYTES = build_pdf(["TESYS LC1D18P7", "18 A AC-3 440 V"])
PUBLIC_IP = "93.184.216.34"

#: What a search engine returns: one real source and four convincing distractions.
RESULTS = [
    {"url": f"https://amazon.com/dp/{MPN}", "title": f"{MPN} Contactor - Amazon", "rank": 1},
    {"url": f"https://grainger.com/p/{MPN}", "title": f"Schneider {MPN}", "rank": 2},
    {"url": DATASHEET_URL, "title": f"{MPN} product datasheet", "rank": 3},
    {"url": "https://se.com/p/LC1D18B7/", "title": "LC1D18B7 contactor", "rank": 4},
    {"url": "https://se.com/range/LC1D18/", "title": "TeSys LC1D18 range", "rank": 5},
]


#: A complete audit record. Entries without one are locator-grade by design.
REVIEW = {
    "reviewed_at": "2026-08-17",
    "reviewed_by": "test",
    "basis": "synthetic fixture; no real domain was checked",
}


class FakeSearchProvider:
    """A provider that returns fixed results and counts how often it was asked.

    `CURATED_CORPUS` is the truthful `DiscoveryMethod` here: results come from a fixed
    local set, which is exactly what that value means. It is not a stand-in for "search".
    """

    name = "fake"
    discovery_method = DiscoveryMethod.CURATED_CORPUS

    def __init__(self, results=None, *, api_key: str = "secret-key-never-stored") -> None:
        self._results = results if results is not None else RESULTS
        self.api_key = api_key
        self.calls: list[str] = []

    def search(self, call: SearchCall) -> list[dict]:
        self.calls.append(call.query)
        return list(self._results)


def registry():
    return parse_registry(
        {
            "name": "test",
            "authority": "REVIEWED",
            "manufacturer": [
                {
                    "key": "schneider",
                    "authority_hints": [MAKER, "Schneider"],
                    "domains": ["se.com", "schneider-electric.com"],
                    "review": REVIEW,
                },
                {
                    "key": "acme",
                    "authority_hints": ["Acme Corp"],
                    "domains": ["acme.example"],
                    "review": REVIEW,
                },
            ],
            "hosts": {
                "marketplaces": ["amazon.com"],
                "distributors": ["grainger.com"],
                "blocked": ["alldatasheet.com"],
            },
        }
    )


def resolver(host: str) -> list[str]:
    return [PUBLIC_IP]


def transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        if str(request.url).endswith(".pdf"):
            return httpx.Response(
                200, content=PDF_BYTES, headers={"content-type": "application/pdf"}
            )
        return httpx.Response(
            200, content=b"<html>page</html>", headers={"content-type": "text/html"}
        )

    return httpx.MockTransport(handler)


def raw_row() -> RawProductRow:
    return RawProductRow(
        row_number=1,
        raw={
            "Mfg_Part_Num": MPN,
            "Part_Desc": "TESYS CONTACTOR 18A 3P",
            "E1_Brand": "-- Unbranded --",
            "Unilog_Brand": "-- No Unilog Brand --",
            "DIB_Brand": "",
            "Part_Manuf": "Schneider Electric (SCHNE)",
        },
    )


def request_from(row: RawProductRow) -> DiscoveryRequest:
    """The adapter a batch stage would use. Hints only, nothing canonical."""
    manufacturer = row.manufacturer
    return DiscoveryRequest(
        mpn=row.mfg_part_num or "",
        raw_mpn=row.raw_value("Mfg_Part_Num"),
        manufacturer_hint=manufacturer.display_name,
        manufacturer_code=manufacturer.supplier_code,
        brand_signals=row.brand_signals,
        description=row.part_desc,
        row_number=row.row_number,
    )


@pytest.fixture
def stores(tmp_path):
    return (
        CassetteStore(tmp_path / "cassettes", writable=True),
        ArtifactStore(tmp_path / "artifacts", writable=True),
    )


def run(stores, *, mode=RunMode.LIVE, provider=None, results=None, budget=None):
    cassettes, artifacts = stores
    return discover_sources(
        request_from(raw_row()),
        provider=provider or FakeSearchProvider(results),
        registry=registry(),
        cassettes=cassettes,
        artifacts=artifacts,
        mode=mode,
        budget=budget or DiscoveryBudget(),
        transport=transport(),
        resolver=resolver,
    )


class TestTheWholePath:
    def test_the_manufacturer_datasheet_is_found_and_ingested(self, stores):
        result = run(stores)
        acquired = result.acquired
        assert len(acquired) == 1
        assert acquired[0].url == DATASHEET_URL
        assert acquired[0].authority is SourceAuthority.APPROVED_MANUFACTURER
        assert acquired[0].relevance is MpnRelevance.EXACT

    def test_the_artifact_lands_in_the_existing_store(self, stores):
        """The seam: no second artifact model, no second parsing path."""
        _, artifacts = stores
        result = run(stores)
        sha = result.acquired[0].artifact_sha256
        stored = artifacts.load(sha, verify_original=True)
        assert stored.sha256 == sha
        assert stored.page_count == 2
        assert artifacts.load_original_bytes(sha) == PDF_BYTES

    def test_discovery_lineage_survives_ingestion(self, stores):
        """Y. The URL asked for and the URL arrived at are both retained."""
        _, artifacts = stores
        result = run(stores)
        candidate = result.acquired[0]
        stored = artifacts.load(candidate.artifact_sha256)
        assert stored.source.discovery_url == DATASHEET_URL
        assert stored.source.final_artifact_url == DATASHEET_URL
        assert stored.source.publisher == MAKER
        assert stored.source.retrieved_at is not None
        # What the frozen model has no field for stays on the candidate.
        assert candidate.redirect_chain == (DATASHEET_URL,)
        assert candidate.result.query in result.executed_queries

    @pytest.mark.parametrize(
        ("url", "reason"),
        [
            (f"https://amazon.com/dp/{MPN}", RejectionReason.MARKETPLACE_SOURCE),
            (f"https://grainger.com/p/{MPN}", RejectionReason.DISTRIBUTOR_SOURCE),
            ("https://se.com/p/LC1D18B7/", RejectionReason.SIBLING_REFERENCE),
            ("https://se.com/range/LC1D18/", RejectionReason.FAMILY_ONLY),
        ],
    )
    def test_the_distractions_are_refused_with_reasons(self, stores, url, reason):
        result = run(stores)
        candidate = next(c for c in result.candidates if c.url == url)
        assert candidate.status is CandidateStatus.REJECTED
        assert reason.value in candidate.rejections
        assert candidate.artifact_sha256 is None

    def test_only_the_eligible_candidate_was_fetched(self, stores):
        """No marketplace page is ever downloaded, let alone hashed as evidence."""
        result = run(stores)
        assert result.summary.fetch_attempts == 1
        assert result.summary.fetch_successes == 1
        assert result.summary.artifacts_ingested == 1

    def test_the_manufacturer_source_ranks_first(self, stores):
        """Even though the search engine put Amazon at rank 1."""
        result = run(stores)
        assert result.candidates[0].url == DATASHEET_URL
        assert result.preferred is not None
        assert result.preferred.url == DATASHEET_URL

    def test_the_summary_counts_are_operational_not_accuracy(self, stores):
        result = run(stores)
        summary = result.summary
        assert summary.search_results == len(RESULTS)
        assert summary.official_candidates == 3  # datasheet, sibling, family: all se.com
        assert summary.exact_mpn_candidates == 3  # amazon, grainger, datasheet
        assert summary.rejected_third_party == 2
        assert summary.bytes_downloaded == len(PDF_BYTES)

    def test_finding_nothing_authoritative_is_a_valid_result(self, stores):
        """No manufacturer source is a better answer than a marketplace one."""
        result = run(
            stores,
            results=[{"url": f"https://amazon.com/dp/{MPN}", "title": MPN, "rank": 1}],
        )
        assert result.found_authoritative_source is False
        assert result.acquired == ()
        assert result.summary.fetch_attempts == 0
        assert result.rejection_counts() == {RejectionReason.MARKETPLACE_SOURCE.value: 1}

    def test_identical_bytes_from_two_urls_deduplicate(self, stores):
        """X. One document published twice is one document."""
        _, artifacts = stores
        result = run(
            stores,
            results=[
                {"url": DATASHEET_URL, "title": MPN, "rank": 1},
                {"url": f"https://se.com/mirror/{MPN}.pdf", "title": MPN, "rank": 2},
            ],
        )
        assert len(result.acquired) == 2
        assert len({c.artifact_sha256 for c in result.acquired}) == 1
        assert len(artifacts.hashes()) == 1
        assert result.summary.artifacts_ingested == 1

    def test_an_official_html_page_is_accepted_but_not_ingested(self, stores):
        """The documented scope edge of this milestone, not a quality judgement."""
        result = run(
            stores,
            results=[{"url": f"https://se.com/product/{MPN}/", "title": MPN, "rank": 1}],
        )
        candidate = result.candidates[0]
        assert candidate.status is CandidateStatus.ACCEPTED_NOT_ACQUIRED
        assert RejectionReason.NOT_INGESTABLE_YET.value in candidate.rejections
        assert candidate.artifact_sha256 is None
        assert candidate.content_type == "text/html"

    def test_fetch_budget_is_enforced(self, stores):
        """AE."""
        results = [
            {"url": f"https://se.com/files/{MPN}_a.pdf", "title": MPN, "rank": 1},
            {"url": f"https://se.com/files/{MPN}_b.pdf", "title": MPN, "rank": 2},
            {"url": f"https://se.com/files/{MPN}_c.pdf", "title": MPN, "rank": 3},
        ]
        result = run(stores, results=results, budget=DiscoveryBudget(max_fetch_attempts=1))
        assert result.summary.fetch_attempts == 1
        exhausted = [
            c
            for c in result.candidates
            if RejectionReason.FETCH_BUDGET_EXHAUSTED.value in c.rejections
        ]
        assert len(exhausted) == 2


class TestReplay:
    def test_replay_reproduces_the_live_run(self, stores):
        live = run(stores)
        replayed = run(stores, mode=RunMode.REPLAY)
        assert [c.url for c in replayed.candidates] == [c.url for c in live.candidates]
        assert replayed.summary.search_results == live.summary.search_results

    def test_a_missing_cassette_fails_closed(self, stores):
        """Z. Never a silent fall back to the network."""
        with pytest.raises(ReplayMissError):
            run(stores, mode=RunMode.REPLAY)

    def test_replay_never_calls_the_provider(self, stores):
        """AA."""
        recorder = FakeSearchProvider()
        run(stores, provider=recorder)
        assert recorder.calls

        replayer = FakeSearchProvider()
        run(stores, mode=RunMode.REPLAY, provider=replayer)
        assert replayer.calls == []

    def test_replay_opens_no_socket(self, stores, monkeypatch):
        """AA, the strong form: discovery in REPLAY makes no network call at all."""
        run(stores)  # record first, with the mock transport

        def refuse(*args, **kwargs):
            raise AssertionError("discovery attempted a network connection during REPLAY")

        monkeypatch.setattr(socket.socket, "connect", refuse)
        monkeypatch.setattr(socket, "create_connection", refuse)
        result = run(stores, mode=RunMode.REPLAY)
        assert result.summary.search_results == len(RESULTS)

    def test_no_credential_reaches_a_cassette(self, stores):
        """AG."""
        cassettes, _ = stores
        provider = FakeSearchProvider(api_key="super-secret-token-abc123")
        run(stores, provider=provider)

        recorded = cassettes.keys()
        assert recorded
        for key in recorded:
            body = cassettes.path_for(key).read_text(encoding="utf-8")
            assert "super-secret-token-abc123" not in body
            assert "api_key" not in body


class TestRedirectAuthority:
    """Being safe to connect to and being the publisher are different properties.

    `fetch_url` already re-applies network policy at every hop, so a redirect into the
    private network fails. It says nothing about *ownership*: an approved manufacturer URL
    can redirect to an entirely public, entirely reachable third-party host, and before
    this gate existed those bytes were stored as manufacturer evidence because the
    original candidate still said APPROVED_MANUFACTURER.
    """

    def _redirecting(self, target: str):
        def handler(request: httpx.Request) -> httpx.Response:
            if "start" in str(request.url):
                return httpx.Response(302, headers={"location": target})
            return httpx.Response(
                200, content=PDF_BYTES, headers={"content-type": "application/pdf"}
            )

        return httpx.MockTransport(handler)

    def _run(self, stores, target: str):
        cassettes, artifacts = stores
        start = f"https://se.com/start/{MPN}.pdf"
        return (
            discover_sources(
                request_from(raw_row()),
                provider=FakeSearchProvider([{"url": start, "title": MPN, "rank": 1}]),
                registry=registry(),
                cassettes=cassettes,
                artifacts=artifacts,
                mode=RunMode.LIVE,
                transport=self._redirecting(target),
                resolver=resolver,
            ),
            artifacts,
        )

    def test_redirect_within_the_approved_domain_succeeds(self):
        """A/B is covered below; this is the same-host case."""

    @pytest.mark.parametrize(
        "target",
        [
            f"https://se.com/files/{MPN}.pdf",  # A: same approved host
            f"https://download.se.com/{MPN}.pdf",  # B: approved subdomain
            f"https://schneider-electric.com/{MPN}.pdf",  # C: second approved domain
        ],
    )
    def test_redirects_that_stay_with_the_manufacturer_succeed(self, stores, target):
        result, artifacts = self._run(stores, target)
        assert len(result.acquired) == 1
        assert result.acquired[0].final_authority is SourceAuthority.APPROVED_MANUFACTURER
        assert len(artifacts.hashes()) == 1

    @pytest.mark.parametrize(
        "target",
        [
            f"https://unrelated.example/{MPN}.pdf",  # F: public but unknown
            f"https://grainger.com/{MPN}.pdf",  # D: distributor
            f"https://amazon.com/{MPN}.pdf",  # E: marketplace
            f"https://acme.example/{MPN}.pdf",  # G: another manufacturer's domain
        ],
    )
    def test_redirects_that_leave_the_manufacturer_lose_authority(self, stores, target):
        """C-G. Every one of these destinations is public and safe to connect to."""
        result, artifacts = self._run(stores, target)
        candidate = result.candidates[0]
        assert candidate.status is CandidateStatus.REJECTED
        assert RejectionReason.REDIRECT_AUTHORITY_LOST.value in candidate.rejections
        assert candidate.artifact_sha256 is None
        # H: the bytes were downloaded and then discarded. Nothing was stored.
        assert artifacts.hashes() == ()
        assert result.summary.artifacts_ingested == 0

    def test_the_lost_authority_reason_is_not_an_ssrf_reason(self, stores):
        """Network safety and publisher authority must stay separable in the record."""
        result, _ = self._run(stores, f"https://unrelated.example/{MPN}.pdf")
        rejections = result.candidates[0].rejections
        assert RejectionReason.PRIVATE_ADDRESS.value not in rejections
        assert RejectionReason.BLOCKED_HOST.value not in rejections

    def test_a_redirect_to_a_private_address_still_fails_as_ssrf(self, stores):
        """P. The existing network protection is untouched by the authority gate."""
        result, artifacts = self._run(stores, "http://127.0.0.1/admin.pdf")
        assert RejectionReason.PRIVATE_ADDRESS.value in result.candidates[0].rejections
        assert artifacts.hashes() == ()

    def test_the_stored_artifact_records_the_final_url(self, stores):
        """G (spec): provenance is checked against where the bytes came from."""
        result, artifacts = self._run(stores, f"https://download.se.com/{MPN}.pdf")
        stored = artifacts.load(result.acquired[0].artifact_sha256)
        assert stored.source.final_artifact_url == f"https://download.se.com/{MPN}.pdf"
        assert stored.source.discovery_url == f"https://se.com/start/{MPN}.pdf"


class TestStoredProvenance:
    def test_provenance_comes_from_the_provider_not_a_default(self, stores):
        """M. The fake provider declares a curated corpus, and that is what is stored."""
        _, artifacts = stores
        result = run(stores)
        stored = artifacts.load(result.acquired[0].artifact_sha256)
        assert stored.source.discovery_method is DiscoveryMethod.CURATED_CORPUS

    def test_a_provider_name_alone_cannot_spoof_google_grounding(self, stores):
        """N. Branding is not provenance."""

        class NamedGoogle(FakeSearchProvider):
            name = "google-search"
            discovery_method = DiscoveryMethod.CURATED_CORPUS

        _, artifacts = stores
        result = run(stores, provider=NamedGoogle())
        stored = artifacts.load(result.acquired[0].artifact_sha256)
        assert stored.source.discovery_method is DiscoveryMethod.CURATED_CORPUS

    def test_a_provider_declaring_google_grounding_records_it(self, stores):
        """N. The declaration is what counts, and only the provider can make it."""

        class RealGoogle(FakeSearchProvider):
            name = "programmable-search"
            discovery_method = DiscoveryMethod.GOOGLE_SEARCH_GROUNDING

        _, artifacts = stores
        result = run(stores, provider=RealGoogle())
        stored = artifacts.load(result.acquired[0].artifact_sha256)
        assert stored.source.discovery_method is DiscoveryMethod.GOOGLE_SEARCH_GROUNDING

    def test_an_undeclared_provider_cannot_store_an_artifact(self, stores):
        """Unsupported provenance is refused, not rounded to whatever fits the enum."""

        class Undeclared(FakeSearchProvider):
            name = "mystery"
            discovery_method = None

        _, artifacts = stores
        result = run(stores, provider=Undeclared())
        candidate = next(c for c in result.candidates if c.url == DATASHEET_URL)
        assert candidate.status is CandidateStatus.REJECTED
        assert RejectionReason.DISCOVERY_PROVENANCE_UNDECLARED.value in candidate.rejections
        assert artifacts.hashes() == ()

    def test_an_unknown_document_kind_is_not_called_a_datasheet(self, stores):
        """O. A PDF from a manufacturer may be a manual, a warranty, or a brochure.

        The URL gives no hint of what the document is — no `.pdf`, no `datasheet`, no
        `/product` — so the kind stays UNKNOWN even though PDF bytes came back.
        """
        cassettes, artifacts = stores

        def always_pdf(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=PDF_BYTES, headers={"content-type": "application/pdf"}
            )

        url = f"https://se.com/f/{MPN}"
        result = discover_sources(
            request_from(raw_row()),
            provider=FakeSearchProvider([{"url": url, "title": MPN, "rank": 1}]),
            registry=registry(),
            cassettes=cassettes,
            artifacts=artifacts,
            mode=RunMode.LIVE,
            transport=httpx.MockTransport(always_pdf),
            resolver=resolver,
        )
        assert result.acquired[0].kind is SourceKind.UNKNOWN
        stored = artifacts.load(result.acquired[0].artifact_sha256)
        assert stored.source.source_type is None

    def test_a_datasheet_is_recorded_as_one(self, stores):
        _, artifacts = stores
        result = run(stores)
        stored = artifacts.load(result.acquired[0].artifact_sha256)
        assert stored.source.source_type is SourceType.MANUFACTURER_DATASHEET


class TestHintStanding:
    """A dirty spelling may help find a page. It may not name its publisher."""

    def _registry(self):
        return parse_registry(
            {
                "name": "test",
                "authority": "REVIEWED",
                "manufacturer": [
                    {
                        "key": "dewalt",
                        "authority_hints": ["DeWalt"],
                        "locator_hints": ["Black & Decker/dewlt"],
                        "domains": ["dewalt.com"],
                        "review": REVIEW,
                    }
                ],
            }
        )

    def test_a_locator_only_hint_cannot_grant_manufacturer_authority(self):
        """I."""
        assert (
            classify_authority(
                "dewalt.com",
                registry=self._registry(),
                manufacturer_hint="Black & Decker/dewlt",
            )
            is SourceAuthority.UNVERIFIED_MANUFACTURER
        )

    def test_a_reviewed_hint_does_grant_authority(self):
        """K."""
        assert (
            classify_authority("dewalt.com", registry=self._registry(), manufacturer_hint="DeWalt")
            is SourceAuthority.APPROVED_MANUFACTURER
        )

    def test_a_locator_only_hint_still_builds_site_queries(self):
        """J. Losing the search would be a worse trade than withholding the authority."""
        from skutruth.discovery import build_queries

        request = DiscoveryRequest(mpn="DCL183", manufacturer_hint="Black & Decker/dewlt")
        domains = self._registry().domains_for_hint(request.manufacturer_hint)
        assert domains == ("dewalt.com",)
        assert '"DCL183" site:dewalt.com' in build_queries(request, approved_domains=domains)

    def test_an_unverified_candidate_is_never_acquired(self, stores):
        """The end-to-end consequence of I."""
        cassettes, artifacts = stores
        result = discover_sources(
            DiscoveryRequest(mpn="DCL183", manufacturer_hint="Black & Decker/dewlt"),
            provider=FakeSearchProvider(
                [{"url": "https://dewalt.com/p/DCL183.pdf", "title": "DCL183", "rank": 1}]
            ),
            registry=self._registry(),
            cassettes=cassettes,
            artifacts=artifacts,
            mode=RunMode.LIVE,
            transport=transport(),
            resolver=resolver,
        )
        candidate = result.candidates[0]
        assert candidate.authority is SourceAuthority.UNVERIFIED_MANUFACTURER
        assert RejectionReason.AUTHORITY_NOT_ESTABLISHED.value in candidate.rejections
        assert artifacts.hashes() == ()

    def test_review_metadata_does_not_promote_a_locator_alias(self):
        """A reviewed *domain* says nothing about which dirty strings name the maker."""
        assert (
            classify_authority(
                "dewalt.com",
                registry=self._registry(),
                manufacturer_hint="Black & Decker/dewlt",
            )
            is SourceAuthority.UNVERIFIED_MANUFACTURER
        )

    def test_a_demo_registry_cannot_license_evidence(self):
        """L."""
        demo = parse_registry(
            {
                "name": "illustrative",
                "authority": "DEMO",
                "manufacturer": [
                    {"key": "dewalt", "authority_hints": ["DeWalt"], "domains": ["dewalt.com"]}
                ],
            }
        )
        assert (
            classify_authority("dewalt.com", registry=demo, manufacturer_hint="DeWalt")
            is SourceAuthority.UNVERIFIED_MANUFACTURER
        )

    def test_the_old_single_hint_form_is_refused(self):
        """Migrating by guessing which spellings were reviewed is the failure to avoid."""
        from skutruth.discovery import MalformedRegistryError

        with pytest.raises(MalformedRegistryError, match="uses `hints`"):
            parse_registry(
                {
                    "name": "x",
                    "authority": "REVIEWED",
                    "manufacturer": [
                        {"key": "a", "hints": ["A"], "domains": ["a.example"]}
                    ],
                }
            )

    def test_a_name_cannot_be_both_authority_and_locator(self):
        from skutruth.discovery import MalformedRegistryError

        with pytest.raises(MalformedRegistryError, match="both an authority and a locator"):
            parse_registry(
                {
                    "name": "x",
                    "authority": "REVIEWED",
                    "manufacturer": [
                        {
                            "key": "a",
                            "authority_hints": ["Acme"],
                            "locator_hints": ["ACME."],
                            "domains": ["a.example"],
                        }
                    ],
                }
            )


#: The only discovery module permitted to touch a model client.
#:
#: Google Search grounding is model-mediated: reaching it *requires* a Gemini call, so a
#: blanket "discovery imports no model SDK" rule can no longer be stated. The guarantee it
#: existed to protect is narrower and is unchanged — **no model participates in a
#: decision** — so the rule now names the seam and holds every deciding module to the
#: original standard. A model may say where to look. Nothing else.
MODEL_AWARE_DISCOVERY_MODULES = {"grounded_search.py"}


class TestArchitecturalGuarantees:
    def _imports_of(self, path):
        import ast

        tree = ast.parse(path.read_text(encoding="utf-8"))
        imported: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        return imported

    def _package(self):
        from pathlib import Path

        return Path(__file__).resolve().parents[1] / "backend" / "skutruth" / "discovery"

    def test_no_deciding_module_imports_a_model_client(self):
        """AC. Source authority is policy, never a model's opinion."""
        for module in self._package().glob("*.py"):
            if module.name in MODEL_AWARE_DISCOVERY_MODULES:
                continue
            imported = self._imports_of(module)
            assert not [m for m in imported if m.split(".")[0] in {"google", "vertexai"}], module
            assert not [m for m in imported if "extraction" in m], module

    def test_only_the_named_provider_seam_may_reach_a_model(self):
        """The allowlist is exhaustive: a new model-using module fails this."""
        offenders = {
            module.name
            for module in self._package().glob("*.py")
            if [m for m in self._imports_of(module) if m.split(".")[0] in {"google", "vertexai"}]
        }
        assert offenders <= MODEL_AWARE_DISCOVERY_MODULES

    def test_the_grounded_provider_asks_the_model_only_to_locate(self):
        """The prompt must not delegate any judgement the deterministic gates own."""
        from skutruth.discovery.grounded_search import build_grounding_prompt

        prompt = build_grounding_prompt('"LC1D18P7" site:se.com').casefold()
        assert "google search" in prompt
        # It must actively tell the model not to do these, not merely omit them.
        assert "do not describe the product" in prompt
        assert "do not state any specification" in prompt
        assert "authoritative" in prompt

    def test_policy_decides_authority_without_the_provider(self):
        """The deciding modules import the registry, not the search seam."""
        policy = self._imports_of(self._package() / "policy.py")
        assert any("domains" in m for m in policy)
        assert not any("grounded" in m for m in policy)

    def test_no_confidence_or_probability_field_exists(self):
        """AD."""
        from skutruth.discovery import (
            DiscoveryRequest as Req,
        )
        from skutruth.discovery import (
            DiscoveryResult as Res,
        )
        from skutruth.discovery import (
            DiscoverySummary as Sum,
        )
        from skutruth.discovery import (
            SearchResult as SR,
        )
        from skutruth.discovery import (
            SourceCandidate as SC,
        )

        banned = {"confidence", "probability", "score", "certainty", "likelihood"}
        for model in (Req, Res, Sum, SR, SC):
            assert not banned & set(model.model_fields)

    def test_a_snippet_never_becomes_an_artifact(self, stores):
        """S, the strong form: no snippet text is anywhere in stored bytes."""
        _, artifacts = stores
        marker = "SNIPPET-MUST-NOT-BE-EVIDENCE"
        results = [
            {"url": DATASHEET_URL, "title": MPN, "snippet": marker, "rank": 1},
        ]
        result = run(stores, results=results)
        sha = result.acquired[0].artifact_sha256
        stored = artifacts.load(sha)
        assert marker not in artifacts.load_original_bytes(sha).decode("latin-1")
        assert all(marker not in page.raw_text for page in stored.pages)
        # The snippet is retained on the candidate as locator metadata, and only there.
        assert result.acquired[0].result.snippet == marker
