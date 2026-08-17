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
                                                 safe fetch
                                                        ↓  authority re-checked on the FINAL host
                                                 ArtifactStore
                                                        ↓
                                                 DiscoveryResult
```

## Six independent gates. None substitutes for another.

```
SEARCH RESULT  ≠  NETWORK SAFETY  ≠  DOMAIN REVIEW  ≠  MANUFACTURER IDENTITY  ≠  PRODUCT SCOPE

and, underneath the middle one:

EVIDENCE AVAILABLE FOR REVIEW  ≠  REVIEW PERFORMED
GIT AUTHOR                     ≠  DOMAIN REVIEWER
```

| Gate | Question | Answered by |
|---|---|---|
| **search result** | where might this be? | the provider — a locator, nothing more |
| **network safety** | is this safe to connect to? | `fetch.py` — scheme, DNS, address ranges, per hop |
| **domain review** | has anyone actually checked that this manufacturer publishes from this host? | a `DomainReview` record on the registry entry |
| **manufacturer identity** | does this supplier spelling *name* that manufacturer? | `authority_hints`, never `locator_hints` |
| **MPN relevance** | is it worth acquiring for *this* reference? | `canonical_mpn` token comparison |
| **product scope** | what does the document actually cover? | the identity resolver, after acquisition |

Each pair is genuinely different, and each confusion is a real failure mode:

* **safety vs review.** A public, reachable, perfectly safe third-party host is *safe to
  connect to* and has no standing to publish a manufacturer's specification.
  `REDIRECT_AUTHORITY_LOST` is deliberately not an SSRF reason.
* **review vs identity.** `dewalt.com` being a reviewed DeWalt domain says nothing about
  whether the supplier string `Black & Decker/dewlt` means DeWalt. One is a fact about a
  host; the other is canonicalisation, and it needs the manufacturer master.
* **identity vs product scope.** Knowing whose site a document is on says nothing about
  which product it describes. Discovery hands over bytes; identity resolution decides what
  they are about, and mechanical verification decides what they support.

## Scope of this milestone

**PDF acquisition only.** An official HTML product page is discovered, ranked, fetched,
and hashed — and then recorded as `NOT_INGESTABLE_YET` rather than forced into an artifact
store whose every invariant (page map, per-page hashes, per-page text) is defined for a
paginated document. Writing an HTML page in there as a one-page PDF-shaped record would be
a small lie told in exactly the place the system's provenance rests on.

That is a scope statement, not a quality judgement, and it is deliberate: half a safe HTML
pipeline is worse than none.

## The live path, and the four different things it can achieve

```
    organizer row
        ↓
    deterministic queries          query.py — no model, no sampling
        ↓
    LIVE search provider           agent_search.py (site-restricted keyword search)
        ↓
    candidate LOCATOR              a URL. Nothing more.
        ↓
    human domain review            review.py + scripts/review_manufacturer_domains.py
        ↓
    manufacturer authority         domains.py — only now may bytes be stored
        ↓
    safe acquisition               fetch.py + acquire.py → ArtifactStore
