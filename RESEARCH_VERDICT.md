# RESEARCH_VERDICT.md — SKUTruth / UniHack 2026

**Status:** Post-research, post-red-team. Supersedes the pre-review draft in full.
**Last revised:** 2026-08-09, after the Checkpoint 1 review in [`CODEX_REVIEW.md`](CODEX_REVIEW.md)
and the final contract reconciliation.

> This document previously contained several claims that did not survive review — a broad P0,
> a cross-attribute physics check, near-term confidence calibration, and an over-absolute
> reading of both our differentiation and our evidence. Those are corrected here rather than
> quietly dropped; the *Corrections* section at the end records what changed and why.

---

## What SKUTruth is

**SKUTruth is an auditable product-fact verification and triage layer for long-tail catalog
enrichment, designed to feed existing PIM workflows.**

It takes a sparse input — brand, manufacturer part number, a few words of description —
and produces a structured, ETIM-typed product record in which **every accepted value carries a
source span we located ourselves in a hashed artifact**, and everything else is explicitly
withheld with a reason a person can act on.

The core trust claim, stated exactly:

> **No value is accepted unless its supporting span is verified in a versioned source
> artifact.**

That is a mechanical property, and the contract enforces it: an accepted attribute with no
`EXACT_SPAN` or `FUZZY_OCR_SPAN` evidence cannot be constructed.

## What SKUTruth is not

It is not a claim to have invented product enrichment. Unilog already performs custom SKU
creation, gap fill, cleansing, standardisation, taxonomy design, attribute mapping,
validation, and parent/child grouping, and sells a content library of 10M+ enriched SKUs
alongside a services team that does this work. Their HyperScale agent suite already ships a
Product Description Agent and has Item Matching and Product Grouping agents on its roadmap.

So the honest framing is narrower and more useful: **the expensive step in that workflow is
expert verification, and SKUTruth is aimed at reducing it.** It decides which facts are safe
to accept, shows the evidence behind each decision, and routes only the unresolved remainder
to a person.

The business KPI that follows is **expert review minutes per accepted attribute** (or per
completed SKU), reported alongside unsupported-claim rate — not fill rate, which Unilog
already knows how to maximise.

The pitch sentence:

> We do not automate filling every field. We automate deciding which product facts are safe to
> accept, show the evidence for each decision, and send only the unresolved remainder to an
> expert.

---

## Hard constraints

| Item | Fact |
|---|---|
| Submission deadline | **23 Aug 2026** (prototype submission runs 29 Jul – 23 Aug) |
| Evaluation | 24 Aug – 1 Sep 2026, **offline and unattended** |
| Finale | 4 Sep 2026 |
| Format | Virtual · teams of 1–4 · undergraduate engineering students in India |
| Judging | Innovation, technical implementation, business relevance, **scalability**, overall impact |
| IP | Ownership of winning solutions transfers to the organisers on award |

Two consequences drive everything below. **We have days, not weeks.** And **no one will be in
the room** — the deployed demo, the video, the README and the evaluation report do all the
talking, so the demo must be incapable of failing on a third-party call, and every number must
be reproducible by a reviewer with no API key.

*The deadline and IP terms should be archived as an organiser-issued PDF or full-page capture
rather than relied on from a dynamic page.*

---

## The differentiation, stated carefully

Eight properties, each mechanically checkable. None of them is "we use AI".

**1. Identity before enrichment.** Nothing is enriched until we determine what the input
refers to. `IdentityDisposition` is `EXACT`, `FAMILY_OR_INCOMPLETE_REFERENCE`, `UNKNOWN`, or
`CONTRADICTORY`, and it is a hard gate in the contract, not advice. A perfect record for the
wrong variant is a worse outcome than no record.

**2. Family / incomplete-reference detection.** `LC1D18` is a TeSys D device stem; exact
Schneider references append a coil code (`LC1D18P7`, `LC1D18BD`). We report that the coil
discriminator is unbound, name it, and offer the choice — we do **not** claim the reference is
unorderable, because some channels do list family stems as purchasable records.

