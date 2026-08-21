"""Manual official-source intake through existing trust gates, entirely offline."""

from __future__ import annotations

import socket

import httpx
import pytest
from conftest_pdf import build_pdf
from skutruth.contracts import DiscoveryMethod
from skutruth.discovery import (
    MANUAL_SOURCE_PROVIDER,
    AgentSearchProvider,
    CandidateStatus,
    ManualLocatorKind,
    ManualSourceInput,
    ManualSourceMode,
    MpnRelevance,
    RejectionReason,
    SourceAuthority,
    ingest_manual_source,
    parse_registry,
    plan_manual_source,
)
from skutruth.discovery.agent_search import PROVIDER_NAME
from skutruth.discovery.models import DiscoveryRequest
from skutruth.ingest.storage import ArtifactStore

MPN = "45297BK"
MANUFACTURER = "Kichler Lighting"
PUBLIC_IP = "93.184.216.34"

# Synthetic/test-only. This has not been observed on the live Kichler site.
OFFICIAL_FIXTURE_URL = (
    "https://www.kichler.com/test-only/manual-source/45297BK-spec.pdf"
)

REVIEW = {
    "reviewed_at": "2026-08-21",
    "reviewed_by": "fixture-reviewer",
    "basis": "synthetic test review; no live domain lookup was performed",
}

PDF_BYTES = build_pdf(["SYNTHETIC TEST DOCUMENT", MPN])


def registry(*, reviewed: bool = True):
    manufacturer = {
        "key": "kichler-lighting",
        "authority_hints": [MANUFACTURER, "Kichler"],
        "domains": ["kichler.com"],
    }
    if reviewed:
        manufacturer["review"] = REVIEW
    return parse_registry(
        {
            "name": "synthetic-manual-source-test",
            "authority": "REVIEWED",
            "manufacturer": [manufacturer],
            "hosts": {
                "distributors": ["distributor.example"],
                "marketplaces": ["marketplace.example"],
            },
        },
        source="synthetic test registry",
    )


def manual_source(
    url: str = OFFICIAL_FIXTURE_URL,
    *,
    mpn: str = MPN,
    manufacturer: str = MANUFACTURER,
    note: str = "synthetic test-only locator",
) -> ManualSourceInput:
    return ManualSourceInput(
        request=DiscoveryRequest(
            mpn=mpn,
            raw_mpn=mpn,
            manufacturer_hint=manufacturer,
            manufacturer_code="KICLI",
            description="synthetic lighting fixture",
            row_number=17,
        ),
        url=url,
        note=note,
    )


def public_resolver(_host: str) -> list[str]:
    return [PUBLIC_IP]


def pdf_transport(*, redirect_to: str | None = None):
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if redirect_to and len(calls) == 1:
            return httpx.Response(302, headers={"location": redirect_to})
        return httpx.Response(
            200,
            content=PDF_BYTES,
            headers={"content-type": "application/pdf"},
        )

    return httpx.MockTransport(handler), calls


def test_reviewed_kichler_exact_manual_locator_is_acquisition_eligible():
    result = plan_manual_source(manual_source(), registry=registry())
    assert result.locator_kind is ManualLocatorKind.MANUAL
    assert result.mode is ManualSourceMode.DRY_RUN
    assert result.manufacturer_key == "kichler-lighting"
    assert result.domain_review is not None
    assert result.input_host == "kichler.com"
    assert result.candidate.authority is SourceAuthority.APPROVED_MANUFACTURER
    assert result.candidate.relevance is MpnRelevance.EXACT
    assert result.candidate.status is CandidateStatus.ACCEPTED_NOT_ACQUIRED
    assert result.acquisition_would_be_attempted is True


def test_distributor_url_cannot_gain_manufacturer_authority():
    url = f"https://distributor.example/products/{MPN}.pdf"
    result = plan_manual_source(manual_source(url), registry=registry())
    assert result.candidate.authority is SourceAuthority.KNOWN_DISTRIBUTOR
    assert result.candidate.relevance is MpnRelevance.EXACT
    assert RejectionReason.DISTRIBUTOR_SOURCE.value in result.candidate.rejections
    assert result.acquisition_would_be_attempted is False


