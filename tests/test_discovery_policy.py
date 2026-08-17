"""Discovery policy: whose site, which product, and how candidates rank.

Everything is synthetic. No network, no search provider, no organizer file.

The tests that matter most are the refusals. Finding a manufacturer's datasheet is the
easy half; the milestone is only worth anything if a marketplace listing, a lookalike
domain, and a sibling part number reliably fail to become manufacturer evidence.
"""

from __future__ import annotations

import pytest
from skutruth.discovery import (
    DiscoveryRequest,
    MpnRelevance,
    SearchResult,
    SourceAuthority,
    SourceKind,
    build_queries,
    classify_authority,
    classify_candidate,
    classify_kind,
    classify_relevance,
    host_covered_by,
    load_registry,
    normalize_host,
    normalize_manufacturer,
    parse_registry,
    rank_candidates,
)
from skutruth.discovery.domains import RegistryAuthority
from skutruth.discovery.errors import MalformedRegistryError, RejectionReason
from skutruth.discovery.query import QueryBudget

MPN = "LC1D18P7"
MAKER = "Schneider Electric"


def registry():
    return parse_registry(
        {
            "name": "test",
            "authority": "DEMO",
            "manufacturer": [
                {
                    "key": "schneider",
                    "hints": ["Schneider Electric", "Schneider"],
                    "domains": ["se.com", "schneider-electric.com"],
                },
                {"key": "acme", "hints": ["Acme Corp"], "domains": ["acme.example"]},
            ],
            "hosts": {
                "marketplaces": ["amazon.com", "ebay.com"],
                "distributors": ["grainger.com", "rs-online.com"],
                "blocked": ["alldatasheet.com"],
            },
        }
    )


def result(url: str, *, title: str = "", rank: int = 1, snippet: str = "") -> SearchResult:
    return SearchResult(
        url=url, title=title, snippet=snippet, rank=rank, query="q", provider="fake"
    )


def request(mpn: str = MPN, maker: str | None = MAKER) -> DiscoveryRequest:
    return DiscoveryRequest(mpn=mpn, manufacturer_hint=maker)


class TestHostNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("SE.com", "se.com"),
            ("www.se.com", "se.com"),
            ("se.com.", "se.com"),
            ("  Download.SE.com ", "download.se.com"),
            (None, ""),
        ],
    )
    def test_hosts_normalise(self, raw, expected):
        assert normalize_host(raw) == expected

    @pytest.mark.parametrize(
        ("host", "domain", "covered"),
        [
            ("se.com", "se.com", True),
            ("download.se.com", "se.com", True),
            ("www.se.com", "se.com", True),
            # The attack a bare endswith would admit.
            ("se.com.evil.example", "se.com", False),
            ("notse.com", "se.com", False),
            ("evilse.com", "se.com", False),
        ],
    )
    def test_subdomain_matching_is_label_aware(self, host, domain, covered):
        assert host_covered_by(host, domain) is covered

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("Schneider Electric", "schneider electric"),
            ("SCHNEIDER ELECTRIC, INC.", "schneider electric"),
            ("Makita Usa Inc", "makita"),
            ("Black & Decker", "black decker"),
            (None, ""),
        ],
    )
    def test_manufacturer_names_fold_case_punctuation_and_suffixes(self, raw, expected):
        assert normalize_manufacturer(raw) == expected


class TestAuthority:
    def test_approved_manufacturer_host(self):
        assert (
            classify_authority("se.com", registry=registry(), manufacturer_hint=MAKER)
            is SourceAuthority.APPROVED_MANUFACTURER
        )

    def test_subdomain_of_an_approved_host(self):
        assert (
            classify_authority("download.se.com", registry=registry(), manufacturer_hint=MAKER)
            is SourceAuthority.APPROVED_MANUFACTURER
        )

    def test_a_domain_approved_for_someone_else_is_not_authoritative_here(self):
        """A Schneider domain says nothing authoritative about an Acme part."""
        assert (
            classify_authority("se.com", registry=registry(), manufacturer_hint="Acme Corp")
            is SourceAuthority.OTHER_MANUFACTURER
        )

    @pytest.mark.parametrize(
        ("host", "expected"),
        [
            ("amazon.com", SourceAuthority.KNOWN_MARKETPLACE),
            ("grainger.com", SourceAuthority.KNOWN_DISTRIBUTOR),
            ("alldatasheet.com", SourceAuthority.BLOCKED),
            ("some-random-blog.example", SourceAuthority.UNKNOWN),
        ],
    )
    def test_non_manufacturer_hosts(self, host, expected):
        assert classify_authority(host, registry=registry(), manufacturer_hint=MAKER) is expected

    def test_a_lookalike_hostname_is_not_the_manufacturer(self):
        """The whole reason authority is configuration rather than string similarity."""
        for host in (
            "schneider-electric-superstore.example",
            "se-com.example",
            "buy-schneider.example",
        ):
            assert (
                classify_authority(host, registry=registry(), manufacturer_hint=MAKER)
                is SourceAuthority.UNKNOWN
            )

    def test_only_approved_manufacturer_may_license_evidence(self):
        for authority in SourceAuthority:
            expected = authority is SourceAuthority.APPROVED_MANUFACTURER
            assert authority.may_license_evidence is expected


