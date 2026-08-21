"""The submission API, exercised the way a judge's browser will exercise it.

Two things are load-bearing here and are asserted rather than assumed.

**The demo cannot reach the network.** `DEMO_REPLAY` is what will be running while
somebody watches, and the whole reason it exists is that Google, Vertex, or a
manufacturer site being unavailable must not turn into a blank screen. One test guards
every outbound connection and DNS lookup for the duration of every route, and fails if
anything addresses something other than localhost.

**The API cannot leak.** The response is a public surface built over private material:
stored third-party documents, cassette bodies, absolute paths on the operator's machine.
A test walks every rendered response and asserts none of it is there.
"""

from __future__ import annotations

import socket
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from skutruth.api import ApiSettings, ExecutionMode, create_app

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

CASES = ROOT / "data" / "demo" / "cases.json"
KICHLER = "45297BK"
SATCO = "62-1875"
FEIT = "SHOP/4X2/840/V1"


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(create_app(ApiSettings()))


def _detail(client: TestClient, mpn: str) -> dict:
    response = client.get(f"/api/demo/products/{mpn}")
    assert response.status_code == 200, response.text
    return response.json()


def _stage(detail: dict, stage: str) -> dict:
    return next(item for item in detail["timeline"] if item["stage"] == stage)


class TestHealth:
    def test_health_reports_the_mode_and_touches_nothing(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok"
        assert body["mode"] == "DEMO_REPLAY"
        assert body["demo_cases"] == 3
        assert body["external_calls"] is False

    def test_live_mode_says_so(self):
        live = TestClient(create_app(ApiSettings(mode=ExecutionMode.LIVE)))
        assert live.get("/api/health").json()["external_calls"] is True


class TestDemoIndex:
    def test_all_three_real_cases_are_listed(self, client):
        body = client.get("/api/demo/products").json()
        assert [item["mpn"] for item in body["products"]] == [KICHLER, SATCO, FEIT]

    def test_the_index_counts_match_the_detail(self, client):
        body = client.get("/api/demo/products").json()
        for card in body["products"]:
            detail = _detail(client, card["mpn"])
            assert card["verified_count"] == len(detail["attributes"]["verified"])
            assert card["withheld_count"] == len(detail["attributes"]["withheld"])

    def test_metrics_are_countable_facts_only(self, client):
        metrics = client.get("/api/demo/products").json()["metrics"]
        assert metrics["organizer_rows"] == 1000
        assert metrics["delivery_columns"] == 252
        assert metrics["attribute_triplets"] == 50
        # No accuracy, precision, or recall: there is no labelled benchmark to compute
        # them against, and a metric named that way would be read as one.
        assert not {"accuracy", "precision", "recall"} & set(metrics)


class TestKichlerCompleteCase:
    """The one case that reaches a verified manufacturer fact."""

    def test_identity_is_exact_sku(self, client):
        identity = _detail(client, KICHLER)["identity"]
        assert identity["decision"] == "EXACT"
        assert identity["identity_scope"] == "EXACT_SKU"
        assert identity["covers_mpn"] == KICHLER

    def test_the_model_proposed_ten_and_all_ten_were_source_bound(self, client):
        ai = _detail(client, KICHLER)["ai"]
        assert ai["ran"] is True
        assert ai["proposal_count"] == 10
        assert ai["source_bound_count"] == 10
        assert ai["rejected_count"] == 0

    def test_seven_verified_three_withheld(self, client):
        attributes = _detail(client, KICHLER)["attributes"]
        assert len(attributes["proposed"]) == 10
        assert len(attributes["verified"]) == 7
        assert len(attributes["withheld"]) == 3

    def test_every_verified_fact_is_manufacturer_evidence_and_not_delivery_content(
        self, client
    ):
        for fact in _detail(client, KICHLER)["attributes"]["verified"]:
            assert fact["authority"] == "MANUFACTURER_EVIDENCE"
            assert fact["unilog_mapping_status"] == "UNAUTHORIZED"
            assert fact["delivery_eligible"] is False

    def test_the_verified_values_are_the_ones_the_source_states(self, client):
        facts = {
            item["source_key"]: item
            for item in _detail(client, KICHLER)["attributes"]["verified"]
        }
        assert facts["lighting.overall_width"]["value"] == "24"
        assert facts["lighting.finish_name"]["value"] == "Black"
        assert facts["lighting.socket_configuration"]["value"] == "3 E26 (Medium)"
        # The comparison the demo is built on: proposal and source agree, so it verified.
        assert facts["lighting.overall_width"]["source_value"] == "24"
        assert facts["lighting.overall_width"]["source_label"] == "Width"

    def test_a_withheld_candidate_keeps_its_typed_reason(self, client):
        withheld = {
            item["source_key"]: item
            for item in _detail(client, KICHLER)["attributes"]["withheld"]
        }
        light_count = withheld["lighting.light_count_descriptor"]
        assert light_count["proposed_value"] == "3-Light"
        # Evidence exists and still is not enough: the source files it under a generic
        # "Attribute" bucket, which does not establish which concept it belongs to.
        assert light_count["source_value"] == "3-Light"
        assert light_count["reason"] == "SOURCE_PROPERTY_NOT_AUTHORIZED"
        assert light_count["status"] == "UNVERIFIED"

    def test_delivery_mapping_is_unauthorized_despite_verified_facts(self, client):
        delivery = _detail(client, KICHLER)["delivery"]
        assert delivery["mapped_count"] == 0
        assert delivery["mapping_status"] == "UNAUTHORIZED"
        assert delivery["unauthorized_reason"]

    def test_every_verified_fact_carries_a_usable_locator(self, client):
        for fact in _detail(client, KICHLER)["attributes"]["verified"]:
            locator = fact["locator"]
            assert locator["kind"] in {"HTML_JSONLD", "HTML_TEXT"}
            if locator["kind"] == "HTML_JSONLD":
                assert locator["jsonld_block_index"] is not None
                assert locator["json_pointer"]
            else:
                assert locator["element_index"] is not None
                assert locator["start_offset"] is not None
                assert locator["end_offset"] is not None


class TestSatcoBlocker:
    """Trusted discovery, blocked fetch, and nothing invented afterwards."""

    def test_discovery_found_the_exact_official_source(self, client):
        source = _detail(client, SATCO)["source"]
        assert source["discovery_status"] == "SUCCESS"
        assert source["authority"] == "APPROVED_MANUFACTURER"
        assert source["relevance"] == "EXACT"
        assert source["exact_candidates"] >= 1
        assert source["discovery_url"].startswith("https://www.satco.com/")

    def test_acquisition_is_blocked_by_a_rate_limit(self, client):
        detail = _detail(client, SATCO)
        assert detail["source"]["blocker"] == "SOURCE_RATE_LIMITED"
        acquisition = _stage(detail, "ACQUISITION")
        assert acquisition["status"] == "BLOCKED"
        assert acquisition["reason"] == "SOURCE_RATE_LIMITED"
        # An HTTP 429 cannot be replayed, and the response says so rather than implying
        # the server just re-derived it.
        assert acquisition["evidence"] == "RECORDED_OBSERVATION"

    def test_nothing_downstream_claims_anything(self, client):
        detail = _detail(client, SATCO)
        assert detail["source"]["artifact_sha256"] is None
        assert detail["identity"]["decision"] == "NOT_RUN"
        assert detail["ai"]["ran"] is False
        assert detail["ai"]["proposal_count"] == 0
        assert detail["attributes"] == {"proposed": [], "verified": [], "withheld": []}
        for stage in ("IDENTITY", "AI_PROPOSAL", "VERIFICATION"):
            assert _stage(detail, stage)["status"] == "NOT_RUN"


class TestFeitRepresentationGap:
    """Official sources, a differently spelled reference, and a refusal to guess."""

    def test_the_manufacturer_is_approved_and_the_reference_is_not_exact(self, client):
        source = _detail(client, FEIT)["source"]
        assert source["authority"] == "APPROVED_MANUFACTURER"
        assert source["exact_candidates"] == 0
        assert source["blocker"] == "NO_EXACT_SOURCE"

    def test_the_gap_is_described_as_representation_not_model_failure(self, client):
        detail = _detail(client, FEIT)
        blocker = detail["source"]["blocker_detail"]
        assert "shop-4x2-840-v1" in blocker
        assert "SHOP/4X2/840/V1" in blocker
        # The model is not implicated, because the model never ran.
        assert detail["ai"]["ran"] is False

    def test_nothing_was_acquired_and_nothing_was_read(self, client):
        detail = _detail(client, FEIT)
        assert detail["source"]["artifact_sha256"] is None
        assert detail["identity"]["decision"] == "NOT_RUN"
        assert detail["attributes"]["verified"] == []
        for stage in ("ACQUISITION", "IDENTITY", "AI_PROPOSAL", "VERIFICATION"):
            assert _stage(detail, stage)["status"] == "NOT_RUN"

    def test_the_slash_bearing_mpn_is_routable(self, client):
        # A route that could not express this MPN would hide the exact case.
        assert client.get(f"/api/demo/products/{FEIT}").status_code == 200


class TestTypedFailures:
    def test_an_unknown_demo_product_is_a_typed_404(self, client):
        response = client.get("/api/demo/products/NOT-A-REAL-MPN")
        assert response.status_code == 404
        body = response.json()
        assert body["code"] == "DEMO_CASE_NOT_FOUND"
        assert body["retryable"] is False

    def test_an_invalid_analyze_payload_is_a_typed_422(self, client):
        response = client.post("/api/analyze", json={"description": "no reference"})
        assert response.status_code == 422
        body = response.json()
        assert body["code"] == "INVALID_REQUEST"
        assert body["details"] == {"mpn": "missing"}

    def test_an_unknown_field_is_refused_rather_than_ignored(self, client):
        response = client.post("/api/analyze", json={"mpn": "X1", "source_url": "http://x"})
        assert response.status_code == 422
        assert response.json()["code"] == "INVALID_REQUEST"

    def test_no_traceback_or_exception_text_reaches_the_client(self, client):
        body = client.get("/api/demo/products/NOT-A-REAL-MPN").text
        assert "Traceback" not in body
        assert "Error" not in body.replace("DEMO_CASE_NOT_FOUND", "")


class TestAnalyze:
    def test_a_known_row_replays_the_full_case(self, client):
        body = client.post("/api/analyze", json={"mpn": KICHLER}).json()
        assert body["case_id"] == "kichler-45297bk"
        assert len(body["attributes"]["verified"]) == 7

    def test_an_unknown_row_gets_deterministic_stages_and_honest_gaps(self, client):
        body = client.post(
            "/api/analyze",
            json={
                "mpn": "ZZZ-0001",
                "description": "ZZZ-0001 Some Unknown Widget",
                "manufacturer": "Nobody At All (0000)",
            },
        ).json()
        assert body["normalization"]["manufacturer_decision"] in {"REVIEW", "WITHHOLD"}
        assert body["classification"]["decision"] in {"COMMIT", "REVIEW", "WITHHOLD"}
        assert body["ai"]["ran"] is False
        assert body["attributes"]["verified"] == []
        for stage in ("DISCOVERY", "ACQUISITION", "IDENTITY", "AI_PROPOSAL", "VERIFICATION"):
            assert _stage(body, stage)["status"] == "NOT_RUN"

    def test_deterministic_stages_still_do_real_work(self, client):
        body = client.post(
            "/api/analyze",
            json={
                "mpn": "45297ZZ",
                "description": "45297ZZ Kichler Wall Lt",
                "manufacturer": "Kichler Lighting (KICLI)",
            },
        ).json()
        assert body["normalization"]["manufacturer"] == "Kichler Lighting"
        assert body["classification"]["family"] == "LIGHTING"
        # Recognising the manufacturer is not evidence about the product.
        assert body["source"]["discovery_status"] == "NOT_RUN"

    def test_live_mode_refuses_arbitrary_rows_rather_than_falling_back(self):
        live = TestClient(create_app(ApiSettings(mode=ExecutionMode.LIVE)))
        response = live.post("/api/analyze", json={"mpn": "ZZZ-0002"})
        assert response.status_code == 501
        assert response.json()["code"] == "LIVE_MODE_UNAVAILABLE"


class TestReplayMakesNoNetworkCalls:
    """The claim the demo depends on, enforced rather than trusted."""

    def test_every_route_answers_with_sockets_forbidden(self, monkeypatch):
        """Loopback stays allowed; anything leaving the machine fails the test.

        The test client runs the app through an in-process transport, but its event loop
        still needs a loopback socketpair on Windows. Banning `socket.socket` outright
        would fail on the harness rather than on the app, so the guard is on the
        destination: a connect or a DNS lookup for anything but localhost is the thing
        that must never happen.
        """
        allowed = {"127.0.0.1", "::1", "localhost", ""}
        real_connect = socket.socket.connect
        real_getaddrinfo = socket.getaddrinfo

        def guarded_connect(self, address, *args, **kwargs):
            host = address[0] if isinstance(address, tuple) else str(address)
            if host not in allowed:
                raise AssertionError(f"DEMO_REPLAY attempted a network call to {host}")
            return real_connect(self, address, *args, **kwargs)

        def guarded_getaddrinfo(host, *args, **kwargs):
            if host not in allowed and host is not None:
                raise AssertionError(f"DEMO_REPLAY attempted to resolve {host}")
            return real_getaddrinfo(host, *args, **kwargs)

        client = TestClient(create_app(ApiSettings()))
        monkeypatch.setattr(socket.socket, "connect", guarded_connect)
        monkeypatch.setattr(socket, "getaddrinfo", guarded_getaddrinfo)
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/demo/products").status_code == 200
        assert client.get("/api/schema").status_code == 200
        for mpn in (KICHLER, SATCO, FEIT):
            assert client.get(f"/api/demo/products/{mpn}").status_code == 200
        assert client.post("/api/analyze", json={"mpn": "ZZZ-0003"}).status_code == 200


@pytest.fixture(scope="module")
def rendered(client: TestClient) -> str:
    """Every route's response body, concatenated, for the leak assertions below."""
    chunks = [
        client.get("/api/health").text,
        client.get("/api/demo/products").text,
        client.get("/api/schema").text,
        *(client.get(f"/api/demo/products/{mpn}").text for mpn in (KICHLER, SATCO, FEIT)),
        client.post("/api/analyze", json={"mpn": KICHLER}).text,
    ]
    return "\n".join(chunks)


class TestTheApiDoesNotLeak:
    """Everything the response must never contain."""

    @pytest.mark.parametrize(
        "forbidden",
        [
            "E:\\\\",
            "E:/UNIHACK",
            "C:\\\\Users",
            "/home/",
            "data/replay/runtime",
            "data/artifacts/runtime",
            "application_default_credentials",
            "refresh_token",
            "access_token",
            "client_secret",
            "Bearer ",
        ],
    )
    def test_no_path_or_credential_material_appears(self, rendered, forbidden):
        assert forbidden not in rendered

    def test_no_raw_html_is_returned(self, rendered):
        for marker in ("<html", "<div", "<script", "<!DOCTYPE", "</span>"):
            assert marker not in rendered

    def test_no_cassette_internals_are_returned(self, rendered):
        for marker in ("cassette_version", "key_version", "captured_at", "system_instruction"):
            assert marker not in rendered

    def test_evidence_excerpts_stay_pointers(self, client):
        from skutruth.api.models import MAX_EXCERPT

        payload = _detail(client, KICHLER)
        for group in ("proposed", "verified", "withheld"):
            for item in payload["attributes"][group]:
                locator = item.get("locator")
                if locator:
                    assert len(locator["excerpt"]) <= MAX_EXCERPT


class TestTheCommittedRecordMatchesTheEvidence:
    """The demo record is derived, so it must not drift from what the pipeline does."""

    def test_the_case_file_is_committed_and_valid(self):
        from skutruth.api.cases import load_demo_cases

        library = load_demo_cases(CASES)
        assert len(library.cases) == 3

    def test_rederiving_from_local_evidence_reproduces_the_file(self):
        """Skipped on a clean clone: the evidence is deliberately not committed."""
        import build_demo_cases

        for path in (
            build_demo_cases.INPUT,
            build_demo_cases.DELIVERY,
            build_demo_cases.ARTIFACTS,
            build_demo_cases.CASSETTES,
        ):
            if not path.exists():
                pytest.skip("the recorded evidence is not present in this checkout")
        assert build_demo_cases.main(["--check"]) == 0
