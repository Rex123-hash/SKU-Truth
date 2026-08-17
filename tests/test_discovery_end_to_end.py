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
from skutruth.contracts import RunMode
from skutruth.discovery import (
    CandidateStatus,
    DiscoveryRequest,
    MpnRelevance,
    SearchCall,
    SourceAuthority,
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


class FakeSearchProvider:
    """A provider that returns fixed results and counts how often it was asked."""

    name = "fake"

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
            "authority": "DEMO",
            "manufacturer": [
                {
                    "key": "schneider",
                    "hints": [MAKER, "Schneider"],
                    "domains": ["se.com", "schneider-electric.com"],
                }
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


class TestArchitecturalGuarantees:
    def test_no_model_client_is_imported_by_discovery(self):
        """AC. Source authority is policy, never a model's opinion."""
        import ast
        from pathlib import Path

        package = Path(__file__).resolve().parents[1] / "backend" / "skutruth" / "discovery"
        for module in package.glob("*.py"):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            imported: set[str] = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(a.name for a in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.add(node.module)
            assert not [m for m in imported if m.split(".")[0] in {"google", "vertexai"}]
            assert not [m for m in imported if "extraction" in m]

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
