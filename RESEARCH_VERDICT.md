# RESEARCH_VERDICT.md — SKUTruth / UniHack 2026

**Author:** Lead engineer & technical product owner
**Date:** 2026-08-09
**Status:** Research pass complete. Implementation NOT started, pending decisions in §K.

---

## TL;DR (read this if you read nothing else)

1. **The deadline is 2026-08-23, not September.** Prototype submission closes the same day registration closes. Evaluation runs 24 Aug – 1 Sep *without us in the room*. **We have 14 days**, and the submission artifacts (video + repo + deployed link + docs) do 100% of the talking. This single fact invalidates the scope in the current plan.
2. **The core hypothesis survives and is genuinely differentiated.** Unilog's own AI roadmap (HyperScale) is *generation*-shaped — Product Description Agent, Item Matching Agent, Product Grouping Agent. Nothing on their published roadmap does evidence, verification, conflict adjudication, calibrated confidence, or abstention. We are complementary, not duplicative.
3. **The biggest technical win available is ETIM 10.0.** It is free, ODC-BY licensed, redistributable, 2.9 MB, and gives us 5,641 typed product classes, 17,379 features with units, 201,285 allowed picklist values, and 37,059 class synonyms. This converts taxonomy mapping, gap analysis, unit normalisation, and value validation from "ask an LLM" into **deterministic, verifiable code**. Verified by download and inspection today.
4. **Three things in the current plan are wrong and will be attacked by a competent reviewer:** LLM-emitted confidence scores, a hardcoded source-authority tier table, and naive multi-source agreement. Fixes in §C.
5. **One question materially blocks budget design:** the $300 Google Cloud trial credit **cannot** be spent on the AI Studio Gemini API — only on Vertex AI. See §K1.

---

## A. What I confirmed

### A1. The challenge, rules, and timeline (verified on the official Hack2Skill event page)

| Item | Fact |
|---|---|
| Event | UniHack — "AI-Powered Product Intelligence for Industrial Commerce", Unilog × Hack2Skill |
| Format | **Virtual**, asynchronous |
| Team size | **1–4** |
| Eligibility | Undergraduate engineering students at recognised Indian colleges |
| Registration | 29 Jul – **23 Aug 2026** |
| **Prototype submission** | **29 Jul – 23 Aug 2026** (same window) |
| Evaluation | 24 Aug – 1 Sep 2026 (offline, judges only) |
| Finale | 4 Sep 2026 |
| Prize pool | ₹5,00,000 (₹2L / ₹1.5L / ₹1L / 2 × ₹25k) |
| Judging criteria | Innovation, technical implementation, business relevance, **scalability**, overall impact |
| **IP** | *"Ownership of the IP rights for winning solutions will be transferred to the program organizers upon confirmation of the award."* |

The four "expected outcomes" in the brief map exactly to our pipeline: structured generation from limited inputs, accuracy & consistency, AI validation & enrichment, scalable catalog engine. Note that **"scalability" is an explicit judging criterion** — it is not optional decoration.

**Consequence — this is the most important thing in this document:** judging is *offline and unattended*. Nobody will forgive a broken live demo, re-run a failed request, or listen to us explain an architecture diagram. Everything must be legible in ~5 minutes from a video and a README, and the deployed app must be **incapable of failing due to a third-party network call.**

### A2. Unilog — what they already have (so we don't rebuild it)

- **CX1 Platform**: CX1 eCommerce, **CX1 PIM**, CX1 Product Content, CX1 Connect.
- **CX1 Content Subscription**: a library of **10M+ pre-enriched SKUs** sourced from direct relationships with ~2,000 manufacturers.
- **CX1 Content Services**: a *human* services team doing custom SKU creation, attribute mapping, taxonomy design, digital asset sourcing.
- **HyperScale** (their AI agent suite, live + roadmap):
  - Available now: Blog Agent, Synonym Agent, Sales Insights Agent, Connect Agent, Writing Agent, **Product Description Agent** (in CX1 PIM).
  - Coming soon: **Item Matching Agent**, **Product Grouping Agent**, Image Enhancement Agent, Merchandising/Promotions/Reporting Agents.

**Read on this:** their AI is aimed at *producing content* and *matching/grouping items*. Their moat on *facts* is the human Content Services team and the 10M-SKU library — i.e. **facts are still expensive and manual**. The unaddressed problem is: *when the library doesn't have the SKU, how do you get trustworthy attributes without paying a human, and how do you prove they're trustworthy?* That is precisely SKUTruth. Our pitch line writes itself:

> "HyperScale writes the copy. SKUTruth establishes the facts the copy is allowed to make."