Critically, when identity is family-level we may only state attributes **proven** invariant
across the family, which requires a variant table span or agreement across two or more
distinct exact children. Copying an invariant-looking value from one child is an inference,
not verified product intelligence, and the contract rejects it.

**3. Condition-aware technical attributes.** A contactor's `18 A` and `32 A` are its AC-3 and
AC-1 ratings, not a contradiction. Qualifiers — utilization category, voltage, frequency,
temperature, phase, measurement basis, region, standard — are structured data bound to each
value, so condition differences resolve deterministically instead of being reported as
factual conflicts.

**4. Verified page/span evidence.** Discovery and provenance are separate concerns. Google
Search grounding and URL Context tell us *where to look*; they annotate generated text with
source URLs and do not prove that a quote exists on a stated page. Evidence authority comes
from an artifact we ingested, hashed, and page-mapped ourselves, with the quote located in it
(`EXACT_SPAN` / `FUZZY_OCR_SPAN`, else `UNVERIFIED` and unusable for acceptance).

**5. Deterministic normalisation.** Units, ranges, enums, and booleans are normalised in
code against ETIM's own unit and allowed-value tables. `18000 mA → 18 A` is a versioned
transform with a recorded lineage, not a model call.

**6. Explicit abstention with a reason.** `NOT_FOUND`, `NOT_APPLICABLE`, `VARIANT_DEPENDENT`,
`CONFLICTED`, `UNSUPPORTED_SPAN`, `OUT_OF_IDENTITY_SCOPE`. A user must be able to tell why a
field is empty, because the remedy differs in each case.

**7. Selective human review.** Only conflicted, unsupported, and identity-ambiguous decisions
reach a person. That is the mechanism behind the review-minutes KPI.

**8. Auditable acceptance decisions.** Support is a coarse, rule-derived grade (A/B/C) over
logged factors, recomputed by the contract so it cannot be hand-set, with the reasoning shown
in the Evidence Drawer. Not a decimal probability.

---

## Taxonomy: ETIM, scoped honestly

ETIM 10.0 is vendored under **ODC-BY 1.0** (attribution in [`data/etim/ATTRIBUTION.md`](data/etim/ATTRIBUTION.md)).
Counts below come from [`scripts/etim_stats.py`](scripts/etim_stats.py), which is the single
source of truth for every ETIM number in this repository; parsed records, headers excluded:

| | |
|---|---:|
| Classes | 5,640 |
| Groups | 159 |
| Features | 17,377 |
| Units | 188 |
| Values | 16,163 |
| Class-feature rows | 76,625 |
| Allowed-value rows | 201,284 |
| Synonyms | 37,058 |
| Referential-integrity issues | 0 |

**What ETIM gives us:** stable class and feature identifiers, four explicit feature types
(`N`/`A`/`L`/`R`), units for numeric and range features, fixed allowed values for
alphanumeric features, and class synonyms that make lexical candidate generation free.

**What ETIM does not give us, and we must not imply it does:** proof that a value is true, a
manufacturer SKU identity graph, or a mandatory field list. **ETIM features characterise a
class; they are not required product fields.** A feature that does not apply to a product is
not a gap.

Coverage is therefore reported four ways — ETIM feature coverage, buyer-critical coverage,
accepted count, not-applicable count — and only **applicable, buyer-critical, accepted** fields
feed the buyer-facing number. The buyer-critical subset is hand-reviewed per class.

UNSPSC may be emitted as a secondary code; it classifies for spend analysis and defines no
attributes, so it cannot drive gap analysis.

---

## Evidence and sourcing policy

- **Curated, attributed artifact corpus is the reliable path** for the evaluation set and the
  demo. Search grounding is an optional discovery input.
- **We operate no general crawler.** Public availability does not grant redistribution rights,
  and `robots.txt` is a crawl-control signal, not a content licence. `se.com/robots.txt`
  disallows the document paths where datasheets live.
