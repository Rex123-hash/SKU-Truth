"""Safe acquisition: URL policy, redirect revalidation, limits, content checks.

Every test here is offline. The HTTP transport is an `httpx.MockTransport` and the DNS
resolver is a plain function, both injected — so the real redirect loop, byte cap,
content-type allowlist, and PDF signature check all execute, without a socket ever
being opened.

This is SSRF-sensitive code. The tests are written from the attacker's side: each one
names a way to reach something the fetcher must not reach.
"""

from __future__ import annotations

import httpx
import pytest
from conftest_pdf import build_pdf
from skutruth.discovery import (
    FetchError,
    FetchPolicy,
    RejectionReason,
    fetch_url,
    validate_url,
)
from skutruth.discovery.fetch import USER_AGENT

PUBLIC_IP = "93.184.216.34"
PDF_BYTES = build_pdf(["hello"])


def public_resolver(host: str) -> list[str]:
    return [PUBLIC_IP]


def resolver_for(mapping: dict[str, list[str]]):
    def resolve(host: str) -> list[str]:
        return mapping.get(host, [PUBLIC_IP])

    return resolve


def transport_for(handler):
    return httpx.MockTransport(handler)


def pdf_response(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, content=PDF_BYTES, headers={"content-type": "application/pdf"})


def fetch(url: str, handler=pdf_response, *, policy=None, resolver=public_resolver):
    return fetch_url(
        url, policy=policy, transport=transport_for(handler), resolver=resolver
    )


class TestUrlPolicy:
    def test_https_is_accepted(self):
        """B."""
        assert validate_url("https://se.com/x.pdf", resolver=public_resolver) == "se.com"

    def test_http_is_accepted(self):
        """A. Plain http is allowed; many manufacturer PDF hosts still redirect via it."""
        assert validate_url("http://se.com/x.pdf", resolver=public_resolver) == "se.com"

    @pytest.mark.parametrize(
        "url",
        [
            "file:///etc/passwd",
            "ftp://example.com/x.pdf",
            "data:application/pdf;base64,AAAA",
            "javascript:alert(1)",
            "gopher://example.com/",
        ],
    )
    def test_non_http_schemes_are_refused(self, url):
        """C, D."""
        with pytest.raises(FetchError) as exc:
            validate_url(url, resolver=public_resolver)
        assert exc.value.reason is RejectionReason.UNSUPPORTED_SCHEME

    @pytest.mark.parametrize("url", ["https://", "http://:8080/x", "not-a-url"])
    def test_malformed_urls_are_refused(self, url):
        """AF."""
        with pytest.raises(FetchError) as exc:
            validate_url(url, resolver=public_resolver)
        assert exc.value.reason in {
            RejectionReason.MALFORMED_URL,
            RejectionReason.UNSUPPORTED_SCHEME,
        }

    @pytest.mark.parametrize("host", ["localhost", "api.localhost"])
    def test_localhost_is_refused(self, host):
        """E."""
        with pytest.raises(FetchError) as exc:
            validate_url(f"http://{host}/admin", resolver=public_resolver)
        assert exc.value.reason is RejectionReason.BLOCKED_HOST

    @pytest.mark.parametrize(
        "host",
        [
            "127.0.0.1",  # F
            "[::1]",  # G
            "10.0.0.5",  # H
            "192.168.1.1",  # H
            "172.16.0.1",  # H
            "169.254.169.254",  # I - cloud metadata
            "[fe80::1]",  # I
            "[fd00::1]",  # unique local
            "0.0.0.0",  # unspecified
            "224.0.0.1",  # multicast
        ],
    )
    def test_private_and_special_addresses_are_refused(self, host):
        """F, G, H, I."""
        with pytest.raises(FetchError) as exc:
            validate_url(f"http://{host}/x", resolver=public_resolver)
        assert exc.value.reason is RejectionReason.PRIVATE_ADDRESS

    def test_a_hostname_resolving_to_a_private_address_is_refused(self):
        """The rebind case: the name looks fine, the answer does not."""
        resolver = resolver_for({"internal.example": ["10.1.2.3"]})
        with pytest.raises(FetchError) as exc:
            validate_url("https://internal.example/x", resolver=resolver)
        assert exc.value.reason is RejectionReason.PRIVATE_ADDRESS

    def test_every_resolved_address_is_checked_not_just_the_first(self):
        """One public answer does not excuse a private one."""
        resolver = resolver_for({"split.example": [PUBLIC_IP, "127.0.0.1"]})
        with pytest.raises(FetchError) as exc:
            validate_url("https://split.example/x", resolver=resolver)
        assert exc.value.reason is RejectionReason.PRIVATE_ADDRESS

    def test_a_name_resolving_to_nothing_is_refused(self):
        with pytest.raises(FetchError) as exc:
            validate_url("https://nowhere.example/x", resolver=lambda host: [])
        assert exc.value.reason is RejectionReason.DNS_FAILURE

    def test_a_dns_failure_is_typed(self):
        def boom(host: str) -> list[str]:
            raise OSError("no such host")

        with pytest.raises(FetchError) as exc:
            validate_url("https://nowhere.example/x", resolver=boom)
        assert exc.value.reason is RejectionReason.DNS_FAILURE


