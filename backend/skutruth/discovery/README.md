# Manufacturer source discovery

## A SEARCH RESULT IS A LOCATOR. IT IS NEVER EVIDENCE.

A search engine returning `officialmanufacturer.com/LC1D18P7 — "18 A contactor, 440 V"`
has told us **where to look**. It has not told us the product is rated 18 A. The snippet
never reaches a `ProductAttribute`, an `Evidence`, or the `ArtifactStore`; only bytes we
fetched and hashed ourselves can, and even those must still pass identity resolution and
mechanical verification unchanged.

Rank is not authority either. Being first on a results page is a fact about a search
engine, not about who publishes a product's specification.

```
DiscoveryRequest  →  deterministic queries  →  provider (through record/replay)
                                                        ↓
                                                 SearchResult[]
                                                        ↓  authority · relevance · kind
                                                 SourceCandidate[]  ranked, with reasons
                                                        ↓  eligible only
                                                 safe fetch  →  ArtifactStore
                                                        ↓
                                                 DiscoveryResult
```

## Scope of this milestone

**PDF acquisition only.** An official HTML product page is discovered, ranked, fetched,
and hashed — and then recorded as `NOT_INGESTABLE_YET` rather than forced into an artifact
store whose every invariant (page map, per-page hashes, per-page text) is defined for a
paginated document. Writing an HTML page in there as a one-page PDF-shaped record would be
a small lie told in exactly the place the system's provenance rests on.

That is a scope statement, not a quality judgement, and it is deliberate: half a safe HTML
pipeline is worse than none.

## Four deterministic decisions, none of them asked of a model

| Question | Answered by |
|---|---|
| Which queries? | fixed templates in `query.py` |
| Whose site is this? | the reviewed registry in `domains.py` |
| Is it this exact product? | token comparison against the frozen `canonical_mpn` |
| Which candidate first? | lexicographic tiers in `ranking.py` |

A model is never asked "is this the official manufacturer site?" or "are these two part
numbers the same?" Both answers would be plausible, unfalsifiable, and upstream of every
trust decision that follows. A test asserts the package imports no model client.

## Domain authority is configuration

`philips-superstore-example.com` contains "philips". `philips.com` is Philips. No
similarity score separates those reliably, and getting it wrong yields a reseller's
marketing copy presented as manufacturer specification.

So a host is manufacturer-owned because a reviewed registry says so, and for no other
reason. Host matching is label-aware: `download.se.com` is covered by `se.com`, while
`se.com.evil.example` is not — a bare suffix test would accept the second.

| Authority | May license a fact |
|---|---|
| `APPROVED_MANUFACTURER` | **yes** |
| `OTHER_MANUFACTURER` — approved, but for a different manufacturer | no |
| `KNOWN_DISTRIBUTOR`, `KNOWN_MARKETPLACE` | no |
| `BLOCKED` — datasheet mirrors, scraped aggregators | no |
| `UNKNOWN` | no. Unknown is not permission. |

Mirrors are refused even though they frequently carry a genuine manufacturer PDF: the copy
cannot be shown to be unaltered, and knowing exactly what we read is the entire point of
hashing an artifact.

Registries declare their own provenance — `OFFICIAL` (organizer-supplied), `REVIEWED` (a
person checked each domain), `DEMO`. **We hold no organizer manufacturer master**, so
everything shipped today is `REVIEWED` at best and `is_authoritative` is `False`.

## Exact-MPN relevance can only demote

Only `EXACT` — the reference present as a whole token under `canonical_mpn` — lets a
candidate be acquired. The other states exist to refuse things that look right:

* `FAMILY_ONLY` — `LC1D18` is not `LC1D18P7`. A family stem is not its own child.
* `SIBLING` — `LC1D18B7` is a different coil voltage.
* `AMBIGUOUS` — several diverging siblings and no exact match.

Family and sibling detection compares token prefixes, which is exactly the "cleverer" MPN
reasoning `contracts/mpn.py` says belongs behind evaluation. It is admissible here for one
reason: **it is only ever used to reject.** A heuristic that loses a good source costs
recall; one that grants authority costs correctness. Only the frozen `canonical_mpn` can
produce `EXACT`.

