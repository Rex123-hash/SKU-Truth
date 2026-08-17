"""The live search provider adapter, exercised entirely offline.

Every test here injects an `httpx.MockTransport`, so the real request construction,
header handling, size cap, JSON decoding, and error mapping all execute without a socket
being opened. Nothing in the committed suite may reach the internet; a test that needed
to would be measuring Google's availability rather than our code.

The tests are written around the two things that would be most damaging to get wrong: a
credential escaping into somewhere it is persisted or printed, and a `REPLAY` run quietly
making a live call.
"""

from __future__ import annotations

import json

import httpx
import pytest
from skutruth.contracts import DiscoveryMethod, RunMode
from skutruth.discovery import (
    MalformedSearchResponseError,
    MissingSearchCredentialsError,
    SearchBudgetExceededError,
    SearchCall,
    SearchCredentials,
    SearchLimits,
    SearchProviderHTTPError,
    SearchProviderTimeout,
    SearchProviderTransportError,
    execute_search,
)
from skutruth.discovery.programmable_search import (
    API_KEY_ENV,
    ENDPOINT_URL,
    ENGINE_ID_ENV,
    PROVIDER_NAME,
    PROVIDER_VERSION,
    ProgrammableSearchProvider,
    normalize_items,
)
from skutruth.discovery.provider import search_request
from skutruth.replay.errors import ReplayMissError
from skutruth.replay.store import CassetteStore

SECRET = "AIzaSyTOTALLY-NOT-A-REAL-KEY-000000000"
ENGINE = "0123456789abcdef0"
CREDS = SearchCredentials(api_key=SECRET, engine_id=ENGINE)


def api_response(items: list[dict], *, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json={"kind": "customsearch#search", "items": items})


def provider_for(handler, *, limits: SearchLimits | None = None) -> ProgrammableSearchProvider:
    """A provider whose transport is a mock. Construction is otherwise identical."""
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return ProgrammableSearchProvider(CREDS, limits=limits, client=client)


ITEM = {
    "title": "LC1D18P7 contactor",
    "link": "https://download.se.com/files/LC1D18P7.pdf",
    "snippet": "TeSys D contactor, 18 A, 230 V AC coil.",
    "displayLink": "download.se.com",
}


class TestCredentials:
    def test_missing_key_refuses_rather_than_searching_anonymously(self):
        with pytest.raises(MissingSearchCredentialsError) as exc:
            SearchCredentials.from_env({ENGINE_ID_ENV: ENGINE})
        assert API_KEY_ENV in str(exc.value)

    def test_missing_engine_id_refuses(self):
        with pytest.raises(MissingSearchCredentialsError) as exc:
            SearchCredentials.from_env({API_KEY_ENV: SECRET})
        assert ENGINE_ID_ENV in str(exc.value)

    def test_blank_credentials_are_missing_credentials(self):
        """A variable set to whitespace is not a credential."""
        with pytest.raises(MissingSearchCredentialsError):
            SearchCredentials.from_env({API_KEY_ENV: "   ", ENGINE_ID_ENV: ENGINE})

    def test_credentials_read_from_env_when_present(self):
        creds = SearchCredentials.from_env({API_KEY_ENV: SECRET, ENGINE_ID_ENV: ENGINE})
        assert creds.api_key == SECRET
        assert creds.engine_id == ENGINE

    def test_repr_does_not_contain_the_key(self):
        """`repr` reaches logs and assertion diffs without anyone intending it to."""
        assert SECRET not in repr(CREDS)
        assert ENGINE in repr(CREDS)

    def test_scrub_removes_the_key_from_arbitrary_text(self):
        assert SECRET not in CREDS.scrub(f"failed calling ?key={SECRET}&cx=x")


