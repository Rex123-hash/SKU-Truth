"""Fetching a URL safely. This is SSRF-sensitive code and fails closed.

Everything discovery downloads was named by a search engine, which means the URL is
attacker-influenceable in the ordinary case, not the exotic one. A fetcher that will
retrieve any URL handed to it is a request-forgery gadget pointed at whatever network the
process happens to sit inside.

## What is enforced

* `http` and `https` only. `file:`, `ftp:`, `data:`, `javascript:` and everything else
  are refused before a socket exists.
* Every hostname is resolved and **every** resulting address is checked. One public
  address is not enough if another resolves to loopback.
* Loopback, private, link-local, unique-local, multicast, reserved, and unspecified
  addresses are refused, for both IPv4 and IPv6.
* Redirects are followed manually, one hop at a time, and the full policy — scheme, host,
  DNS, address ranges — is re-applied at **every** hop. A public URL redirecting to
  `http://127.0.0.1/admin` fails on the second hop.
* Redirect count, connect timeout, read timeout, and response size are all bounded. The
  body is read in chunks and abandoned the moment it exceeds the cap, so an endless
  response cannot exhaust memory.
* Only declared content types are accepted, and a response claiming `application/pdf`
  must actually begin with `%PDF-`.
* No credentials are sent, and no header is carried across a redirect to another host.

## What is NOT enforced, stated plainly

**DNS is not pinned.** Addresses are resolved and validated, and then httpx resolves the
hostname again when it opens the connection. A name that returns a public address to our
preflight and a private one microseconds later would defeat the check. Closing that
window means connecting to a validated IP directly while preserving SNI and certificate
verification against the original hostname, which httpx does not expose cleanly.

The residual risk is a same-name DNS rebind inside a sub-second window against a host a
search engine returned. That is documented here rather than mitigated, because claiming a
protection the code does not implement is worse than the gap itself. It is the first thing
to fix if discovery is ever pointed at untrusted input at scale.

## No browser

Nothing here executes JavaScript, loads sub-resources, or follows `<meta>` refreshes. A
PDF is bytes; an HTML page is bytes we may hash and record, and this milestone does not
interpret them.
"""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlsplit

import httpx

from skutruth.ingest.hashing import sha256_bytes
from skutruth.ingest.limits import PDF_MAGIC

from .errors import FetchError, RejectionReason

#: Bumped when a change here could alter what is downloadable.
ACQUISITION_VERSION = "source-acquisition@v1"

#: Honest, contactable, and not pretending to be a browser.
USER_AGENT = "SKUTruth/0.1 (product-data verification; +https://github.com/Rex123-hash/SKU-Truth)"

ALLOWED_SCHEMES = frozenset({"http", "https"})

PDF_CONTENT_TYPES = frozenset({"application/pdf", "application/x-pdf"})
HTML_CONTENT_TYPES = frozenset({"text/html", "application/xhtml+xml"})

#: Resolves a hostname to address strings. Injected so tests never touch DNS.
Resolver = Callable[[str], list[str]]