And `EXACT` still proves nothing about the product. It means the reference appears in a
URL or a title — a reason to fetch the document, after which identity resolution applies
exactly as before. Discovery cannot bypass the identity gate; it feeds it.

The **snippet is deliberately not consulted** for relevance. It is provider-generated text
that may quote a cross-sell list, and letting it decide what a page is about would put a
search engine's summarisation upstream of a product decision.

## Ranking

Lexicographic over named tiers, so every ordering can be explained in words rather than
trusted:

1. authority · 2. MPN relevance · 3. source kind · 4. provider rank

Provider rank is last on purpose — it is the only signal a search engine controls, so
anything it could outrank would be a decision the engine had made for us. **An approved
manufacturer page for the exact product always outranks a third-party page for the exact
product**, however the engine ordered them.

## Fetching is SSRF-sensitive and fails closed

Every URL was named by a search engine, so it is attacker-influenceable in the ordinary
case. See `fetch.py` for the full list; in summary: `http`/`https` only; every resolved
address checked, not just the first; loopback, private, link-local, unique-local,
multicast, reserved and unspecified refused for IPv4 and IPv6; redirects followed manually
with the **whole policy re-applied at every hop**; bounded redirects, timeouts, and
response size; content-type allowlist plus a `%PDF-` signature check; no credentials sent
and no headers carried across hosts; an honest user agent that does not impersonate a
browser.

**DNS is not pinned, and that is stated rather than papered over.** Addresses are resolved
and validated, then httpx resolves again when connecting. A same-name rebind inside that
sub-second window would defeat the check. Closing it means connecting to a validated IP
while preserving SNI and certificate verification, which httpx does not expose cleanly.
The gap is documented in `fetch.py` and is the first thing to fix if discovery is ever
pointed at untrusted input at scale. Claiming a protection the code does not implement
would be worse than the gap.

No browser engine, no JavaScript, no sub-resource loading, no crawling. Discovery fetches
documents a provider named and stops.

## Bounded work

Queries per product, results per query, fetch attempts, redirects, timeouts, and bytes are
all capped. There is no spidering and no link following.

## Failure is a result

`found_authoritative_source == False` is the honest outcome for most long-tail products,
and it is better than every alternative. Returning a marketplace listing because it was
the only result would hand the pipeline a page that cannot license a single fact.

## Replay

Search goes through the existing `skutruth.replay` runner rather than new machinery:
versioned cassette keys, credential redaction before key derivation, and a `REPLAY` mode
that cannot reach the network — **not on a miss, not on a malformed cassette**. A replay
run that quietly reached the internet would invalidate every measurement taken from it.

API keys belong to the live callable and never enter the interaction descriptor, so they
cannot reach a cassette key or a stored recording. A test asserts a credential never
appears in a cassette file.

## The seam into the existing pipeline

`ingest/limits.py` already said it, before there was a fetcher: *"Discovery hands over
bytes; ingestion never reaches the network."* That contract is honoured exactly — nothing
here re-implements PDF parsing, hashing, or page mapping. `discovered_artifacts()` returns
ordinary `IngestedArtifact` values, the same type identity, extraction, and verification
already consume, so wiring discovery to the rest of the system means passing them on
rather than copying files.

Identical bytes at two URLs are one artifact. A document published twice is one document,
and counting it twice would let a mirror manufacture agreement.

## Known limitations

* HTML pages are discovered and hashed but not ingested (above).
* DNS is not pinned (above).
* Manufacturer hints are matched against explicitly listed spellings. A manufacturer not
  in the registry yields no approved domain — correct, and it means coverage is bounded by
  how much of the registry has been written.
* `Part_Manuf` is not always a manufacturer. Several of the organizer input's largest
  suppliers are buying groups and distributors, so no manufacturer domain exists to find.
  Resolving that needs the manufacturer master, not more discovery.
* No live search provider is implemented. The `SearchProvider` protocol is the whole
  interface; adding one is a small, isolated piece of work, deliberately not bundled with
  the policy engine.