def test_unreviewed_manufacturer_binding_cannot_proceed():
    result = plan_manual_source(manual_source(), registry=registry(reviewed=False))
    assert result.candidate.authority is SourceAuthority.UNVERIFIED_MANUFACTURER
    assert RejectionReason.AUTHORITY_NOT_ESTABLISHED.value in result.candidate.rejections
    assert result.domain_review is None
    assert result.acquisition_would_be_attempted is False


def test_manual_input_never_creates_or_changes_domain_review():
    domains = registry(reviewed=False)
    before = domains.entries
    plan_manual_source(manual_source(), registry=domains)
    assert domains.entries == before
    assert domains.entries[0].review is None
    assert domains.licensing_entries == ()


def test_entered_mpn_and_note_do_not_automatically_establish_exact_relevance():
    source = manual_source(
        "https://www.kichler.com/test-only/manual-source/product-page",
        note=f"operator says this is {MPN}",
    )
    result = plan_manual_source(source, registry=registry())
    assert result.source.note.endswith(MPN)
    assert result.candidate.result.title == ""
    assert result.candidate.result.snippet == ""
    assert result.candidate.relevance is MpnRelevance.ABSENT
    assert RejectionReason.MPN_ABSENT.value in result.candidate.rejections
    assert result.acquisition_would_be_attempted is False


@pytest.mark.parametrize(
    ("url", "expected", "reason"),
    [
        (
            "https://www.kichler.com/test-only/45297/",
            MpnRelevance.FAMILY_ONLY,
            RejectionReason.FAMILY_ONLY,
        ),
        (
            "https://www.kichler.com/test-only/45297WH/",
            MpnRelevance.SIBLING,
            RejectionReason.SIBLING_REFERENCE,
        ),
        (
            "https://www.kichler.com/test-only/45297WH-vs-45297NI/",
            MpnRelevance.AMBIGUOUS,
            RejectionReason.AMBIGUOUS_REFERENCE,
        ),
        (
            "https://www.kichler.com/test-only/unrelated/",
            MpnRelevance.ABSENT,
            RejectionReason.MPN_ABSENT,
        ),
    ],
)
def test_non_exact_locator_relevance_states_remain_blocked(url, expected, reason):
    result = plan_manual_source(manual_source(url), registry=registry())
    assert result.candidate.relevance is expected
    assert reason.value in result.candidate.rejections
    assert result.acquisition_would_be_attempted is False


def test_exact_reviewed_pdf_uses_shared_acquisition_and_artifact_store(tmp_path):
    transport, calls = pdf_transport()
    store = ArtifactStore(tmp_path / "artifacts")
    result = ingest_manual_source(
        manual_source(),
        registry=registry(),
        store=store,
        transport=transport,
        resolver=public_resolver,
    )
    assert calls == [OFFICIAL_FIXTURE_URL]
    assert result.network_attempted is True
    assert result.candidate.status is CandidateStatus.ACQUIRED
    assert result.artifact_sha256 in store.hashes()
    assert result.bytes_downloaded == len(PDF_BYTES)


def test_redirect_to_distributor_loses_manufacturer_authority(tmp_path):
    target = f"https://distributor.example/files/{MPN}.pdf"
    transport, calls = pdf_transport(redirect_to=target)
    store = ArtifactStore(tmp_path / "artifacts")
    result = ingest_manual_source(
        manual_source(),
        registry=registry(),
        store=store,
        transport=transport,
        resolver=public_resolver,
    )
    assert calls == [OFFICIAL_FIXTURE_URL, target]
    assert result.candidate.final_authority is SourceAuthority.KNOWN_DISTRIBUTOR
    assert result.candidate.status is CandidateStatus.REJECTED
    assert RejectionReason.REDIRECT_AUTHORITY_LOST.value in result.candidate.rejections
    assert store.hashes() == ()