- Prefer URLs, hashes, and minimal quoted spans over shipping third-party PDFs; each corpus
  item's terms get reviewed before inclusion.
- A live search hit is either ingested through a controlled path and verified, or presented as
  an **unverified discovery candidate** that cannot support an accepted value.

Datasheet URL patterns do not generalise — of 11 Schneider references probed against the
`iportal` pattern, one resolved. Discovery recall is therefore a measured metric, and
abstention is the honest failure mode.

---

## Architecture

Six observable decisions, not ten stages:

```
identify → classify → discover/ingest → extract/verify → normalize/adjudicate → present/evaluate
```

- **Python 3.12 + FastAPI**, Pydantic contracts shared by pipeline, API, and evaluation.
- **Next.js + TypeScript** for one record screen and one evidence drawer.
- **Postgres** for records and runs; **object storage** for artifacts.
- **Cassette record/replay** around every external call, from day one.
- **No** vector database, RAG, knowledge graph, agent framework, microservices, message
  broker, or fine-tuning. Whole-document extraction suits datasheet-sized PDFs with a
  deterministic page map; a page/table-aware fallback handles long catalogues. *(This is a
  size-based policy, not a claim that chunking is inherently worse — a page-preserving chunk
  can improve provenance, and long context does not guarantee recall.)*

**Model use.** One extraction model, selected by a small bake-off on the development set and
pinned along with the SDK and provider surface. Routing is deferred until measurements justify
it. Deterministic code owns MPN normalisation, ETIM candidate generation, unit conversion,
range parsing, enum validation, span verification, hashing, and cache keys. A model is used
only to choose among plausible ETIM classes, extract facts into the typed schema, interpret
ambiguous family/condition language, and classify unresolved conflicts — and **never** to
resolve a factual conflict into a committed value.

Vertex AI is the target surface (the $300 Google Cloud credit does not cover the AI Studio
Gemini API). A day-one compatibility spike on the exact project, region, SDK, model,
structured-output schema, PDF path, Search, and URL Context is a prerequisite, not an
assumption.

---

## Scope

**P0 — the reduced vertical slice.**

1. Frozen contracts *(done)*.
2. ETIM loader, validators, attribution, integrity checks *(loader done)*.
3. Identity gating, including the family/incomplete case and non-Schneider traps.
4. Curated document ingestion with hashes, caps, and safe parsing.
5. Page map and span verification.
6. Structured extraction into the ETIM class schema.
7. Deterministic normalisation.
8. Abstention statuses and a conservative acceptance policy chosen on the development set.
9. Golden Product Record.
10. Evidence Drawer with real page highlighting and condition display.
11. Strict replay.
12. Narrow locked evaluation.
13. Public replay-safe deployment.

**Explicitly not in P0:** broad dashboard, commerce copy generation, review queue, source
clustering, model routing, physical consistency, confidence calibration, durable large-scale
queue, live cost telemetry, advanced batch infrastructure.

**P1.** Conservative source-root clustering on document hashes and high-threshold excerpt
similarity; the full conflict-cause pipeline; a small measured CSV batch with persisted
idempotent stages; a review queue; verified before/after buyer-critical coverage; a
family-variant matrix; a conspicuously live single-SKU run if reliability is proven.

**P2.** Statistical calibration with grouped cross-validation and adequate samples; Cloud Run
Jobs or Cloud Tasks for durable batches; broader lineage; domain-expert-approved
cross-attribute constraints; golden-record diff; image extraction; distributor API connector;
BMEcat/xChange export; expansion beyond the initial classes.

---

## Evaluation

- **3–4 ETIM classes in one coherent electrical vertical**, ≥3 manufacturers, several
  families per class.
- **30 development SKUs, 20 locked test SKUs, split by product family** — never by attribute
  row, which would leak document style across the split.
- Manifest pre-registered before final prompt tuning: input, expected identity disposition,
  artifact hash, labelled attributes, trap type.