def system_resolver(host: str) -> list[str]:
    """Every address a hostname resolves to, IPv4 and IPv6."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [info[4][0] for info in infos]


@dataclass(frozen=True, slots=True)
class FetchPolicy:
    """Bounds for one acquisition. Every field is a refusal threshold."""

    #: 25 MB. Comfortably above a large family catalogue, far below a runaway download.
    max_bytes: int = 25 * 1024 * 1024
    max_redirects: int = 5
    connect_timeout: float = 10.0
    read_timeout: float = 30.0
    accepted_content_types: frozenset[str] = field(
        default_factory=lambda: PDF_CONTENT_TYPES | HTML_CONTENT_TYPES
    )


@dataclass(frozen=True, slots=True)
class FetchedResource:
    """Bytes we actually downloaded, with the lineage needed to defend them."""

    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    status_code: int
    content_type: str
    body: bytes
    sha256: str
    fetched_at: datetime

    @property
    def byte_size(self) -> int:
        return len(self.body)

    @property
    def is_pdf(self) -> bool:
        return self.content_type in PDF_CONTENT_TYPES

    @property
    def is_html(self) -> bool:
        return self.content_type in HTML_CONTENT_TYPES


def _refuse(reason: RejectionReason, detail: str) -> FetchError:
    return FetchError(reason, detail)


def _check_address(raw: str, *, host: str) -> None:
    """Refuse any address that is not ordinary public unicast."""
    try:
        address = ipaddress.ip_address(raw)
    except ValueError as exc:  # pragma: no cover - resolver returned a non-address
        raise _refuse(RejectionReason.DNS_FAILURE, f"{host!r} resolved to {raw!r}") from exc

    disqualifying = (
        ("loopback", address.is_loopback),
        ("private", address.is_private),
        ("link-local", address.is_link_local),
        ("multicast", address.is_multicast),
        ("reserved", address.is_reserved),
        ("unspecified", address.is_unspecified),
    )
    for label, hit in disqualifying:
        if hit:
            raise _refuse(
                RejectionReason.PRIVATE_ADDRESS,
                f"{host!r} resolves to {raw} which is {label}",
            )


def validate_url(url: str, *, resolver: Resolver = system_resolver) -> str:
    """Check scheme, host, and every resolved address. Returns the normalized host.

    Raises `FetchError` with a typed reason rather than returning a boolean, so a caller
    cannot forget to look at the answer.
    """
    try:
        parts = urlsplit(url)
    except ValueError as exc:
        raise _refuse(RejectionReason.MALFORMED_URL, f"{url!r} cannot be parsed") from exc

    scheme = (parts.scheme or "").lower()
    if scheme not in ALLOWED_SCHEMES:
        raise _refuse(
            RejectionReason.UNSUPPORTED_SCHEME,
            f"{scheme or 'missing'!r} is not http or https",
        )

    try:
        host = parts.hostname
    except ValueError as exc:
        raise _refuse(RejectionReason.MALFORMED_URL, f"{url!r} has an unusable host") from exc
    if not host:
        raise _refuse(RejectionReason.MALFORMED_URL, f"{url!r} names no host")

    host = host.lower()
    if host == "localhost" or host.endswith(".localhost"):
        raise _refuse(RejectionReason.BLOCKED_HOST, "localhost is not fetchable")

    # An IP literal is checked directly; a name is resolved and every answer checked.
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            addresses = resolver(host)
        except OSError as exc:
            raise _refuse(RejectionReason.DNS_FAILURE, f"{host!r} did not resolve: {exc}") from exc
        if not addresses:
            raise _refuse(
                RejectionReason.DNS_FAILURE, f"{host!r} resolved to nothing"
            ) from None
        for address in addresses:
            _check_address(address, host=host)
    else:
        _check_address(host, host=host)

    return host


def _content_type_of(response: httpx.Response) -> str:
    return (response.headers.get("content-type") or "").split(";")[0].strip().lower()


def _read_bounded(response: httpx.Response, *, limit: int, url: str) -> bytes:
    """Read the body, abandoning it the moment it exceeds the cap."""
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > limit:
            raise _refuse(
                RejectionReason.RESPONSE_TOO_LARGE,
                f"{url} exceeded {limit} bytes",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def fetch_url(
    url: str,
    *,
    policy: FetchPolicy | None = None,
    transport: httpx.BaseTransport | None = None,
    resolver: Resolver = system_resolver,
) -> FetchedResource:
    """Download one URL under the full policy. Raises `FetchError` on any refusal.

    `transport` is injected so tests exercise the real redirect, limit, and content-type
    logic without a network. `resolver` is injected for the same reason: a committed test
    must not depend on DNS either.
    """
    limits = policy or FetchPolicy()
    current = url
    chain: list[str] = []

    timeout = httpx.Timeout(limits.read_timeout, connect=limits.connect_timeout)
    headers = {"User-Agent": USER_AGENT, "Accept": "*/*"}

    with httpx.Client(
        transport=transport, timeout=timeout, follow_redirects=False, headers=headers
    ) as client:
        for _ in range(limits.max_redirects + 1):
            # Re-validated at every hop, not just the first. This is the check that
            # stops a public URL from redirecting into the private network.
            validate_url(current, resolver=resolver)
            chain.append(current)

            try:
                with client.stream("GET", current) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise _refuse(
                                RejectionReason.REDIRECT_BLOCKED,
                                f"{current} returned {response.status_code} with no Location",
                            )
                        current = str(httpx.URL(current).join(location))
                        continue

                    if response.status_code >= 400:
                        raise _refuse(
                            RejectionReason.HTTP_ERROR,
                            f"{current} returned {response.status_code}",
                        )

                    content_type = _content_type_of(response)
                    if content_type not in limits.accepted_content_types:
                        raise _refuse(
                            RejectionReason.UNSUPPORTED_CONTENT_TYPE,
                            f"{current} served {content_type or 'no content type'!r}",
                        )

                    body = _read_bounded(response, limit=limits.max_bytes, url=current)
            except httpx.TimeoutException as exc:
                raise _refuse(RejectionReason.TIMEOUT, f"{current} timed out: {exc}") from exc
            except httpx.HTTPError as exc:
                raise _refuse(
                    RejectionReason.TRANSPORT_ERROR, f"{current} failed: {exc}"
                ) from exc

            if content_type in PDF_CONTENT_TYPES and not body.startswith(PDF_MAGIC):
                raise _refuse(
                    RejectionReason.INVALID_PDF,
                    f"{current} claims {content_type} but does not begin with %PDF-",
                )
            if not body:
                raise _refuse(RejectionReason.CONTENT_INTEGRITY_ERROR, f"{current} was empty")

            return FetchedResource(
                requested_url=url,
                final_url=current,
                redirect_chain=tuple(chain),
                status_code=response.status_code,
                content_type=content_type,
                body=body,
                sha256=sha256_bytes(body),
                fetched_at=datetime.now(UTC),
            )

    raise _refuse(
        RejectionReason.TOO_MANY_REDIRECTS,
        f"{url} exceeded {limits.max_redirects} redirects",
    )


__all__ = [
    "ACQUISITION_VERSION",
    "ALLOWED_SCHEMES",
    "HTML_CONTENT_TYPES",
    "PDF_CONTENT_TYPES",
    "USER_AGENT",
    "FetchPolicy",
    "FetchedResource",
    "Resolver",
    "fetch_url",
    "system_resolver",
    "validate_url",
]