class TestRequestConstruction:
    def test_request_targets_the_documented_endpoint_with_documented_params(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["params"] = dict(request.url.params)
            seen["headers"] = dict(request.headers)
            return api_response([ITEM])

        provider_for(handler).search(SearchCall(query='"LC1D18P7" datasheet', max_results=5))

        assert seen["url"].startswith(ENDPOINT_URL)
        assert seen["params"]["q"] == '"LC1D18P7" datasheet'
        assert seen["params"]["cx"] == ENGINE
        assert seen["params"]["num"] == "5"

    def test_the_key_travels_in_a_header_and_never_in_the_url(self):
        """A query-string credential leaks into access logs, referrers, and proxies."""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("x-goog-api-key")
            return api_response([])

        provider_for(handler).search(SearchCall(query="q"))

        assert seen["auth"] == SECRET
        assert SECRET not in seen["url"]
        assert "key=" not in seen["url"]

    def test_result_cap_is_clamped_to_the_api_maximum(self):
        """The API documents `num` as 1..10. Asking for 50 must not send 50."""
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["num"] = request.url.params["num"]
            return api_response([])

        provider_for(handler).search(SearchCall(query="q", max_results=50))
        assert seen["num"] == "10"

    def test_configured_limit_lowers_the_cap_further(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["num"] = request.url.params["num"]
            return api_response([])

        provider = provider_for(handler, limits=SearchLimits(max_results_per_query=3))
        provider.search(SearchCall(query="q", max_results=10))
        assert seen["num"] == "3"

    def test_limits_above_the_api_maximum_are_refused_at_construction(self):
        with pytest.raises(ValueError):
            SearchLimits(max_results_per_query=25)

    def test_an_empty_query_is_refused_before_a_call_is_made(self):
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return api_response([])

        with pytest.raises(MalformedSearchResponseError):
            provider_for(handler).search(SearchCall(query="   "))
        assert calls == []

    def test_an_overlong_query_is_refused_before_a_call_is_made(self):
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError("should not have been called")

        with pytest.raises(MalformedSearchResponseError):
            provider_for(handler).search(SearchCall(query="x" * 3000))


class TestNormalization:
    def test_documented_fields_map_onto_the_result_shape(self):
        rows = normalize_items([ITEM])
        assert rows == [
            {
                "url": "https://download.se.com/files/LC1D18P7.pdf",
                "title": "LC1D18P7 contactor",
                "snippet": "TeSys D contactor, 18 A, 230 V AC coil.",
                "rank": 1,
            }
        ]

    def test_rank_follows_provider_order(self):
        rows = normalize_items([{"link": f"https://x.example/{i}"} for i in range(1, 4)])
        assert [r["rank"] for r in rows] == [1, 2, 3]

    def test_rank_records_the_original_position_when_a_row_is_skipped(self):
        """Renumbering after a skip would misreport where the provider put a result."""
        rows = normalize_items(
            [
                {"link": "https://a.example/1"},
                {"displayLink": "b.example"},  # no link — unusable
                {"link": "https://c.example/3"},
            ]
        )
        assert [(r["url"], r["rank"]) for r in rows] == [
            ("https://a.example/1", 1),
            ("https://c.example/3", 3),
        ]

    def test_a_row_without_a_link_is_skipped_not_invented(self):
        assert normalize_items([{"displayLink": "se.com", "title": "t"}]) == []

    def test_a_non_dict_row_is_skipped(self):
        assert normalize_items(["nonsense", 42, None]) == []  # type: ignore[list-item]

    def test_missing_title_and_snippet_become_empty_not_none(self):
        rows = normalize_items([{"link": "https://x.example/a"}])
        assert rows[0]["title"] == "" and rows[0]["snippet"] == ""

    def test_absent_items_is_an_empty_result_not_an_error(self):
        """The API omits `items` when a query matches nothing. That is a normal answer."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"kind": "customsearch#search"})

        assert provider_for(handler).search(SearchCall(query="q")) == []

    def test_a_body_that_is_not_an_object_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=["not", "the", "documented", "shape"])

        with pytest.raises(MalformedSearchResponseError):
            provider_for(handler).search(SearchCall(query="q"))

    def test_items_that_is_not_a_list_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"items": {"link": "https://x.example"}})

        with pytest.raises(MalformedSearchResponseError):
            provider_for(handler).search(SearchCall(query="q"))

    def test_a_non_json_body_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"<html>error</html>")

        with pytest.raises(MalformedSearchResponseError):
            provider_for(handler).search(SearchCall(query="q"))

    def test_an_oversized_body_is_refused_before_parsing(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b'{"items":[]}' + b" " * 5000)

        provider = provider_for(handler, limits=SearchLimits(max_response_bytes=1000))
        with pytest.raises(MalformedSearchResponseError):
            provider.search(SearchCall(query="q"))


class TestTypedFailures:
    def test_a_timeout_is_typed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("timed out", request=request)

        with pytest.raises(SearchProviderTimeout):
            provider_for(handler).search(SearchCall(query="q"))

    def test_a_transport_failure_is_typed(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("dns", request=request)

        with pytest.raises(SearchProviderTransportError):
            provider_for(handler).search(SearchCall(query="q"))

    def test_an_error_status_is_typed_and_carries_the_code(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429, json={"error": {"code": 429, "message": "Quota exceeded"}}
            )

        with pytest.raises(SearchProviderHTTPError) as exc:
            provider_for(handler).search(SearchCall(query="q"))
        assert exc.value.status_code == 429
        assert "Quota exceeded" in str(exc.value)

    def test_a_forbidden_status_is_distinguishable_from_a_quota_refusal(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(403, json={"error": {"message": "API key not valid"}})

        with pytest.raises(SearchProviderHTTPError) as exc:
            provider_for(handler).search(SearchCall(query="q"))
        assert exc.value.status_code == 403


class TestCredentialsNeverEscape:
    """The credential must not reach a message, a traceback, or a persisted file."""

    def test_an_http_error_message_does_not_contain_the_key(self):
        def handler(request: httpx.Request) -> httpx.Response:
            # An error body that echoes the request, which some gateways do.
            return httpx.Response(400, json={"error": {"message": f"bad request key={SECRET}"}})

        with pytest.raises(SearchProviderHTTPError) as exc:
            provider_for(handler).search(SearchCall(query="q"))
        assert SECRET not in str(exc.value)
        assert SECRET not in repr(exc.value)

    def test_a_transport_error_message_does_not_contain_the_key(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(f"failed to connect with key={SECRET}", request=request)

        with pytest.raises(SearchProviderTransportError) as exc:
            provider_for(handler).search(SearchCall(query="q"))
        assert SECRET not in str(exc.value)

    def test_a_raised_error_does_not_chain_the_client_exception(self):
        """`raise ... from None`: a chained cause puts the request URL in the traceback."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("boom", request=request)

        with pytest.raises(SearchProviderTransportError) as exc:
            provider_for(handler).search(SearchCall(query="q"))
        assert exc.value.__cause__ is None
        assert exc.value.__context__ is None or not isinstance(
            exc.value.__context__, httpx.HTTPError
        ) or exc.value.__suppress_context__

    def test_the_key_is_not_in_the_replay_descriptor(self):
        request = search_request(
            "q", provider=PROVIDER_NAME, max_results=5, version=PROVIDER_VERSION
        )
        assert SECRET not in json.dumps(request.key_material())
        assert SECRET not in request.model_dump_json()

    def test_the_key_is_not_written_into_a_cassette(self, tmp_path):
        """The strongest form: search live, then grep every byte on disk."""

        def handler(request: httpx.Request) -> httpx.Response:
            return api_response([ITEM])

        store = CassetteStore(tmp_path)
        execute_search(
            SearchCall(query='"LC1D18P7" datasheet', max_results=5),
            provider=provider_for(handler),
            store=store,
            mode=RunMode.LIVE,
        )

        written = list(tmp_path.rglob("*"))
        assert any(p.is_file() for p in written), "expected a cassette to have been recorded"
        for path in written:
            if path.is_file():
                assert SECRET not in path.read_text(encoding="utf-8")


class TestProviderContract:
    def test_the_provider_declares_no_discovery_method(self):
        """No frozen enum value truthfully describes a programmable web-search API.

        This is the recorded contract gap. `GOOGLE_SEARCH_GROUNDING` would be a lie:
        grounding is a different mechanism that returns model-chosen queries and Vertex
        redirect URLs, neither of which this provider produces.
        """
        assert ProgrammableSearchProvider(CREDS).discovery_method is None

    def test_the_provider_does_not_claim_google_search_grounding(self):
        assert (
            ProgrammableSearchProvider(CREDS).discovery_method
            is not DiscoveryMethod.GOOGLE_SEARCH_GROUNDING
        )

    def test_the_provider_declares_a_version_folded_into_the_replay_key(self):
        provider = ProgrammableSearchProvider(CREDS)
        with_version = search_request(
            "q", provider=provider.name, max_results=5, version=provider.version
        )
        without = search_request("q", provider=provider.name, max_results=5)
        assert with_version.cassette_key() != without.cassette_key()

    def test_a_different_result_cap_is_a_different_recording(self):
        five = search_request("q", provider=PROVIDER_NAME, max_results=5)
        ten = search_request("q", provider=PROVIDER_NAME, max_results=10)
        assert five.cassette_key() != ten.cassette_key()

    def test_a_provider_without_a_version_keys_as_it_always_did(self):
        """Recordings made before `version` existed must stay replayable."""
        assert search_request("q", provider="fake", max_results=5).stage_version is None
        assert "options" not in search_request("q", provider="fake", max_results=5).payload


class TestBudgets:
    def test_the_total_call_budget_is_enforced(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return api_response([])

        provider = provider_for(handler, limits=SearchLimits(max_calls=2))
        provider.search(SearchCall(query="a"))
        provider.search(SearchCall(query="b"))
        with pytest.raises(SearchBudgetExceededError):
            provider.search(SearchCall(query="c"))

    def test_calls_made_is_reported(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return api_response([])

        provider = provider_for(handler)
        provider.search(SearchCall(query="a"))
        provider.search(SearchCall(query="b"))
        assert provider.calls_made == 2

    def test_a_failed_call_still_counts_against_the_budget(self):
        """Otherwise a failing provider could be retried without limit."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, json={"error": {"message": "boom"}})

        provider = provider_for(handler, limits=SearchLimits(max_calls=1))
        with pytest.raises(SearchProviderHTTPError):
            provider.search(SearchCall(query="a"))
        with pytest.raises(SearchBudgetExceededError):
            provider.search(SearchCall(query="b"))


class TestReplay:
    """A `REPLAY` run must make no provider call of any kind."""

    def _record(self, tmp_path, query="q"):
        def handler(request: httpx.Request) -> httpx.Response:
            return api_response([ITEM])

        store = CassetteStore(tmp_path)
        execute_search(
            SearchCall(query=query, max_results=5),
            provider=provider_for(handler),
            store=store,
            mode=RunMode.LIVE,
        )
        return store

    def test_replay_returns_the_recorded_results(self, tmp_path):
        store = self._record(tmp_path)
        results = execute_search(
            SearchCall(query="q", max_results=5),
            provider=provider_for(self._exploding_handler()),
            store=store,
            mode=RunMode.REPLAY,
        )
        assert [r.url for r in results] == [ITEM["link"]]

    def test_replay_touches_no_transport(self, tmp_path):
        """The mock transport raises if reached, so a live call cannot pass silently."""
        store = self._record(tmp_path)
        execute_search(
            SearchCall(query="q", max_results=5),
            provider=provider_for(self._exploding_handler()),
            store=store,
            mode=RunMode.REPLAY,
        )

    def test_a_replay_miss_fails_closed(self, tmp_path):
        store = self._record(tmp_path, query="recorded")
        with pytest.raises(ReplayMissError):
            execute_search(
                SearchCall(query="never recorded", max_results=5),
                provider=provider_for(self._exploding_handler()),
                store=store,
                mode=RunMode.REPLAY,
            )

    def test_a_replay_miss_does_not_fall_back_to_the_provider(self, tmp_path):
        """Fail-closed means fail, not "try live instead"."""
        store = self._record(tmp_path, query="recorded")
        provider = provider_for(self._exploding_handler())
        with pytest.raises(ReplayMissError):
            execute_search(
                SearchCall(query="different", max_results=5),
                provider=provider,
                store=store,
                mode=RunMode.REPLAY,
            )
        assert provider.calls_made == 0

    @staticmethod
    def _exploding_handler():
        def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
            raise AssertionError(f"REPLAY made a live call to {request.url.host}")

        return handler


class TestSnippetsAreNotEvidence:
    def test_a_snippet_containing_a_specification_stays_locator_metadata(self, tmp_path):
        """A perfect sentence in a snippet is still not something we may cite."""
        item = {
            "link": "https://download.se.com/x.pdf",
            "title": "LC1D18P7",
            "snippet": "Rated operational current Ie: 18 A.",
        }

        def handler(request: httpx.Request) -> httpx.Response:
            return api_response([item])

        results = execute_search(
            SearchCall(query="q", max_results=5),
            provider=provider_for(handler),
            store=CassetteStore(tmp_path),
            mode=RunMode.LIVE,
        )
        result = results[0]
        assert result.snippet == "Rated operational current Ie: 18 A."
        # The only fields a `SearchResult` has are locator metadata. There is nowhere on
        # it to put an attribute, a unit, or a citation, and the model forbids extras.
        assert set(result.model_dump()) == {
            "url",
            "title",
            "snippet",
            "rank",
            "query",
            "provider",
        }