- One person labels, a second verifies every test label against manufacturer evidence.
  A model-proposed label never becomes ground truth until a human confirms the page and
  conditions. `UNKNOWN` is recorded when authoritative truth is genuinely unavailable rather
  than manufactured from distributor consensus.
- Traps included deliberately: nonexistent MPN, family/incomplete reference, exact SKU with no
  authoritative document, conflicting exact-SKU sources, correct value under the wrong
  condition, missing field, inapplicable feature, malicious or irrelevant document.

**Headline metrics.** Identity disposition accuracy and **false-exact rate** (reported
separately — false exactness is the most dangerous error); committed-value precision;
unsupported-claim rate; buyer-critical coverage; verified citation rate; unit and condition
normalisation accuracy; cost per SKU; latency per SKU. Raw numerator and denominator always
shown, with intervals aggregated by SKU.

**Not reported:** any calibration curve, ECE, or AURC from a 50-SKU corpus — attribute rows
are correlated within families, documents, and manufacturers, so the effective sample is far
closer to 50 than to the raw row count. Nor conflict-class accuracy with a handful of examples
per category; a case matrix with raw counts instead.

`IndustryBench-MIPU` (arXiv 2606.14383) is cited as **motivation only** — it establishes that
completeness is the hard part of industrial attribute extraction. It is a multi-image
benchmark on a different task and its 49.9% figure is **not** a baseline for our PDF/web/ETIM
pipeline.

---

## Scalability

Scalability is an explicit judging criterion, and the credible version is measured, not
claimed:

- persisted, idempotent stage results with retry limits and no duplicate paid calls;
- bounded concurrency per provider and domain, with backoff and per-run budgets;
- content-addressed document and extraction caching, keyed on schema/prompt/model versions;
- a measured 25–50 SKU batch reporting success rate, p50/p95, cost, cache-hit rate, retries,
  and failure distribution.

A Cloud Run *service* is suitable for the API but is not proof of durable background
processing — requests time out and instances disappear. Durable batching via Cloud Run Jobs or
Cloud Tasks is P1. Gemini's Batch API discount is real but is not automatically an end-to-end
catalog engine, and tool compatibility must be tested before it becomes the scale story.

Any projection beyond the measured batch is presented as a **clearly labelled scenario table**
with its assumptions written out, never as tested capacity.

---

## Security, minimally and seriously

Public demo serves replay only; live runs are gated behind an admin secret with hard per-run
and per-day budgets. Curated domain allowlist for fetching, with SSRF protections if arbitrary
fetching is ever enabled. PDF-only ingestion with size, page, and time caps, parsed in
isolation. All document text is treated as untrusted data, never as instructions; the
extraction model gets a fixed schema, no tools, no secrets, and no ability to choose URLs.
Source text is rendered escaped. Fake citations are defeated by span verification, not by
filtering.

Not spending time on RBAC, WAF, VPC Service Controls, or compliance claims.

---

## Demo

1. Enter `Schneider Electric / LC1D18 / Contactor`.
2. `Family or incomplete reference` appears immediately, naming the missing discriminator:
   coil voltage.
3. Fields proven family-level are shown; variant-dependent fields are visibly blocked.
4. Select `230 V AC` → resolves to `LC1D18P7`.
5. The record updates.
6. Click `Rated operational current — 18 A` → the actual PDF page opens with the supporting
   span highlighted, and `32 A / AC-1` is shown alongside as a *condition distinction*, not a
   conflict.
7. Close on the locked-test summary: false-exact count, committed-value precision, unsupported
   claims, coverage, cost per SKU.

The replay badge and capture date are visible throughout.

---

## Principal risks