```

Each arrow is a separate achievement, and the report never collapses them:

* **LIVE SEARCH ≠ HUMAN REVIEW.** A search engine naming `kichler.com` establishes that a
  search engine named it. Whether Kichler operates that host is a question a person
  answers, and until they do, everything found there is `UNVERIFIED_MANUFACTURER`.
* **HUMAN DOMAIN REVIEW ≠ PRODUCT IDENTITY.** Confirming that a manufacturer owns a domain
  says nothing about whether a given document on it describes the product in hand. That is
  decided by exact-reference matching and then by identity resolution on the fetched bytes.
* **PRODUCT IDENTITY ≠ ATTRIBUTE VERIFICATION.** Knowing a PDF is about `LC1D18P7` does not
  make any number in it true of the product. Mechanical verification decides that, span by
  span, and most claims do not survive it.

`diagnostics.py` reports which of these a row reached, as a state rather than a score.

## The live search provider

`AgentSearchProvider` calls **Agent Search basic website search** (Discovery Engine),
using the project's existing GCP setup and Application Default Credentials.

### Why not Google Search grounding

A grounding provider was implemented and removed. Its terms state that Grounded Results,
Search Suggestions, and Links "are intended to be used in combination to respond to a
given End User prompt", and prohibit "using programmatic or automated means to collect
Links, using Links to build an index, or using Links to identify destination pages for
crawling or scraping". SKUTruth does all three: it collects links programmatically,
records them as candidates, and fetches the pages they name.

Grounding is therefore not available to this pipeline. That is a terms question, not a
technical one, and no amount of engineering changes it. The commit that added it stays in
history as an experiment.

An earlier Custom Search JSON API adapter was also removed: Google has closed that API to
new customers.

### Why basic website search fits

* **the caller's query is executed verbatim.** `build_queries` is the query again, not an
  intent handed to a model that may rewrite it. Discovery is deterministic end to end, and
  a test asserts no module in this package imports a model client.
* **results carry the publisher's real URL** (`derivedStructData.link`), so the exact-MPN
  gate has something to match and the authority lookup needs no redirect workaround.
* **no generative feature is used** — no summaries, no `answer`, no follow-ups. Ordinary
  search results only.
* **advanced website indexing is off.** It requires verifying domains we do not own;
  Google's guidance is to disable it in exactly that case. Basic search reads Google's
  existing index instead.

### The corpus is the reviewed set

`included_patterns_for()` builds the included URL patterns **only** from registry entries
carrying a `DomainReview`. A domain becomes searchable after a human reviews it, never
before — so Agent Search cannot be used to decide that a domain is trustworthy, and no
provider output can add one. `scripts/setup_agent_search.py` prints the resulting
configuration and creates nothing.

Basic website search allows **50 included URL patterns**. That ceiling is enforced rather
than truncated: silently dropping the fifty-first would make a reviewed manufacturer
quietly unsearchable, and the run would report "no results" for a domain the operator
believed was configured.

### Queries and filters

Site restriction and file type are **filters**, not query text, so the query stays exactly
the reference being looked for:

    query  = 45297BK
    filter = siteSearch:"https://kichler.com/*" AND fileType:".pdf"

Basic website search's documented grammar is `filter = expression, { "AND", expression }`.
There is **no `OR`** — using one returns *"Unsupported expression type in filter"*, because
`OR` belongs to the advanced-indexing grammar and advanced indexing is off here. So
`build_filter` takes a single site pattern; an OR filter is not expressible rather than
being a runtime parse error waiting to happen.

`fileType` is available on basic search and not on advanced indexing — one more reason
basic suits this use. Snippets are returned and kept as locator metadata; they are
deliberately **not** consulted by `classify_relevance`, so a snippet can never establish
that a page is about a product.

### Corpus, and per-row site filter, are different things

| | what it is | how wide |
|---|---|---|
| **data store corpus** | what the app may search at all | every reviewed domain, ≤ 50 patterns |
| **query-time filter** | what one row searches | only *that row's* manufacturer's reviewed domains |

Conflating them would search every reviewed manufacturer's site for every part number —
spending calls on other manufacturers and inviting a near-miss host to be considered in
the first place. `reviewed_patterns_for_hint` resolves the row's manufacturer hint through
the registry and returns its reviewed domains, or **empty**, which means: make no call for
this row.

A manufacturer with several reviewed domains (Makita publishes from `makitatools.com` and
`makita.com`) costs one bounded request per domain, merged deterministically — domains in
configured order, results in provider order, first sighting of a URL wins. Rank stays the
position within its own query, which is what the provider actually reported; there is no
synthetic global score, and `ranking.py` orders candidates by its own tiers regardless.

Result caps: basic website search documents `pageSize` default 10, **maximum 25**. The API
coerces larger values down silently, so `AgentSearchLimits` refuses them — a run that
believed it saw 100 results when it saw 25 would draw conclusions from a truncated set it
did not know was truncated. That ceiling is unrelated to the 50-pattern corpus limit.

### What has and has not been verified

The `SearchRequest` shape was verified against the installed SDK
(`google-cloud-discoveryengine` 0.20.2), and the filter grammar is implemented from
Google's documented basic website-search syntax. **No live Agent Search request has run**,
so the backend has not parsed our filters. Constructing a `SearchRequest` locally proves
the field names and types, and nothing about whether the service accepts the expression.

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
| `UNVERIFIED_MANUFACTURER` — the registry connects host and manufacturer, but not with enough standing | no |
| `OTHER_MANUFACTURER` — approved, but for a different manufacturer | no |
| `KNOWN_DISTRIBUTOR`, `KNOWN_MARKETPLACE` | no |
| `BLOCKED` — datasheet mirrors, scraped aggregators | no |
| `UNKNOWN` | no. Unknown is not permission. |

Mirrors are refused even though they frequently carry a genuine manufacturer PDF: the copy
cannot be shown to be unaltered, and knowing exactly what we read is the entire point of
hashing an artifact.

### Authority is re-decided on the host the bytes came from

`fetch.py` re-applies *network* policy at every redirect hop. That is a different question
from ownership, and answering only it leaves a real hole: an approved manufacturer URL can
302 to an ordinary public third-party host, pass every SSRF check, and — if authority were
still read from the URL the search engine named — have its bytes stored as manufacturer
evidence.

So `SourceCandidate` carries both `authority` (the host named, which decides whether the
candidate is worth fetching) and `final_authority` (the host the download came from, which
decides what may be stored). `effective_authority` is what every provenance-writing path
reads, and `acquire_pdf` refuses outright when it does not license evidence. Bytes from a
lost-authority redirect are downloaded and discarded, never ingested.

### Two kinds of hint, and only one grants ownership

* `authority_hints` — reviewed as genuinely naming this manufacturer. Differences are
  case, punctuation, or corporate form; `Makita Usa Inc` reduces to `Makita` under a
  documented suffix rule. These may produce `APPROVED_MANUFACTURER`.
* `locator_hints` — observed spellings that are *plausibly* this manufacturer and are not
  confirmed. `Phillips Lighting` (two Ls) is almost certainly Philips; `Black &
  Decker/dewlt` is probably DeWalt. They build site-restricted queries and grant nothing;
  anything found through them is `UNVERIFIED_MANUFACTURER`.

Losing the search would be the worse trade — a `site:` query aimed at the wrong
manufacturer costs one query and returns nothing, while never searching the right site
costs the source entirely. Granting ownership on a guess costs correctness, so only that
half is withheld. Neither path rewrites the input spelling.

Deciding that `Black & Decker/dewlt` *is* DeWalt is exactly the canonicalisation the
missing manufacturer master would authorise. Asserting it as a side effect of a domain
lookup would make that decision without the evidence.

### What a registry's own provenance permits

| | `is_authoritative` | may license | needs a per-entry review record |
|---|---|---|---|
| `OFFICIAL` — organizer master, named in `source` | yes | yes | no |
| `REVIEWED` — a person checked each domain | no | **only with a record** | **yes** |
| `DEMO` — illustrative | no | no | n/a |

`REVIEWED` licenses evidence because domain ownership is a checkable fact, and a different
claim from conforming to Unilog's catalogue rules. `DEMO` licenses nothing — an
illustrative entry that could authorise a download would make the label meaningless.

`OFFICIAL` needs no per-entry review: its basis is the organizer master, named once on the
registry, and inventing a "manual review" for rows that came from a supplied file would
record a check nobody performed. An `OFFICIAL` registry that names no `source` is refused.

### What `REVIEWED` actually means, and what backs it

Licensing authority now rests on the review, so the review cannot be an unaudited
assertion. Every entry that licenses evidence carries:

```toml
[manufacturer.review]
reviewed_at = "2026-08-17"
reviewed_by = "Amaan Khan"
basis      = "what was checked, ideally something re-examinable in this repository"
```

A half-filled record is refused at load — one naming no reviewer, no date, or no basis
answers none of the questions it exists to answer. An entry with **no** review block is
not an error: it is simply unreviewed, stays useful for locating candidates, and licenses
nothing.

### Evidence available for review ≠ review performed

This is the distinction the whole mechanism turns on, and it is easy to lose.

The shipped registry's Schneider entry has more supporting material than any other: the
local artifact store holds documents fetched from those hosts with their URLs and byte
hashes recorded, and `research/lc1d18_artifact_note.md` preserves that lineage in
committed form. (The manufacturer PDFs themselves are gitignored and stay that way, so a
fresh clone has the note, not the documents.) A reviewer could use all of it.

Nobody has. So the entry carries **no** review and licenses nothing.

### Git author ≠ domain reviewer

An earlier revision of this file recorded `reviewed_by = "Amaan Khan"`, taken from the
repository's git identity during an automated session. Nobody had opened Schneider's site
and confirmed anything. That is exactly the assertion `DomainReview` exists to refuse,
manufactured by the mechanism built to refuse it.

A review is an **affirmative audit event**: a named person checked, and says so. It is
never inferred from git authorship, from commit history, from artifacts existing in a
store, or from an automated run having read the files. Those produce material that *can*
be reviewed. Only a person produces a review.

**The shipped registry therefore has zero licensing entries.** Measured against the
organizer input: 5 of 75 supplier spellings remain **searchable** (291 of 959 rows) and
**none licenses evidence** (0 of 959). Zero is the correct number for a registry nobody
has audited, and it is better than one entry with a signature its owner never gave.

To promote an entry: open the manufacturer's site, confirm it publishes from each listed
domain, then add `[manufacturer.review]` with your own `reviewed_by` and a `basis` naming
what you checked. Nothing automated may perform that step.

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

## Provenance is never rounded up to something plausible

Two places where a convenient default would have been a lie:

* **`discovery_method`. The provider declares it; nothing infers it.** A `SearchProvider`
  states its own `discovery_method`, because only it knows how it finds things. Reading it
  off the provider's *name* would let a class called `google-search` mint
  `GOOGLE_SEARCH_GROUNDING` provenance for results that never went near Google — branding
  deciding what the audit trail says.

  `None` is a legitimate declaration: it means the frozen `DiscoveryMethod` has no value
  that truthfully describes this provider. Acquisition then **refuses**
  (`DISCOVERY_PROVENANCE_UNDECLARED`) rather than defaulting, because
  `SourceMetadata.discovery_method` is non-optional and every available default —
  including `OPERATOR_SUPPLIED` and `DIRECT_URL` — would assert something untrue about how
  the document was found. An artifact that cannot say how it was discovered is not stored.

  **The contract gained one value, for a concrete case.** `AgentSearchProvider` declares
  `SITE_RESTRICTED_SEARCH`, added because no existing member was true: `CURATED_CORPUS`
  implies a pre-assembled document set rather than a live index, `GOOGLE_SEARCH_GROUNDING`
  names a different mechanism, and `DIRECT_URL` / `OPERATOR_SUPPLIED` would credit a person
  for a search result. It is named for the mechanism, not the vendor, because the product
  implementing it has been renamed twice already.

  The rule that produced the earlier gap stands: a provider that cannot state its
  mechanism declares `None`, and acquisition refuses with
  `DISCOVERY_PROVENANCE_UNDECLARED` rather than defaulting. Tests still cover that path.
* **`source_type`.** `MANUFACTURER_DATASHEET` asserts the document *is a datasheet*. A PDF
  from a manufacturer may equally be a manual, a warranty, a brochure, or a catalogue, so
  only a candidate whose kind is actually `DATASHEET` receives it, `PRODUCT_PAGE` receives
  `MANUFACTURER_PAGE`, and everything else stores `None`. `SourceMetadata.source_type` is
  optional precisely so this can be left unsaid, and the repository's own ingested
  Schneider catalogue records `null` there.

`publisher` is likewise only set when the effective authority licenses evidence. An
artifact that arrived from a host with no standing does not get to name a manufacturer.

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

* **No live Agent Search run has happened yet.** No manufacturer domain has been reviewed,
  so the corpus is empty and there is nothing to search. The provider is exercised offline
  through the whole service; whether basic website search returns useful results for
  third-party manufacturer domains is unverified, and should be checked with a single real
  query before anything is built on it.
* Manufacturer hints are matched against explicitly listed spellings, so coverage is
  bounded by how much of the registry has been written *and reviewed*. Against the
  organizer input: 5 of 75 supplier spellings are searchable (291 of 959 rows), and
  **none licenses evidence** (0 of 959), because **no entry has been reviewed by anyone**.
  Raising that number requires a person to perform and sign real domain reviews; it is not
  an engineering task.
* Basic website search caps the corpus at **50 URL patterns**, so one data store cannot
  cover every manufacturer in a 1,000-row catalogue. Sharding is a later problem; a handful
  of reviewed manufacturers is enough to prove the seam.
* Agent Search reads Google's index, so coverage depends on what Google has indexed and on
  the publisher's own indexing policy. A manufacturer PDF Google has not indexed is not
  findable this way.
* HTML pages are discovered and hashed but not ingested (above).
* DNS is not pinned (above).
* `Part_Manuf` is not always a manufacturer. Several of the organizer input's largest
  suppliers are buying groups and distributors, so no manufacturer domain exists to find.
  Resolving that needs the manufacturer master, not more discovery.

## Reviewing a domain

```
python scripts/review_manufacturer_domains.py packet --input <organizer csv>
python scripts/review_manufacturer_domains.py confirm \
    --manufacturer <key> --confirm-domain <domain> \
    --reviewed-by "<your name>" --basis "<what you checked>" --write
```

`packet` gathers the observed spellings, row counts, sample references, configured
domains, and — with `--search` — live results, and decides nothing. Every candidate comes
out with an unticked decision box.

`confirm` records a decision you state. There is no default for `--reviewed-by`: not git
config, not the OS username, not the environment, and a test parses both files' ASTs to
prove none of those can be read. A review licenses *every* domain on its entry, so all of
them must be confirmed together or the entry must be split first.

Confirming a domain never rewrites a manufacturer spelling. `Phillips Lighting` stays a
locator hint after Signify's domains are confirmed; that is canonicalisation, and it needs
the manufacturer master.