class TestRedirects:
    def _redirect_to(self, target: str, *, status: int = 302):
        def handler(request: httpx.Request) -> httpx.Response:
            if str(request.url).endswith("/start"):
                return httpx.Response(status, headers={"location": target})
            return pdf_response(request)

        return handler

    def test_a_redirect_to_a_private_address_is_blocked(self):
        """J. The headline case: policy is re-applied at every hop."""
        handler = self._redirect_to("http://127.0.0.1/admin")
        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/start", handler)
        assert exc.value.reason is RejectionReason.PRIVATE_ADDRESS

    def test_a_redirect_to_a_private_hostname_is_blocked(self):
        """AH. Revalidation includes DNS, not just the literal host string."""
        handler = self._redirect_to("https://internal.example/secret")
        resolver = resolver_for({"internal.example": ["192.168.0.9"]})
        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/start", handler, resolver=resolver)
        assert exc.value.reason is RejectionReason.PRIVATE_ADDRESS

    def test_a_redirect_to_a_forbidden_scheme_is_blocked(self):
        handler = self._redirect_to("file:///etc/passwd")
        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/start", handler)
        assert exc.value.reason is RejectionReason.UNSUPPORTED_SCHEME

    def test_a_safe_redirect_is_followed_and_recorded(self):
        """Y. Both ends of the journey are retained."""
        handler = self._redirect_to("https://download.se.com/final.pdf")
        resource = fetch("https://se.com/start", handler)
        assert resource.requested_url == "https://se.com/start"
        assert resource.final_url == "https://download.se.com/final.pdf"
        assert resource.redirect_chain == (
            "https://se.com/start",
            "https://download.se.com/final.pdf",
        )

    def test_too_many_redirects_is_refused(self):
        """K."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302, headers={"location": "https://se.com/again"})

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/start", handler, policy=FetchPolicy(max_redirects=2))
        assert exc.value.reason is RejectionReason.TOO_MANY_REDIRECTS

    def test_a_redirect_without_a_location_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(302)

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/start", handler)
        assert exc.value.reason is RejectionReason.REDIRECT_BLOCKED

    def test_a_relative_redirect_resolves_against_the_current_url(self):
        handler = self._redirect_to("/files/final.pdf")
        resource = fetch("https://se.com/start", handler)
        assert resource.final_url == "https://se.com/files/final.pdf"


class TestLimitsAndContent:
    def test_an_oversized_response_is_refused(self):
        """L."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200, content=b"%PDF-" + b"x" * 5000, headers={"content-type": "application/pdf"}
            )

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/big.pdf", handler, policy=FetchPolicy(max_bytes=1000))
        assert exc.value.reason is RejectionReason.RESPONSE_TOO_LARGE

    @pytest.mark.parametrize(
        "content_type",
        ["application/zip", "image/png", "application/octet-stream", "", "text/csv"],
    )
    def test_unsupported_content_types_are_refused(self, content_type):
        """M."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"data", headers={"content-type": content_type})

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/x", handler)
        assert exc.value.reason is RejectionReason.UNSUPPORTED_CONTENT_TYPE

    def test_bytes_that_are_not_a_pdf_are_refused(self):
        """N. A content type is a claim; the signature is a check."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"<html>not a pdf at all</html>",
                headers={"content-type": "application/pdf"},
            )

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/fake.pdf", handler)
        assert exc.value.reason is RejectionReason.INVALID_PDF

    def test_an_empty_body_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"", headers={"content-type": "text/html"})

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/empty", handler)
        assert exc.value.reason is RejectionReason.CONTENT_INTEGRITY_ERROR

    def test_a_timeout_is_a_typed_failure(self):
        """O."""

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("too slow", request=request)

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/slow.pdf", handler)
        assert exc.value.reason is RejectionReason.TIMEOUT

    def test_a_transport_failure_is_a_typed_failure(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("refused", request=request)

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/x.pdf", handler)
        assert exc.value.reason is RejectionReason.TRANSPORT_ERROR

    @pytest.mark.parametrize("status", [400, 403, 404, 500, 503])
    def test_http_errors_are_typed_failures(self, status):
        """P."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(status, content=b"nope", headers={"content-type": "text/html"})

        with pytest.raises(FetchError) as exc:
            fetch("https://se.com/x.pdf", handler)
        assert exc.value.reason is RejectionReason.HTTP_ERROR

    def test_html_is_fetched_and_hashed(self):
        """Discoverable even though this milestone does not ingest it."""

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                content=b"<html><body>page</body></html>",
                headers={"content-type": "text/html"},
            )

        resource = fetch("https://se.com/product/", handler)
        assert resource.is_html is True
        assert len(resource.sha256) == 64


class TestFetchedResource:
    def test_a_successful_fetch_carries_its_lineage(self):
        resource = fetch("https://se.com/x.pdf")
        assert resource.is_pdf is True
        assert resource.status_code == 200
        assert resource.byte_size == len(PDF_BYTES)
        assert resource.sha256 == __import__("hashlib").sha256(PDF_BYTES).hexdigest()
        assert resource.fetched_at.tzinfo is not None

    def test_identical_bytes_from_two_urls_hash_identically(self):
        """X. The dedupe key."""
        first = fetch("https://se.com/a.pdf")
        second = fetch("https://download.se.com/b.pdf")
        assert first.sha256 == second.sha256
        assert first.final_url != second.final_url

    def test_the_user_agent_is_honest_and_not_a_browser(self):
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return pdf_response(request)

        fetch("https://se.com/x.pdf", handler)
        agent = seen["user-agent"]
        assert agent == USER_AGENT
        assert "SKUTruth" in agent
        for impersonation in ("Mozilla", "Chrome", "Safari", "Googlebot"):
            assert impersonation not in agent

    def test_no_authorization_header_is_sent(self):
        """AG-adjacent: nothing this fetcher sends carries a credential."""
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen.update(request.headers)
            return pdf_response(request)

        fetch("https://se.com/x.pdf", handler)
        for header in ("authorization", "cookie", "proxy-authorization"):
            assert header not in seen