| Risk | Mitigation |
|---|---|
| Time. Scope overrun leaves nothing polished | Reduced P0; day-7 end-to-end gate; feature freeze before submission |
| A fabricated or mislocated citation | Span verification against an ingested page map; unverifiable evidence cannot support acceptance |
| Wrong exact identity enriches the wrong variant | Hard identity gate; family invariance must be proven; false-exact rate reported |
| "Unilog already does enrichment" | Position as audit and triage automation; measure review effort saved |
| Replay mistaken for live | Persistent dated banner; `MIXED` never served; strictly separate modes |
| ETIM coverage read as mandatory completeness | Buyer-critical subset, `NOT_APPLICABLE`, careful wording |
| Discovery misses the manufacturer artifact | Curated corpus is the reliable path; discovery recall measured; abstention is the honest failure |
| Public live endpoint abused for spend or SSRF | Replay-only public demo; allowlist; gated budgets |

---

## Corrections to the pre-review draft

Recorded rather than deleted, because a document about data quality should show its own
revision history.

| Claim in the earlier draft | Status |
|---|---|
| "We never let the model invent a value" | **Replaced.** A model can fabricate a quote or page. The defensible claim is the verified-span claim above. |
| Cross-attribute physical consistency (contactor P ≈ √3·V·I·cosφ) as a differentiator | **Removed entirely.** The relation carries assumed power factor, efficiency, duty, and utilization category; it would flag correct manufacturer data as inconsistent. Only definitional constraints remain. |
| Calibrated confidence, reliability diagram, ECE, AURC as near-term deliverables | **Deferred to P2.** 50 correlated SKUs cannot support probability calibration. Replaced by rule-derived A/B/C support grades over logged factors. |
| "VERIFIED requires ≥2 independent evidence clusters" | **Replaced.** It made a weaker second source *necessary*, so one manufacturer datasheet with a verified span could never reach top support while two mutually-copied distributor pages could. |
| Decimal per-attribute confidence (`0.98`) | **Removed** from the contract and the UI. |
| `IndustryBench-MIPU` as external validation of our approach | **Demoted to motivation.** Different task, multi-image, not a baseline. |
| Unilog's roadmap implies they do not address verification | **Withdrawn.** Absence from a marketing page is not evidence of absence; Unilog sells validation and enrichment services today. |
| Google Search grounding / URL Context as page-level provenance | **Corrected.** Discovery only; provenance requires our own ingestion and span verification. |
| All ETIM class features treated as required gaps | **Corrected.** ETIM feature coverage ≠ business completeness; `NOT_APPLICABLE` added; buyer-critical subset introduced. |
| ETIM counts (5,641 classes, etc.) | **Corrected** to header-excluded parsed records; `scripts/etim_stats.py` is now the only source. |
| "Whole-document extraction strictly dominates RAG" | **Softened** to a size-based policy. No vector database either way. |
| Original 12-item P0 | **Deleted** and replaced with the reduced vertical slice. |
| Source-independence clustering in P0 | **Moved to P1.** In P0, extra agreeing sources never raise support at all. |
| Model routing in P0 | **Deferred.** One pinned, tested extraction model first. |
| `RunMode.AUTO` | **Replaced** by `MIXED`, which is observable but never requestable. |

## Sources

- [UniHack event page — Unilog × Hack2Skill](https://hack2skill.com/event/unilog2026)
- [Unilog HyperScale](https://www.unilogcorp.com/hyperscale/) · [CX1 Product Content](https://www.unilogcorp.com/platform/product-content/)
- [ETIM licence (ODC-BY 1.0)](https://www.etim-international.com/classification/license-info/) · [ETIM downloads](https://www.etim-international.com/downloads/)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing) · [URL Context](https://ai.google.dev/gemini-api/docs/url-context) · [Search grounding](https://ai.google.dev/gemini-api/docs/google-search)
- [Google Cloud free-trial exclusions](https://docs.cloud.google.com/free/docs/free-cloud-features)
- [Schneider LC1D18P7 datasheet](https://iportal.se.com/Contents/docs/SQD-LC1D18P7_DATASHEET.PDF)
- [IndustryBench-MIPU (motivation only)](https://arxiv.org/abs/2606.14383)
- [Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs) · [Cloud Tasks](https://docs.cloud.google.com/run/docs/triggering/using-tasks)