class TestMpnRelevance:
    def test_exact_reference_in_the_url(self):
        assert classify_relevance(result(f"https://se.com/p/{MPN}/"), mpn=MPN) is MpnRelevance.EXACT

    def test_exact_reference_in_the_title(self):
        found = result("https://se.com/p/12345/", title=f"TeSys {MPN} contactor")
        assert classify_relevance(found, mpn=MPN) is MpnRelevance.EXACT

    def test_case_and_separators_do_not_defeat_an_exact_match(self):
        found = result("https://se.com/product/lc1d18p7-datasheet.pdf")
        assert classify_relevance(found, mpn=MPN) is MpnRelevance.EXACT

    def test_a_family_stem_is_not_its_own_child(self):
        """V. LC1D18 must never stand in for LC1D18P7."""
        found = result("https://se.com/range/LC1D18/", title="TeSys LC1D18 range")
        assert classify_relevance(found, mpn=MPN) is MpnRelevance.FAMILY_ONLY

    def test_a_sibling_reference_is_not_the_target(self):
        found = result("https://se.com/p/LC1D18B7/", title="LC1D18B7 contactor")
        assert classify_relevance(found, mpn=MPN) is MpnRelevance.SIBLING

    def test_several_diverging_siblings_are_ambiguous(self):
        found = result("https://se.com/compare/", title="LC1D18B7 vs LC1D18M7 vs LC1D18F7")
        assert classify_relevance(found, mpn=MPN) is MpnRelevance.AMBIGUOUS

    def test_an_unrelated_page_is_absent(self):
        found = result("https://se.com/about/", title="About Schneider Electric")
        assert classify_relevance(found, mpn=MPN) is MpnRelevance.ABSENT

    def test_the_snippet_is_never_consulted(self):
        """S. A provider's summary text cannot decide what a page is about."""
        found = result(
            "https://se.com/about/",
            title="About us",
            snippet=f"{MPN} 18 A contactor rated 440 V",
        )
        assert classify_relevance(found, mpn=MPN) is MpnRelevance.ABSENT

    def test_a_short_coincidental_overlap_is_not_a_family(self):
        found = result("https://se.com/p/LC1X/", title="LC1X")
        assert classify_relevance(found, mpn=MPN) is MpnRelevance.ABSENT


class TestSourceKind:
    @pytest.mark.parametrize(
        ("url", "title", "expected"),
        [
            ("https://se.com/files/LC1D18P7_datasheet.pdf", "", SourceKind.DATASHEET),
            ("https://se.com/files/x.pdf", "", SourceKind.DATASHEET),
            ("https://se.com/files/B8-Contactors_catalogue.pdf", "", SourceKind.CATALOG),
            ("https://se.com/product/LC1D18P7/", "", SourceKind.PRODUCT_PAGE),
            ("https://se.com/files/install-manual", "", SourceKind.MANUAL),
            ("https://se.com/x", "", SourceKind.UNKNOWN),
        ],
    )
    def test_kinds(self, url, title, expected):
        assert classify_kind(result(url, title=title)) is expected


class TestCandidateClassification:
    def test_an_official_exact_candidate_is_eligible(self):
        candidate = classify_candidate(
            result(f"https://se.com/p/{MPN}/"), request=request(), registry=registry()
        )
        assert candidate.is_eligible is True
        assert candidate.rejections == ()

    def test_a_marketplace_exact_candidate_is_refused(self):
        """R."""
        candidate = classify_candidate(
            result(f"https://amazon.com/dp/{MPN}"), request=request(), registry=registry()
        )
        assert candidate.is_eligible is False
        assert RejectionReason.MARKETPLACE_SOURCE.value in candidate.rejections

    def test_a_distributor_exact_candidate_is_refused(self):
        """Q."""
        candidate = classify_candidate(
            result(f"https://grainger.com/p/{MPN}"), request=request(), registry=registry()
        )
        assert RejectionReason.DISTRIBUTOR_SOURCE.value in candidate.rejections

    def test_an_official_family_candidate_is_refused(self):
        candidate = classify_candidate(
            result("https://se.com/range/LC1D18/"), request=request(), registry=registry()
        )
        assert RejectionReason.FAMILY_ONLY.value in candidate.rejections

    def test_both_problems_are_reported(self):
        candidate = classify_candidate(
            result("https://amazon.com/dp/LC1D18B7"), request=request(), registry=registry()
        )
        assert set(candidate.rejections) == {
            RejectionReason.MARKETPLACE_SOURCE.value,
            RejectionReason.SIBLING_REFERENCE.value,
        }

    def test_rank_reasons_are_recorded(self):
        candidate = classify_candidate(
            result(f"https://se.com/p/{MPN}/"), request=request(), registry=registry()
        )
        assert any("authority=" in r for r in candidate.rank_reasons)