@pytest.mark.parametrize(
    ("url", "reason"),
    [
        (f"ftp://www.kichler.com/files/{MPN}.pdf", RejectionReason.UNSUPPORTED_SCHEME),
        (f"http://localhost/files/{MPN}.pdf", RejectionReason.BLOCKED_HOST),
        (f"http://127.0.0.1/files/{MPN}.pdf", RejectionReason.PRIVATE_ADDRESS),
    ],
)
def test_static_unsafe_urls_are_blocked_without_network(url, reason):
    result = plan_manual_source(manual_source(url), registry=registry())
    assert result.static_url_valid is False
    assert reason.value in result.candidate.rejections
    assert result.acquisition_would_be_attempted is False
    assert result.network_attempted is False


def test_live_dns_to_private_network_is_blocked_before_http(tmp_path):
    transport, calls = pdf_transport()
    result = ingest_manual_source(
        manual_source(),
        registry=registry(),
        store=ArtifactStore(tmp_path / "artifacts"),
        transport=transport,
        resolver=lambda _host: ["10.0.0.7"],
    )
    assert result.candidate.status is CandidateStatus.REJECTED
    assert RejectionReason.PRIVATE_ADDRESS.value in result.candidate.rejections
    assert calls == []


def test_manual_provenance_survives_into_artifact_metadata(tmp_path):
    transport, _ = pdf_transport()
    store = ArtifactStore(tmp_path / "artifacts")
    result = ingest_manual_source(
        manual_source(),
        registry=registry(),
        store=store,
        transport=transport,
        resolver=public_resolver,
    )
    stored = store.load(result.artifact_sha256)
    assert result.locator_kind is ManualLocatorKind.MANUAL
    assert result.candidate.result.provider == MANUAL_SOURCE_PROVIDER
    assert stored.source.discovery_method is DiscoveryMethod.OPERATOR_SUPPLIED
    assert stored.source.discovery_url == OFFICIAL_FIXTURE_URL
    assert stored.source.final_artifact_url == OFFICIAL_FIXTURE_URL
    assert stored.source.identity_scope is None
    assert stored.source.covers_mpn is None


def test_official_html_locator_is_ingested_with_manual_provenance(tmp_path):
    url = f"https://www.kichler.com/test-only/products/{MPN}"

    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=b"<html><body>synthetic fixture</body></html>",
            headers={"content-type": "text/html"},
        )

    store = ArtifactStore(tmp_path / "artifacts")
    result = ingest_manual_source(
        manual_source(url),
        registry=registry(),
        store=store,
        transport=httpx.MockTransport(html),
        resolver=public_resolver,
    )
    assert result.candidate.status is CandidateStatus.ACQUIRED
    assert result.candidate.content_type == "text/html"
    assert result.candidate.rejections == ()
    stored = store.load(result.artifact_sha256)
    assert stored.artifact_kind.value == "HTML"
    assert stored.sha256 == result.artifact_sha256
    assert stored.byte_size == len(b"<html><body>synthetic fixture</body></html>")
    assert stored.media_type == "text/html"
    assert stored.final_authority == SourceAuthority.APPROVED_MANUFACTURER.value
    assert stored.source.publisher == MANUFACTURER
    assert stored.source.discovery_url == url
    assert stored.source.final_artifact_url == url
    assert stored.source.retrieved_at is not None
    assert stored.source.discovery_method is DiscoveryMethod.OPERATOR_SUPPLIED
    assert stored.source.identity_scope is None
    assert stored.source.covers_mpn is None


def test_dry_run_performs_no_dns_http_or_acquisition(monkeypatch):
    def no_dns(*_args, **_kwargs):
        raise AssertionError("DNS was called during dry-run")

    def no_acquisition(*_args, **_kwargs):
        raise AssertionError("acquisition was called during dry-run")

    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    monkeypatch.setattr("skutruth.discovery.manual.acquire_candidate", no_acquisition)
    result = plan_manual_source(manual_source(), registry=registry())
    assert result.acquisition_would_be_attempted is True
    assert result.dns_check_deferred is True
    assert result.network_attempted is False


def test_agent_search_provider_contract_is_unchanged():
    assert AgentSearchProvider.discovery_method is DiscoveryMethod.SITE_RESTRICTED_SEARCH
    assert MANUAL_SOURCE_PROVIDER != PROVIDER_NAME