Do **not** build: a description generator as the headline feature (they shipped it), item matching as the headline feature (it's on their roadmap), a PIM, a CMS, or search.

### A3. ETIM is the right taxonomy, it is free, and I have the data

- **Licence**: ETIM Classification Model + MC extension are released under **Open Data Commons Attribution Licence (ODC-BY 1.0)** — free to copy, distribute, adapt, and produce works from, with attribution. The xChange exchange standard is Apache-2.0. The **master ETIM English** model needs no membership or registration; only some *local language* versions are member-restricted.
- **Current release**: ETIM 10.0 (Dec 2024). ETIM North America publishes an American-English 10.0.
- **Verified by download** (`ETIM-10.0-ALL-SECTORS-CSV-METRIC-EI-2024-12-05.zip`, 2.9 MB, UTF-16, `;`-delimited):

| File | Rows | What it gives us |
|---|---:|---|
| `ETIMARTGROUP` | 160 | Top-level groups |
| `ETIMARTCLASS` | 5,641 | Product classes |
| `ETIMFEATURE` | 17,379 | Feature dictionary |
| `ETIMUNIT` | 189 | Canonical units |
| `ETIMVALUE` | 16,164 | Value dictionary |
| `ETIMARTCLASSFEATUREMAP` | 76,626 | **Expected features per class**, typed + unit-bound |
| `ETIMARTCLASSFEATUREVALUEMAP` | 201,285 | **Allowed values** per class-feature |
| `ETIMARTCLASSSYNONYMMAP` | 37,059 | Class synonyms (free lexical classifier candidates) |

Feature types across the model: `N` numeric 27,314 · `A` alphanumeric picklist 23,222 · `L` logical 22,014 · `R` range 4,075. Median 10 features/class, mean 13.6, max 121.

Concrete proof it is fit for purpose — `EC000066 "Power contactor, AC switching"` carries 21 features including:

```
EF001392 [N] A   Rated operation current Ie at AC-3, 400 V
EF001364 [N] kW  Rated operation power at AC-3, 400 V
EF003978 [R] V   Rated control supply voltage AC 50 Hz
EF008242 [A] –   Voltage type for actuating  ∈ {AC, DC, AC/DC}
EF006819 [A] –   Type of electrical connection of main circuit ∈ {Flat plug-in, Bolt, PCB, Screw}
EF001374 [N] –   Number of normally open contacts as main contact
EF000008/40/49 [N] mm  Width / Height / Depth
```

This is our schema, our unit dictionary, our enum validator, and our "expected attributes" list for gap analysis — **for free, and it's a real standard Unilog's electrical/HVAC/plumbing distributor customers actually ask for.**

**Taxonomy decision:** ETIM drives the attribute schema; UNSPSC is emitted as a secondary *code only*. UNSPSC classifies for spend analysis but **defines no attributes**, so it cannot drive gap analysis. eCl@ss is licence-encumbered and German-market-weighted. GS1 GPC is retail. ETIM is the only free standard that gives us typed attributes in Unilog's verticals.

### A4. Gemini — current models and real prices (verified on Google's pricing page, Aug 2026)

Per 1M tokens, input / output:

| Model | Std | Batch (−50%) | Free tier | Notes |
|---|---|---|---|---|
| `gemini-3.1-flash-lite` | $0.25 / $1.50 | $0.125 / $0.75 | yes | cheapest sane extractor |
| `gemini-3.5-flash-lite` | $0.30 / $2.50 | $0.15 / $1.25 | yes | GA |
| `gemini-3-flash-preview` | $0.50 / $3.00 | $0.25 / $1.50 | yes | preview |
| `gemini-3.6-flash` | $1.50 / $7.50 | $0.75 / $3.75 | yes | GA, agentic |
| `gemini-3.1-pro-preview` | $2.00–4.00 / $12–18 | −50% | no | escalation only |

- **Batch API: flat 50% discount** on every model → this *is* our catalog-scale story, and it's real, not hand-waved.
- **Context caching**: $0.15/1M + $1.00/1M/hour storage on Flash-class → cheap way to query one datasheet many times.
- **Grounding with Google Search**: Gemini 3.x gets **5,000 free requests/month**, then $14/1,000. Gemini 3 bills *per search query issued*, not per prompt.
- **URL Context tool**: supports HTML, JSON, XML, CSV, **PDF**, and images; max **20 URLs/request**, **34 MB/URL**; retrieved bytes bill as input tokens; **cannot** access paywalled content, YouTube, or private networks. **Combines with Search grounding** — the model can search, then deep-read the hits.
- Both Search grounding and URL Context are available on **Vertex AI** via the `google-genai` SDK.

### A5. Prior art and the real state of the field

- **`IndustryBench-MIPU`** (arXiv 2606.14383, 2026): the first large industrial product attribute-extraction benchmark — 4,559 products, 27,652 images, 103,703 annotations, 18 industrial categories. Headline result: frontier MLLMs hit **86–94% precision but recover only 49.9% of product-level attributes**; moving from single-image to multi-source costs **15–34 points**. Their conclusion: *"completeness, not single-source accuracy, is the core bottleneck."*
  **This is external, citable validation that our content-gap-analysis differentiator targets the actual bottleneck**, and it gives us a defensible reason to report recall/completeness as a headline metric rather than accuracy.
- **Commercial landscape** (Atronous, Parallel, Sixthshop, Outfindo, Productsup, Syndigo): provenance-per-field, source attribution, and per-attribute confidence are the **2026 table stakes** in this category, not a novelty. Grounding architecture and confidence-score methodology are explicitly what buyers now evaluate on.
  **Implication:** "we cite sources and show a confidence number" is no longer differentiating on its own. What differentiates is whether the confidence is *calibrated* and whether the system *knows when its sources aren't independent*. See §C.

---

## B. What I disagree with in the current plan

### B1. Scope. The plan is roughly 4–6 weeks of work and we have 14 days.

Eleven modules (`identity/ discovery/ ingestion/ extraction/ taxonomy/ normalization/ verification/ confidence/ gap_filling/ generation/ evaluation/`) plus eight UI screens plus a batch engine plus an evaluation harness is not deliverable at quality in 14 days by a small team. Shipping all of it badly loses to shipping 60% of it excellently. §H cuts it.

### B2. LLM-emitted confidence scores. Delete this.

The plan's example has the model returning `"Confidence: 0.98"`. LLM self-reported confidence is poorly calibrated and is, correctly, the first thing a reviewer will attack — "what does 0.98 mean, and how do you know?" There is no defensible answer if a language model made the number up.

**Replace with:** confidence computed by a small, transparent, *deterministic* function over measurable features (source authority prior, evidence modality, extraction agreement across independent sources, ETIM type/unit/enum validation pass, cross-attribute physical consistency, SKU-specificity of the evidence, document recency), with weights **fitted on our labelled eval set** and reported with a **reliability diagram + Expected Calibration Error**. Then "0.98" means "of the values we scored ≈0.98, ≈98% were correct on held-out data." That is a defensible sentence, and it's a differentiator competitors will not have.

### B3. The static source-authority hierarchy is too crude.

`manufacturer API > datasheet > product page > authorized distributor > trusted catalog > general web` is a reasonable *prior* but it's wrong as a decision rule, for a specific reason: **authority is a property of the (source, attribute, document-region) triple, not of the domain.** A manufacturer marketing page is *less* reliable for "rated operational current" than a distributor's parametric table transcribed from the datasheet. A datasheet's specification table is far more reliable than the same datasheet's prose introduction.

**Replace with:** authority prior on domain class **×** evidence-modality weight (parametric/spec table > labelled spec line > prose > marketing copy > image/OCR) **×** SKU-specificity (does the document name *this* orderable SKU, or a family?). Keep it a small explicit table we can print in the README, and **fit the weights on the eval set** rather than asserting them.

### B4. Naive multi-source agreement will manufacture false confidence. This is the subtlest and most valuable finding.

For an industrial MPN, "three sources agree" is usually **not** three independent observations — distributors, catalogue aggregators, and marketplaces copy the manufacturer's datasheet verbatim. Counting them as corroboration inflates confidence exactly where it is least warranted, and worse, **propagates a manufacturer typo into a high-confidence golden record**.

**Replace with:** an explicit **source-independence step** — near-duplicate detection (shingling / normalised-value + surrounding-text similarity) collapses copied evidence into a single *evidence cluster*, and confidence rewards **agreement across clusters**, not across URLs. Also: distributor disagreement with the manufacturer is *usually the distributor being wrong or listing a different variant*, so a raw "conflict" is often really an identity error — see B5.

### B5. "Conflict detection" is under-specified, and most real conflicts are identity conflicts.

The plan's example (datasheet 18 A vs distributor 16 A) is, in the real world, most often *not* two sources disagreeing about one product — it's two sources describing **two different SKUs**. We must classify conflicts by cause, because the correct action differs:

| Conflict class | Example | Correct action |
|---|---|---|
| **Variant conflict** | coil voltage 24 V vs 230 V for "LC1D18" | Not a conflict — attribute is *variant-dependent*. Abstain at family level, expose as a variant axis. |
| **Condition conflict** | 18 A vs 32 A rated current | Same product, different rating condition (AC-3 400 V vs AC-1). Fix by binding to the correct ETIM feature. |
| **Unit/format conflict** | 18 A vs 18000 mA vs "18" | Deterministic normalisation resolves it. Not a real conflict. |
| **Genuine factual conflict** | two sources, same SKU, same condition, different value | Adjudicate; escalate to the strong model; lower confidence; queue for review. |
| **Staleness conflict** | superseded product / revised datasheet | Prefer newer; flag lifecycle status. |

Only the fourth row deserves the dramatic "sources disagree" UI. Everything above it should be resolved *deterministically* — and the fact that we resolve them deterministically is itself a strong technical story.

### B6. "Verification" and "confidence" as separate modules is the wrong decomposition.

They share all their state and will develop a circular dependency within a day. Merge into one `adjudication` module (cluster → resolve → score → route).

### B7. Vector database / RAG: I recommend we do **not** build one, and say so loudly.

A manufacturer datasheet is 2–20 pages. Gemini reads PDFs natively with a 1M-token context. Chunking + embedding + retrieval would (a) add a retrieval-recall failure mode we don't currently have, (b) destroy page-level provenance, which is our headline feature, and (c) add infrastructure. **Whole-document long-context extraction with page anchors strictly dominates RAG at this document size.** For genuinely large documents (a 400-page catalogue), do a cheap deterministic page-level pre-filter — that's retrieval, but it's page-anchored and doesn't need a vector store.

Deliberately not using RAG, *with this justification written down*, is a stronger signal of engineering judgement than using it. The brief says the listed technologies "are NOT a checklist" — this is where we prove we read that sentence.

### B8. "Manufacturer API" as the top tier of the hierarchy is aspirational.

I found no general, free, public product-data API for Schneider Electric (the Resource Advisor API is energy-management, not product data). Realistic tiers are: manufacturer **datasheet PDF**, manufacturer product page, distributor with a real API (Nexar/Octopart has a free tier at ~1,000 matched parts/month; Digi-Key and Mouser require registered API keys), then general web. Keep "manufacturer API" in the schema as a source type, but don't promise it in the pitch.

### B9. Demo data reliability: the Schneider datasheet URL pattern does not generalise.

I probed `https://iportal2.schneider-electric.com/Contents/docs/SQD-{REF}_DATASHEET.PDF` against 11 references. **1 of 11 resolved** (`LC1D18P7` → 200, 138 KB PDF); `LC1D18B7`, `LC1D18BD`, `LC1D18M7`, `LC1D09BD`, `GV2ME08`, `A9F74210`, `XB4BA31` all 404. Any plan that assumes deterministic datasheet URLs is broken.

Also: **`se.com/robots.txt` disallows `/*/*/documents/*` and `/*/*/library/*`** — the paths where document downloads live. We should not point our own crawler there. See §F2 and §K4.

---

## C. What I would change

### C1. Make the hero demo *identity resolution*, using a real ambiguity we found

`Brand: Schneider Electric / MPN: LC1D18 / Description: Contactor` — the example in our own brief — **is not an orderable SKU.** It is a TeSys D family stem; the orderable references are `LC1D18B7`, `LC1D18BD`, `LC1D18M7`, `LC1D18P7`, … differing by **coil voltage**. (Confirmed: only the fully-qualified `LC1D18P7` has a datasheet.)

The correct system behaviour, and the single most impressive 30 seconds of our demo video:

> **Family detected, not a SKU.** 
> Attributes invariant across the family — rated operational current Ie @ AC-3 400 V = 18 A, 3 main poles, AC-3 power 7.5 kW — **resolved, high confidence, cited to the datasheet spec table**. 
> Attributes that vary by variant — rated control supply voltage, coil consumption — **abstained**, surfaced as a *variant axis* with the enumerated options, and routed to review with a one-click disambiguation.

No competitor doing "MPN → search → LLM → description" will produce that. It directly demonstrates abstention, evidence, gap analysis, and human-in-the-loop in one screen, on the exact input from the brief.

### C2. Add deterministic **cross-attribute physical consistency** checks

Source-agreement cannot catch a value that every source copied wrong. Physics can. For contactors: rated AC-3 power (kW) and rated AC-3 current (A) at 400 V must satisfy `P ≈ √3 · V · I · cosφ` within tolerance. Dimensions vs. weight sanity. Pole count vs. contact configuration. Value inside the ETIM feature's observed distribution for that class.

This is cheap, deterministic, explainable, catches a class of error nothing else catches, and is genuinely novel in this product category. It should be its own visible badge in the UI ("physically consistent ✓").

### C3. Make confidence **calibrated** and report the calibration

Per B2. Deliverables: reliability diagram, ECE, and a **risk–coverage curve** for the abstention policy (accuracy on the values we *did* commit to, as a function of what fraction we committed to; summarised as AURC). "We abstain 12% of the time" is not a metric. "At 88% coverage our committed values are 97.3% correct, versus 91.1% with no abstention" **is** a metric, and it is the single most convincing number we can put in the video.

### C4. Build **record/replay** into the network and model layer on day 1

Every outbound call (search, fetch, Gemini) goes through a cassette layer keyed by a hash of its inputs. Three modes:
- `live` — real calls, records cassettes;
- `replay` — cassette only, no network, deterministic and instant;
- `auto` — replay if cassette exists, else live.

This buys us four things at once: (1) the deployed judge-facing demo **cannot break** on a third-party outage or rate limit, (2) our eval numbers are **exactly reproducible** by a reviewer with no API key, (3) development is fast and free, (4) it's an honest, checkable answer to "did you really measure this?" Ship the cassettes in the repo.

This is not a demo trick and we must not present it as fake data — it is a recorded-interaction test fixture, and the README will say so plainly, with the live mode available and demonstrated in the video.

### C5. Reframe "scale" as measured cost and cache economics, not fake infrastructure

Scalability is an explicit judging criterion, and the honest, defensible version is:
- bounded-concurrency async worker pool (real, in-process, no Kafka, no microservices);
- **Gemini Batch API for catalog runs (a real, documented 50% price cut)**;
- content-addressed caching of fetched documents *and* of extraction results, keyed by `(document_hash, etim_class, feature_set, prompt_version, model)`;
- a measured **cost-per-SKU curve vs. catalog size**, showing marginal cost falling as cache hit rate rises (many SKUs in a catalog share a datasheet family);
- a **projection to 100k SKUs** stated as an explicit extrapolation from measured throughput, with the assumptions written down.

A chart of *measured* $/SKU and s/SKU with a cache-hit-rate line beats any architecture diagram claiming millions of SKUs.

### C6. Freeze the data contract, with corrections

The proposed contract is close. Changes: values are typed by ETIM feature type; provenance is per-evidence *and* per-cluster; confidence is decomposed so the UI can explain it; conflicts carry a cause class.

```jsonc
// ProductAttribute
{
  "etim_feature_id": "EF001392",
  "name": "Rated operation current Ie at AC-3, 400 V",
  "feature_type": "N",                    // N | A | L | R  (from ETIM)
  "value": { "kind": "numeric", "number": 18.0, "unit": "A" },
  "value_raw": "18 A",                    // as it appeared in the source
  "status": "VERIFIED",                   // VERIFIED | SINGLE_SOURCE | CONFLICTED
                                          // | VARIANT_DEPENDENT | INSUFFICIENT_EVIDENCE
  "confidence": 0.93,                     // calibrated, from confidence_factors
  "confidence_factors": {                 // every term shown in the Evidence Drawer
    "authority_prior": 0.95, "modality": 0.95, "sku_specificity": 1.0,
    "independent_cluster_agreement": 0.80, "etim_validation": 1.0,
    "physical_consistency": 1.0, "recency": 0.9
  },
  "evidence_clusters": [ /* EvidenceCluster[] — ranked */ ],
  "conflicts": [ /* Conflict[] */ ]
}

// EvidenceCluster — the unit of independent corroboration
{
  "cluster_id": "ec_01",
  "representative_value": "18 A",
  "independence_note": "3 URLs collapsed: near-duplicate of manufacturer datasheet text",
  "members": [ /* Evidence[] */ ]
}

// Evidence
{
  "source_url": "https://…/SQD-LC1D18P7_DATASHEET.PDF",
  "source_type": "MANUFACTURER_DATASHEET",  // …|MANUFACTURER_PAGE|DISTRIBUTOR|CATALOG|WEB
  "publisher": "Schneider Electric",
  "document_sha256": "…",                   // artifact in object storage, replayable
  "locator": { "page": 2, "section": "Main characteristics" },
  "quote": "Rated operational current Ie … 18 A",
  "modality": "SPEC_TABLE",                 // SPEC_TABLE|SPEC_LINE|PROSE|MARKETING|IMAGE_OCR
  "sku_specificity": "EXACT_SKU",           // EXACT_SKU | FAMILY | RANGE
  "retrieved_at": "2026-08-…", "extractor_model": "gemini-3.1-flash-lite",
  "prompt_version": "extract@v3", "run_id": "…"
}

// Conflict
{ "cause": "VARIANT" | "CONDITION" | "UNIT_FORMAT" | "FACTUAL" | "STALENESS",
  "values": [ … ], "resolution": "…", "resolved_by": "deterministic" | "escalated_model" | "human" }
```

**Rule:** this contract is frozen once agreed. Components adapt to it; it does not adapt to components.

### C7. Model routing — concrete, current, priced

| Stage | Model | Why |
|---|---|---|
| Class candidates (ETIM) | **no model** — lexical match over 37k ETIM synonyms + embeddings | deterministic, free, fast |
| Class selection among top-k | `gemini-3.1-flash-lite` | trivial multiple-choice |
| Attribute extraction from a document | `gemini-3.1-flash-lite`, structured output constrained to the ETIM class schema | bulk path, $0.25/$1.50 |
| Identity resolution / family-vs-SKU | `gemini-3-flash-preview` (or `3.6-flash` GA) | needs judgement |
| Escalation: factual conflicts, low-confidence, contradictory evidence | `gemini-3.1-pro-preview` | rare, worth the price |
| Commerce copy, fact-constrained | `gemini-3.6-flash` | quality matters, low volume |
| Catalog runs | same models via **Batch API** | −50% |

**Modelled cost per SKU** (to be *replaced with measured numbers* before submission — never ship the estimate as a result): ~40k input + 4k output tokens on flash-lite ≈ **$0.022/SKU**; with escalation on ~15% of SKUs, ≈ **$0.05/SKU**; on Batch, ≈ **$0.025/SKU**. A 1,000-SKU catalog run therefore costs tens of dollars, comfortably inside budget. Search grounding is free for our volume (5,000 requests/month on Gemini 3.x).

### C8. Guardrail: LLMs never emit free-text where ETIM defines a vocabulary

For `A` (picklist) features, the structured-output schema is generated from `ETIMARTCLASSFEATUREVALUEMAP` so the model can only choose an allowed value or `null`. For `N`/`R` features the schema enforces a number plus the ETIM-mandated unit. This eliminates an entire class of hallucination **deterministically, at the decoding layer**, and it is a direct, demonstrable answer to "how do you stop it inventing values?"

---

## D. What appears unnecessary

Cut, with reasons:

| Item | Verdict |
|---|---|
| Knowledge graph | No question it answers that a relational schema + ETIM doesn't. Cut. |
| Vector DB / RAG | Actively harmful at datasheet length (§B7). Cut, and justify in the README. |
| Multi-agent framework (LangGraph / CrewAI / ADK) | A pipeline with typed stages, retries, and caching is clearer, cheaper, and easier to defend than an agent framework. Cut. |
| "Dozens of agents" | Cut. Named stages, not personified agents. |
| Microservices | One API service + one worker. Cut. |
| Auth / RBAC / user management | A single demo reviewer role. Cut. |
| Custom model training / fine-tuning | Nothing in the research suggests it beats constrained decoding + ETIM validation, and we have no training data. Cut. |
| Vision-language image understanding | Tempting (nameplates!), but datasheets are the high-yield source and images are a recall long tail. **P2 at best.** |
| Separate `verification/` and `confidence/` modules | Merge (§B6). |
| Chatbot | Cut. |
| Full ETIM coverage in the demo | Load all 5,641 classes generically; *evaluate* on ~8–10. |
| Mobile / animations / marketing site | Cut until P0+P1 are excellent. |

---

## E. Missing opportunities (not in the current plan)

1. **Source-independence detection** (§B4). The most technically interesting idea available and nobody in the commercial landscape advertises it.
2. **Cross-attribute physical consistency** (§C2). Catches errors that agreement and provenance both miss.
3. **Calibration as a first-class deliverable** — reliability diagram + ECE + risk–coverage curve (§C3). Turns "trustworthy" from an adjective into a chart.
4. **Record/replay cassettes** (§C4) — reproducibility *and* demo safety from one mechanism.
5. **Golden-record diff / regression view.** Re-run a SKU after new evidence appears; show what changed, what got more confident, what broke. This is what a PIM operator actually lives with, and it's a 2-hour feature.
6. **Review decisions become eval labels.** Every human Accept/Edit/Reject writes a labelled datum; show the eval set growing. Closes the loop the challenge implies and makes HITL *measurable* instead of decorative.
7. **A deliberate trap set in the eval data** — a nonexistent MPN, a superseded product, a family stem, a distributor page with a wrong value, a unit-mismatched listing. Reporting how the system behaves on traps is far more persuasive than reporting accuracy on easy SKUs, and it is where naive competitors will visibly fail.
8. **"Before / after" catalog completeness on a real messy CSV.** One chart: ETIM-required attribute fill rate before vs. after, per class. That is the entire business case for Unilog in one image.
9. **Cite the external benchmark.** `IndustryBench-MIPU`'s 49.9% completeness ceiling gives us an independent yardstick to position against, and shows we read the literature.

---

## F. Major risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| F1 | **14 days.** Scope overrun → nothing polished. | **Critical** | §H MVP; hard P0/P1/P2 gate; feature freeze 20 Aug; 21–23 Aug reserved for video, README, deploy. |
| F2 | **Web access & robots.txt.** `se.com` disallows `/documents/` and `/library/`; direct crawling of manufacturer sites is not clean. | **High** | Primary path = Gemini **Search grounding + URL Context** (Google fetches; we don't operate a crawler). Secondary = a small, attributed, cached corpus of publicly downloadable datasheets for eval/demo. Respect robots.txt in any first-party fetcher; identify our UA; rate-limit. **Decision needed — §K4.** |
| F3 | **Datasheet discovery recall.** URL patterns don't generalise (1/11); search may not surface the right PDF. | High | Multi-strategy discovery (grounded search → URL context deep-read → distributor API fallback), and *measure discovery recall as its own metric*. Abstention is the honest failure mode, and we've made it a feature. |
| F4 | **False confidence from copied sources.** | High | §B4 independence clustering. If unmitigated, this is the flaw a sharp reviewer finds. |
| F5 | **Preview-model deprecation** (`gemini-3-flash-preview`, `3.1-pro-preview`). | Medium | Pin GA models on the critical path (`3.1-flash-lite`, `3.6-flash`); make model IDs config, not code; pin SDK versions. |
| F6 | **Credits don't cover the API we build against** ($300 GCP trial excludes AI Studio Gemini API). | Medium | Build on **Vertex AI** via `google-genai`; provider abstraction so switching is a config change. **§K1.** |
| F7 | **Live demo failure during unattended judging.** | Medium | Replay mode as the default for the public demo; live mode behind a toggle, shown in the video. |
| F8 | **Ground-truth labelling is slower than it looks.** ~50 SKUs × ~12 attributes ≈ 600 labels read off real datasheets. | Medium | Start day 1, timebox to 2 people × 1.5 days, semi-automate (model proposes, human verifies from the PDF), record labeller + source page per label. |
| F9 | **IP transfer on winning.** Ownership of winning solutions transfers to the organisers. | Low–Medium (non-technical) | Flagged for your decision — **§K3**. Keep any code you want to retain out of the submission repo. |
| F10 | **Eligibility.** Undergraduate engineering students at recognised Indian colleges only. | Low | **§K2** — confirm before we invest. |

---

## G. Recommended final architecture

Deliberately boring where boring is correct; the novelty is concentrated in adjudication, calibration, and evidence.

```
┌── Next.js (App Router, TS, Tailwind, shadcn) ───────────────────────────┐
│  Dashboard · New Enrichment · Live Run · Golden Record + Evidence       │
│  Drawer · Review Queue · Batch Run · Evaluation Dashboard               │
└──────────────────────────── HTTPS / SSE ───────────────────────────────┘
                                   │
┌── FastAPI (Cloud Run) ─────────────────────────────────────────────────┐
│  /enrich  /runs/{id}/stream(SSE)  /records/{id}  /review  /batch  /eval │
├────────────────────────────────────────────────────────────────────────┤
│  pipeline/  — typed stages, retry + cache + cost meter on every stage   │
│    1 identity      resolve brand+MPN → SKU | FAMILY | UNKNOWN           │
│    2 classify      ETIM class (lexical+embed candidates → LLM pick)     │
│    3 discover      grounded search → ranked candidate documents         │
│    4 ingest        fetch/cache → content-addressed artifact + page map  │
│    5 extract       ETIM-schema-constrained structured output per doc    │
│    6 normalize     units, ranges, enums — DETERMINISTIC (ETIM tables)   │
│    7 adjudicate    independence-cluster → conflict class → resolve      │
│                    → calibrated confidence → route (accept|abstain|HITL)│
│    8 gap           ETIM expected − verified = missing → targeted re-run │
│    9 generate      commerce copy constrained to VERIFIED facts only     │
│   10 export        JSON / CSV / BMEcat-flavoured ETIM output            │
├────────────────────────────────────────────────────────────────────────┤
│  llm/      google-genai → Vertex AI; router; structured output;         │
│            token+cost meter; prompt registry (versioned, hashed)        │
│  net/      cassette layer: live | replay | auto  (§C4)                  │
│  etim/     loader + typed schema + unit/enum validators (deterministic) │
│  eval/     runner, metrics, calibration, reports  (BUILT FIRST)         │
└────────────────────────────────────────────────────────────────────────┘
        │                        │                          │
   Postgres                  GCS bucket                 Cassettes
 (records, evidence,     (PDFs, page images,        (checked into repo,
  runs, costs, labels)    content-addressed)         reviewer-runnable)
```

**Stack decisions and why:**
- **Python 3.12 + FastAPI** — agreed with the plan. Pydantic gives us the frozen data contract *and* the Gemini structured-output schemas from one source of truth.
- **Next.js 15 + TypeScript + Tailwind + shadcn/ui** — agreed. Evidence Drawer is the product; it needs a real component library.
- **Postgres** — records, attributes, evidence, runs, costs, labels. Relational is right; there is no graph problem here.
- **In-process async worker with bounded concurrency**, not Celery/Redis/Kafka. Cloud Run scales the container; that *is* the horizontal story.
- **Cloud Run** for API+worker. Frontend on Cloud Run or Vercel.
- **No vector DB, no agent framework, no message broker** — each an explicit, documented decision (§B7, §D).

**Module list vs. the plan:** `verification/` + `confidence/` → merged into `adjudicate`. `taxonomy/` + `normalization/` → merged into deterministic `etim/`. `net/` (cassettes) and `llm/` (routing + cost) added. Net: 10 pipeline stages, 4 support packages.

---

## H. Recommended MVP (14 days, P0 / P1 / P2)

**P0 — the submission fails without these.** Target: complete by 17 Aug.

1. Frozen data contract (§C6) as Pydantic models + Postgres schema + migrations.
2. `etim/` loader: ETIM 10.0 → typed schema, units, enums, synonyms; deterministic validators. *(Attribution notice for ODC-BY.)*
3. `net/` cassette layer, live|replay|auto. **Day 1** — everything else depends on it.
4. `eval/` harness + the labelled dataset (~50 SKUs, 8–10 ETIM classes, ≥3 manufacturers, **including traps**). **Days 1–3, before the pipeline works.**
5. Single-SKU pipeline end to end: identity → classify → discover → ingest → extract → normalize → adjudicate → gap → generate → export.
6. Abstention that actually abstains, with `INSUFFICIENT_EVIDENCE` surfaced in the UI.
7. **Golden Product Record + Evidence Drawer** — the highest-value screen. Click a spec → value, status, calibrated confidence *with its factor breakdown*, evidence clusters with quote + page + link, conflicts with cause.
8. Live Enrichment Run (SSE) showing stages, per-stage latency, tokens, and running cost.
9. Batch CSV → run → per-SKU status → export, with measured throughput/cost.
10. Review Queue: only abstained / conflicted / low-confidence items; Accept / Edit / Reject writes an eval label.
11. Evaluation dashboard rendering **measured** numbers from a committed eval run.
12. Deployed, reachable, replay-mode-safe. README + architecture doc + demo video.

**P1 — competitive differentiators.** 18–20 Aug.

13. Source-independence clustering (§B4).
14. Confidence calibration: fit + reliability diagram + ECE + risk–coverage curve (§C3).
15. Family-vs-SKU identity resolution with variant-axis surfacing — the hero demo (§C1).
16. Cross-attribute physical consistency checks (§C2).
17. Conflict cause classification (§B5), with deterministic resolution for variant/condition/unit classes.
18. Before/after ETIM completeness chart per class.
19. Model routing + escalation, with cost-per-SKU measured per tier.

**P2 — only if P0+P1 are excellent.**

20. Golden-record diff / re-run regression view.
21. Nameplate/label image understanding.
22. Distributor API connector (Nexar free tier).
23. BMEcat/ETIM xChange export.
24. Prompt-version A/B on the eval set.

**Freeze 20 Aug. 21–23 Aug: video, README, deploy, buffer. Submit 22 Aug, not 23.**

---

## I. Recommended "winning differentiators" (the five sentences of the pitch)

1. **"We never let the model invent a value."** ETIM-constrained decoding + abstention. `INSUFFICIENT_EVIDENCE` is a first-class output, and we measure how often we correctly refuse.
2. **"Our confidence is calibrated, and here is the curve."** Not an LLM's self-report — a fitted function over measurable evidence features, with a reliability diagram, ECE, and a risk–coverage curve on held-out data.
3. **"We know when our sources are not independent."** Three distributors copying one datasheet is one piece of evidence, not three. Nobody else in this category says this.
4. **"We check the physics, not just the citations."** Deterministic cross-attribute consistency catches errors that every source agreed on.
5. **"Identity before enrichment."** `LC1D18` is a family, not a SKU — we detect it, resolve what's invariant, abstain on what varies, and ask one precise question. *A perfect record for the wrong SKU is worse than no record.*

Underneath all five: **every number in the submission is measured and reproducible from committed cassettes with no API key.**

---

## J. What should deliberately NOT be built

Everything in §D, plus, stated for the record in the README as *engineering decisions with reasons*:

- No knowledge graph. No vector database. No RAG. No agent framework. No microservices. No message broker. No fine-tuning. No auth/RBAC/billing. No chatbot. No mobile. No animation work before 20 Aug.
- No claim we can process millions of SKUs. We will show measured throughput and cost and an explicitly-labelled extrapolation.
- **No fabricated benchmark numbers, ever.** Any metric not yet measured is absent from the document, not estimated into it.

---

## K. Questions that materially block implementation

**Resolved 2026-08-09:**

- **K1 — Credits: Google Cloud billing credit.** → We build on **Vertex AI** via `google-genai` with `vertexai=True`, behind a provider abstraction so the Developer API stays a config switch. The AI Studio Gemini API is off the table for spend (the GCP trial credit excludes it). Region and quota to be confirmed at first call; Vertex model IDs pinned to GA on the critical path.
- **K2 — Eligibility: confirmed.** Undergraduate engineering students, recognised Indian college.
- **K4 — Web access: conservative path confirmed.** Live discovery = Gemini **Search grounding + URL Context** (Google performs the fetch; results carry citations; we operate no crawler). Eval/demo = a small **curated, attributed corpus** of publicly-downloadable manufacturer datasheets, content-addressed and cached. No first-party crawler against manufacturer sites in v1. `robots.txt` compliance is a stated project policy in the README.
- **K5 — Team: 2 registered participants; Claude Code does the implementation.** Practical consequence: engineering throughput is not the binding constraint — **human review time is**. Ground-truth labelling and demo-video production are the two tasks that cannot be delegated, so both are front-loaded and semi-automated (model proposes a label with its datasheet page citation; the human confirms or corrects in a purpose-built labelling view). P1 stays intact; P2 items 20 and 22 are stretch.

**Still open (not blocking — answer before 20 Aug):**

- **K3 — IP transfer.** *"Ownership of the IP rights for winning solutions will be transferred to the program organizers upon confirmation of the award."* Confirm you're comfortable. It only affects whether we keep anything reusable outside the submission repo.
- **K6 — Scope confirmation.** Accept the P0/P1/P2 cut: no image/vision understanding in the MVP, ~8–10 ETIM classes evaluated (loader generic over all 5,641), ~50 labelled SKUs, feature freeze 20 Aug, submit 22 Aug.

---

## Sources

- [UniHack event page — Unilog × Hack2Skill](https://hack2skill.com/event/unilog2026)
- [UniHack listing (timeline, prizes)](https://hiretoday.in/competitiondetails/40000127)
- [Unilog HyperScale — AI agent roadmap](https://www.unilogcorp.com/hyperscale/)
- [Unilog CX1 Product Content](https://www.unilogcorp.com/platform/product-content/)
- [ETIM licence info (ODC-BY 1.0)](https://www.etim-international.com/classification/license-info/)
- [ETIM tools & public API](https://www.etim-international.com/tools/)
- [ETIM downloads archive (10.0 all-sectors CSV)](https://www.etim-international.com/downloads/)
- [Gemini API pricing](https://ai.google.dev/gemini-api/docs/pricing)
- [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- [Gemini URL Context tool](https://ai.google.dev/gemini-api/docs/url-context)
- [Grounding with Google Search](https://ai.google.dev/gemini-api/docs/google-search)
- [Google Cloud free trial — credit exclusions](https://docs.cloud.google.com/free/docs/free-cloud-features)
- [IndustryBench-MIPU (arXiv 2606.14383)](https://arxiv.org/abs/2606.14383)
- [ETIM vs UNSPSC vs eCl@ss comparison](https://getclaro.ai/resources/comparisons/etim-vs-unspsc-vs-eclass/)
- [Nexar/Octopart API plans](https://nexar.com/compare-plans)