class TestRanking:
    def _rank(self, *results):
        return rank_candidates(
            [classify_candidate(r, request=request(), registry=registry()) for r in results]
        )

    def test_official_exact_outranks_third_party_exact(self):
        """T. Even when the search engine put the third party first."""
        ranked = self._rank(
            result(f"https://amazon.com/dp/{MPN}", rank=1),
            result(f"https://grainger.com/p/{MPN}", rank=2),
            result(f"https://se.com/p/{MPN}/", rank=9),
        )
        assert ranked[0].host == "se.com"

    def test_exact_outranks_sibling_on_the_same_authority(self):
        """U."""
        ranked = self._rank(
            result("https://se.com/p/LC1D18B7/", rank=1),
            result(f"https://se.com/p/{MPN}/", rank=8),
        )
        assert ranked[0].relevance is MpnRelevance.EXACT

    def test_provider_rank_alone_cannot_override_authority(self):
        """AB."""
        ranked = self._rank(
            result(f"https://amazon.com/dp/{MPN}", rank=1),
            result(f"https://se.com/p/{MPN}/", rank=99),
        )
        assert ranked[0].authority is SourceAuthority.APPROVED_MANUFACTURER

    def test_a_datasheet_outranks_a_product_page_at_equal_authority(self):
        ranked = self._rank(
            result(f"https://se.com/product/{MPN}/", rank=1),
            result(f"https://se.com/files/{MPN}_datasheet.pdf", rank=2),
        )
        assert ranked[0].kind is SourceKind.DATASHEET

    def test_ordering_is_independent_of_input_order(self):
        results = [
            result(f"https://amazon.com/dp/{MPN}", rank=1),
            result(f"https://se.com/p/{MPN}/", rank=2),
            result("https://se.com/range/LC1D18/", rank=3),
        ]
        assert [c.url for c in self._rank(*results)] == [
            c.url for c in self._rank(*reversed(results))
        ]


class TestQueryConstruction:
    def test_queries_are_deterministic(self):
        first = build_queries(request(), approved_domains=("se.com",))
        second = build_queries(request(), approved_domains=("se.com",))
        assert first == second

    def test_site_queries_come_first_when_domains_are_known(self):
        queries = build_queries(request(), approved_domains=("se.com", "schneider-electric.com"))
        assert queries[0] == f'"{MPN}" site:se.com'

    def test_the_reference_is_always_quoted(self):
        assert all(f'"{MPN}"' in q for q in build_queries(request()))

    def test_budgets_bound_the_query_count(self):
        """AE."""
        queries = build_queries(
            request(),
            approved_domains=("a.example", "b.example", "c.example"),
            budget=QueryBudget(max_queries=2, max_site_queries=3),
        )
        assert len(queries) == 2

    def test_quotes_in_input_are_stripped_not_escaped(self):
        queries = build_queries(DiscoveryRequest(mpn='AB"CD', manufacturer_hint="X"))
        assert all('"AB CD"' in q for q in queries)

    def test_an_empty_reference_yields_no_queries(self):
        assert build_queries(DiscoveryRequest(mpn="   ")) == ()

    def test_queries_are_deduplicated(self):
        queries = build_queries(request(maker="datasheet"))
        assert len(queries) == len(set(queries))


class TestRegistryLoading:
    def test_the_committed_demo_registry_loads_and_is_not_authoritative(self):
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[1]
            / "data"
            / "discovery"
            / "manufacturer_domains.demo.toml"
        )
        loaded = load_registry(path)
        assert loaded.authority is RegistryAuthority.REVIEWED
        assert loaded.is_authoritative is False
        assert loaded.owner_of("download.se.com") is not None

    def test_a_missing_authority_is_rejected(self):
        with pytest.raises(MalformedRegistryError, match="must declare"):
            parse_registry({"name": "x", "manufacturer": []})

    def test_a_duplicate_manufacturer_key_is_rejected(self):
        with pytest.raises(MalformedRegistryError, match="appears twice"):
            parse_registry(
                {
                    "name": "x",
                    "authority": "DEMO",
                    "manufacturer": [
                        {"key": "a", "domains": ["a.example"]},
                        {"key": "a", "domains": ["b.example"]},
                    ],
                }
            )

    def test_an_entry_without_domains_is_rejected(self):
        with pytest.raises(MalformedRegistryError, match="needs `key` and `domains`"):
            parse_registry({"name": "x", "authority": "DEMO", "manufacturer": [{"key": "a"}]})

    def test_a_missing_file_is_reported(self, tmp_path):
        with pytest.raises(MalformedRegistryError, match="no domain registry"):
            load_registry(tmp_path / "absent.toml")

    def test_an_unmatched_hint_yields_no_domains(self):
        """No nearest match, ever."""
        assert registry().domains_for_hint("Totally Unknown Maker") == ()

    def test_only_an_official_registry_is_authoritative(self):
        for authority in RegistryAuthority:
            expected = authority is RegistryAuthority.OFFICIAL
            assert authority.is_authoritative is expected
