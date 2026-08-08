# Overall Verdict

YELLOW

SKUTruth is solving the challenge's actual problem and can become a strong submission, but `RESEARCH_VERDICT.md` is not yet a safe implementation contract. Its core direction—identity before enrichment, schema-constrained extraction, per-attribute evidence, deterministic normalization, and explicit abstention—is strong. Its weaknesses are overclaiming differentiation from Unilog, treating ETIM features as a completeness checklist, overstating what Google grounding proves, proposing statistical calibration from too little independent data, and retaining far too many P0 surfaces for a 14-day build.

Go forward only with the reduced vertical slice described below. Do not implement the original P0 list as written.

# Executive Summary

The product thesis is good: turn sparse brand/MPN text into a structured product record while refusing unsupported facts and showing exactly why accepted facts were accepted. That directly addresses all four official outcomes shown in the supplied challenge screenshot.

The strongest version of the pitch is not “AI enrichment,” because Unilog already offers custom SKU creation, enrichment, normalization, gap filling, taxonomy work, parent/child grouping, and a 10M+ product content library. Unilog publicly describes those services itself. The defensible wedge is: **an auditable decision layer that reduces the amount of expert verification required for long-tail and newly introduced SKUs, and exports accepted facts into an existing PIM.** This complements Unilog, but it does overlap with work Unilog already performs. [Unilog Content Services](https://www.unilogcorp.com/platform/product-content/content-services/), [Unilog product-content gap-fill description](https://www.unilogcorp.com/resources/blog-posts/enrich-differentiate-and-convert-with-custom-product-content-services/), [Unilog Content Subscription](https://www.unilogcorp.com/platform/product-content/content-subscription/)

ETIM should remain central to the selected electrical/HVAC/plumbing demonstration vertical, but secondary to identity and evidence in the overall architecture. It supplies classes, typed features, units, and allowed alphanumeric values; it does not establish that a product value is true, does not make every class feature mandatory, and does not cover every commerce field or every Unilog vertical. ETIM's license claim is substantially correct: the model is ODC-BY 1.0, master ETIM English is open, and public use requires attribution and preservation of license notices. [ETIM license](https://www.etim-international.com/classification/license-info/), [ETIM model information](https://www.etim-international.com/classification/model-information/)

Identity resolution must be P0. `LC1D18` is a valuable hero input because Schneider uses it as a device/range stem while actual commercial references append coil codes such as `B7` and `P7`. However, the demo must say “family or incomplete commercial reference,” not universally “not a SKU,” and it must prove invariance across variants rather than copying invariant-looking values from one child. Schneider's own exact product page identifies `LC1D18P7` and its 230 V AC coil; its datasheet separately lists 18 A AC-3, 32 A AC-1, and 7.5 kW at 380–400 V, demonstrating both variant and condition ambiguity. [Schneider LC1D18P7 product page](https://www.se.com/uk/en/product/LC1D18P7/tesys-d-contactor-3p3-no-ac3-440-v-18-a-230-v-ac-coil/), [Schneider LC1D18P7 datasheet](https://iportal.se.com/Contents/docs/SQD-LC1D18P7_DATASHEET.PDF)

The no-generic-RAG decision is appropriate for P0, but “whole document strictly dominates RAG” is false. Page-preserving chunks can improve provenance, and long context does not guarantee recall. Use whole-document extraction for small datasheets with a deterministic page map, then a page-level/table-aware fallback for long catalogs. No vector database is needed.

Confidence-factor logging belongs in P0. Statistical calibration does not. Fifty SKUs may contain hundreds of attribute labels, but those labels are correlated within product families, documents, manufacturers, and ETIM classes. The effective independent sample is much closer to 50 than to the raw attribute count. Show support factors and coarse evidence grades; do not show `0.973`. Calibration becomes P2 after grouped held-out results are credible.

Record/replay is good engineering if strict and conspicuous. It becomes misleading if replay looks like a live run, if `auto` mixes recorded and fresh calls without disclosure, or if replay metrics are presented as current model performance. Public replay and gated live mode should be visually and operationally separate.

The winning 30-second sequence is: sparse input → identity warning → exact missing discriminator (“coil voltage”) → one-click variant resolution → ETIM record → click one value and open the real PDF page with the source text highlighted. The highest wow-to-effort feature is the verified evidence highlight plus the variant axis. The lowest-value spectacle is a live token/cost stream.

# Is the Core Idea Strong Enough?

Yes, conditionally. A polished narrow implementation would be difficult for generic “search + LLM + JSON” teams to beat because it makes correctness visible and falsifiable.

The idea is strongest when it is framed as **decision support for product-data operations**:

- It determines whether the input identifies an exact orderable item.
- It extracts only schema-relevant facts.
- It verifies every accepted value against a retrievable source span.
- It distinguishes “not found,” “variant-dependent,” “conflicting,” and “not applicable.”
- It sends only unresolved decisions to a person.
- It reports verified coverage and unsupported-claim rate, not just how many fields it filled.

The idea weakens when it claims a new product-content category, calibrated truth, physical validation, universal ETIM coverage, or catalog scale without enough evidence. Those claims are easy for a judge or technical buyer to puncture.

The business KPI should not be only completeness. Unilog already knows how to produce complete catalog content. The stronger buyer-facing KPI is **expert minutes per accepted attribute or per completed SKU**, alongside unsupported-claim rate. That directly expresses whether SKUTruth reduces the expensive manual step in Unilog's current service workflow.

# Challenge Alignment

Alignment is strong:

| Official outcome | SKUTruth behavior | Required proof |
|---|---|---|
| Structured intelligence from limited inputs | Brand/MPN/description to typed record | A locked sparse-input test set, not only the hero SKU |
| Improve quality and consistency | ETIM types, unit normalization, enum validation | Correctness before/after, not fill-rate alone |
| Validate and enrich with traceable outputs | Per-attribute source, page, quote, document hash | Quote/page verification against the actual artifact |
| Scale across catalogs | Idempotent batch processing, caching, bounded concurrency | Measured throughput, failures, and cost under stated conditions |

The risk is product drift. Description generation, chatbot behavior, marketing copy, and a new PIM are not required to satisfy the challenge. The supplied challenge wording emphasizes creation, enrichment, validation, traceability, and scale. The reduced vertical slice covers all five without building a broad platform.

“Scalability” does not require a 100,000-SKU run. It does require evidence that the design does not lose work, duplicate paid calls, or collapse under rate limits. A 25–50 SKU measured batch with explicit cache-hit assumptions is more credible than an unsupported large extrapolation.

# What Claude Got Right

- **Identity before enrichment.** A correct record for the wrong variant is a serious failure. Making exact/family/unknown an explicit gate is the most important architectural correction.
- **Typed pipeline rather than an agent framework.** The work is a stateful, testable pipeline. A multi-agent label would add failure modes without increasing product value.
- **ETIM for deterministic constraints.** ETIM officially defines class features, feature types, units, and fixed values for alphanumeric features. That is a strong way to reduce free-form model decisions. [ETIM model information](https://www.etim-international.com/classification/model-information/)
- **No generic vector database for ordinary datasheets.** It is unnecessary for the first vertical slice.
- **Per-attribute provenance.** Product-record-level citations are too coarse; evidence must attach to each claim.
- **Reject LLM self-reported confidence.** A model-generated `0.98` has no operational meaning.
- **Copied sources are not independent corroboration.** Counting URLs is a known way to manufacture certainty.
- **Separate unit/condition/variant differences from factual contradictions.** The Schneider datasheet itself demonstrates why `18 A` and `32 A` are not a factual conflict: they apply to AC-3 and AC-1 respectively. [Schneider datasheet](https://iportal.se.com/Contents/docs/SQD-LC1D18P7_DATASHEET.PDF)
- **Abstention as a first-class output.** This is essential for a trust-oriented product.
- **Curated evaluation corpus and recorded interactions.** Reproducibility is necessary for an unattended submission.
- **Measure cost and latency rather than claim automatic scale.** This is the correct standard of proof.
- **Cut knowledge graphs, microservices, generic RAG, fine-tuning, and chatbot work.** None is needed for the stated problem.

# What Claude Got Wrong

1. **Unilog overlap is understated.** The verdict infers from a public AI roadmap that Unilog does not address verification, but absence from a marketing page is not evidence of absence. Unilog publicly sells custom SKU creation, gap fill, cleansing, standardization, taxonomy, attribute mapping, validation, and parent/child grouping. Why it matters: judges from Unilog may immediately recognize their existing workflow. Judging risk: high. Smallest fix: position SKUTruth as an auditable automation and triage layer for their content operation, and measure review labor saved. [Unilog HyperScale](https://www.unilogcorp.com/hyperscale/), [Unilog custom content](https://www.unilogcorp.com/resources/blog-posts/enhanced-product-content-the-complete-guide-for-b2b-distributors/)

2. **ETIM “expected” is being conflated with “required.”** ETIM features characterize a class, but the public model documentation does not make every mapped feature mandatory for every product or every commerce channel. Why it matters: a gap score can penalize inapplicable fields and reward unnecessary filling. Judging risk: medium-high. Smallest fix: call the measure “ETIM feature coverage,” add `NOT_APPLICABLE`, and define a small buyer-critical subset per demo class.

3. **The ETIM counts appear to include CSV headers.** ETIM's own release material describes 5,640 classes, while the verdict reports 5,641 rows—consistent with counting the header. Other table counts should be rechecked the same way. Why it matters: minor numerically, major as a trust signal in a product about data quality. Judging risk: medium if quoted in the pitch. Smallest fix: count parsed records after header removal and commit a reproducible statistics script. [ETIM 10 release information](https://www.etim-international.com/new-release-etim-10-0-available/)

4. **Google grounding is not page-level provenance.** URL Context returns inline annotations tying generated response segments to a URL and retrieval status metadata; it does not by itself prove the quoted text exists on a stated PDF page. Google Search grounding may also return no grounding metadata. Why it matters: the Evidence Drawer is the product's trust claim. Judging risk: critical. Smallest fix: use search only for discovery, ingest the selected artifact, build a deterministic page map, and verify every accepted quote against that page. [Google URL Context response documentation](https://ai.google.dev/gemini-api/docs/url-context), [Vertex grounding behavior](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/ground-with-google-search)

5. **“No RAG strictly dominates” is an overcorrection.** Chunking does not inherently destroy provenance; a page-preserving chunk can improve it. Long context can still miss tables or confuse repeated conditions. Why it matters: one long catalog will break an absolute design claim. Judging risk: medium. Smallest fix: state a size-based policy: whole-document for small datasheets, deterministic page/table retrieval for large documents, no vector database in v1.

6. **The proposed contactor physics check is unsafe.** Motor output power is not simply `sqrt(3) × V × I × cos(phi)` without efficiency, load, duty, utilization category, and manufacturer rating context. The Schneider values are catalog ratings, not a complete motor operating point. Why it matters: the system could label correct manufacturer data “physically inconsistent.” Judging risk: high if demonstrated. Smallest fix: remove the formula badge; retain only exact logical constraints whose preconditions are fully encoded and domain-reviewed.

7. **Fifty SKUs do not support the proposed calibration claim.** Attribute rows are not independent samples, and 8–10 classes leave only a handful of held-out products per class. Why it matters: a reliability diagram can create statistical theater. Judging risk: high with an ML reviewer. Smallest fix: log factors now, use coarse support grades, group all splits by product family, and defer probability calibration.

8. **The proposed P0 remains too large.** Twelve deliverables include two applications' worth of UI, full ETIM, single and batch flows, a review queue, SSE telemetry, evaluation dashboards, deployment, and content generation. Why it matters: polish and correctness will suffer. Judging risk: critical. Smallest fix: one class family/vertical, one record screen, one evidence drawer, one small evaluation report, one replay-safe deployment.

9. **In-process background work on a Cloud Run service is not a durable catalog architecture.** Cloud Run service requests time out, instances can disappear, and retries can duplicate work. Cloud Run distinguishes request-serving services from jobs that run to completion. Why it matters: “Cloud Run scales the container” does not prove job durability. Judging risk: medium-high when scale is questioned. Smallest fix: P0 measures a bounded batch; P1 uses idempotent persisted stages and a Cloud Run Job or Cloud Tasks. [Cloud Run request timeouts](https://docs.cloud.google.com/run/docs/configuring/request-timeout), [Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs), [Cloud Tasks with Cloud Run](https://docs.cloud.google.com/run/docs/triggering/using-tasks)

10. **The identity conclusion is phrased too absolutely.** `LC1D18` is clearly a family/device stem in Schneider material, but some channels may use a base reference or configurable product record. Why it matters: a judge could find a listing that calls it a product reference. Judging risk: medium. Smallest fix: output `FAMILY_OR_INCOMPLETE_REFERENCE`, cite the missing coil discriminator, and resolve to an exact child only after evidence or user selection.

# Assumptions That Need Verification

| Assumption | Current status | Required verification before implementation |
|---|---|---|
| Submission closes 23 Aug 2026 and judging is unattended | Likely; the supplied screenshot appears to show `14d:08h:30m`, with the leading character obscured by the modal | Save an organizer-issued rules/timeline PDF or full-page screenshot; do not rely on a dynamic page or secondary listing |
| Winning IP transfers to organizers | Not independently recoverable from the dynamically rendered event page in this review | Obtain the exact terms, scope of assigned IP, timing, third-party/open-source treatment, and contributor consent |
| ETIM English 10.0 can be redistributed | Verified subject to ODC-BY attribution and notice requirements | Add attribution, license link, version/date, and modification notice; verify whether the submission ships the database or a derived subset [ETIM license](https://www.etim-international.com/classification/license-info/) |
| Every ETIM feature is a gap obligation | Not verified and likely false as stated | Define `required_for_demo`, `available_in_ETIM`, and `not_applicable` separately |
| LC1D18 is always non-orderable | Too absolute | Verify with at least one Schneider family source and multiple exact child references; use “incomplete/family-level” wording |
| Google Search + URL Context is available with identical behavior, price, and model IDs on the chosen Vertex endpoint | Partially verified, but product surfaces and documentation differ | Run a day-one spike on the exact project, region, SDK version, model, structured-output schema, PDF, Search, and URL Context combination |
| URL Context preserves page evidence | Not verified; public docs describe URL annotations, not page anchors | Build and test local page-span verification |
| Batch API supports every tool used by the live pipeline | Not established | Smoke-test structured extraction and any server-side tools separately; do not make it the scale story until proven |
| Search is “free for our volume” | Unsafe budgeting assumption: Gemini 3 billing can count multiple search queries per request after the allowance | Meter actual search queries and set a hard budget; pricing states a prompt can generate multiple billable searches [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing) |
| Public manufacturer PDFs may be committed and redistributed | Public availability does not automatically grant redistribution rights | Prefer URLs, hashes, minimal quoted spans, and permission-compatible fixtures; review each corpus license/terms |
| Fifty products can be labeled in 1.5 person-days | Optimistic | Time a five-SKU pilot including dual review, qualifiers, page citations, and family variants before committing |

# Architecture Review

The high-level shape—one typed API, one web UI, relational data, object storage, and explicit pipeline stages—is sensible. No knowledge graph, agent framework, or microservice split is needed.

The data contract should be revised before code:

- Separate `identity_status` from attribute status: `EXACT`, `FAMILY_OR_INCOMPLETE`, `UNKNOWN`, `CONTRADICTORY`.
- Add `applicability`: `APPLICABLE`, `NOT_APPLICABLE`, `UNKNOWN`.
- Make conditions first-class structured data rather than part of a feature label only: utilization category, voltage, frequency, temperature, phase, min/typ/max, and region/standard where relevant.
- Preserve both `source_artifact_url` and a content hash. A search citation URL is not necessarily the final artifact URL.
- Store a verifiable locator: page index, normalized quote, start/end offsets where text extraction works, and a rendered page region when tables/OCR make offsets unreliable.
- Add `evidence_verification`: `EXACT_SPAN`, `FUZZY_OCR_SPAN`, `UNVERIFIED`; only the first two may support accepted output.
- Store `run_mode`: `LIVE`, `REPLAY`, or `MIXED`, plus cassette capture time and model/prompt versions.
- Replace a single `confidence` field in P0 with `support_grade` and raw factors.
- Add `INAPPLICABLE`, `NOT_FOUND`, `VARIANT_DEPENDENT`, `CONFLICTED`, and `UNSUPPORTED` instead of overloading `INSUFFICIENT_EVIDENCE`.

Postgres and GCS are reasonable deployment choices but not judging differentiators. Do not spend early days on generalized migrations, object lifecycle policy, or a complex repository pattern. Conversely, do not claim scale from an in-memory worker. Persist stage idempotency keys and results before any scale demonstration.

The ten-stage pipeline should be reduced for P0 to six observable decisions: identify → classify → discover/ingest → extract/verify → normalize/adjudicate → present/evaluate. “Gap rerun,” commerce generation, export variants, and asynchronous review workflows can wait.

# ETIM Review

**Recommendation: central to the chosen technical-product vertical and attribute contract; secondary to identity/evidence globally; not removed.**

What ETIM validly provides:

- Stable product-class and feature identifiers.
- Four explicit feature types (`A`, `L`, `N`, `R`).
- Units for numeric/range features.
- Fixed allowed values for alphanumeric features.
- Class synonyms useful for candidate generation.
- A standard, attributable structure for exchanging technical facts.

These claims match ETIM's official model description. [ETIM model information](https://www.etim-international.com/classification/model-information/)

What ETIM does not provide:

- Proof that an extracted value is true.
- An exact manufacturer SKU identity graph.
- A universal required-field list for a commerce channel.
- Rich conditions for every compound rating as a separate machine-readable object.
- All commerce attributes such as GTIN, packaging, lifecycle, marketing assets, logistics, compatibility, and channel-specific copy.
- Universal coverage for every industrial category Unilog may serve.

The licensing analysis is basically right. ODC-BY permits sharing, creating, and adapting with attribution and retained notices; English master access is open. Treat attribution as a product requirement, not a README afterthought. [ETIM license](https://www.etim-international.com/classification/license-info/), [ETIM 10 downloads](https://www.etim-international.com/downloads/)

Smallest strong implementation:

1. Load only the ETIM 10 records necessary for the evaluated classes, while keeping the loader generic.
2. Commit a reproducible parser/statistics test that excludes headers and asserts referential integrity.
3. Use ETIM for candidate features, types, units, and enum validation.
4. Define a hand-reviewed `buyer_critical` subset for completeness scoring.
5. Support `NOT_APPLICABLE` and explain that ETIM feature coverage is not mandatory completeness.
6. Version every exported record with `etim_release=10.0` and the language code.

# Identity Resolution Review

Identity-first is sound and should be P0. It should also be a hard gate: when exact identity is unresolved, downstream stages may emit only facts explicitly proven invariant at the family level.

The LC1D18 example is technically useful. Schneider's exact `LC1D18P7` record includes the suffix and identifies a 230 V AC coil. Another exact child, `LC1D18B7`, is documented with a 24 V AC coil. This supports the claim that the suffix carries a variant discriminator. [LC1D18P7](https://www.se.com/uk/en/product/LC1D18P7/tesys-d-contactor-3p3-no-ac3-440-v-18-a-230-v-ac-coil/), [LC1D18B7 datasheet](https://iportal2.schneider-electric.com/Contents/docs/SQD-LC1D18B7.PDF)

The unsafe leap is to call attributes invariant after observing only one child. The system needs either a manufacturer family table or evidence across multiple child references. Otherwise, “18 A, 3 poles, 7.5 kW are invariant” is another inference, not verified product intelligence.

Minimum defensible identity implementation:

- Normalize brand aliases and MPN punctuation/case.
- Require exact MPN text in a manufacturer artifact or exact product page for `EXACT`.
- Detect family/incomplete status from explicit child references, a required configurator choice, or multiple suffix-specific exact documents.
- Capture the variant axis and known options only from evidence.
- Ask one precise disambiguation question, such as coil voltage/type.
- Re-run identity after selection and visibly change status from family to exact.
- Include at least five non-Schneider family/incomplete traps so the feature is not obviously hard-coded.

Identity evaluation should be product-level accuracy over `EXACT/FAMILY_OR_INCOMPLETE/UNKNOWN/CONTRADICTORY`, plus the false-exact rate. False exactness is the most dangerous error and should be reported separately.

# Evidence & Provenance Review

Per-field evidence is necessary but not sufficient. The evidence must be mechanically checkable.

For every accepted value, store:

- final publisher and artifact URL;
- document hash and retrieval time;
- exact identity scope: exact SKU, family, or range;
- page number and page count;
- normalized quote or table cell context;
- quote verification status;
- extraction model, prompt/schema version, and run mode;
- condition qualifiers bound to the value;
- source artifact version/date where available.

Search grounding should discover candidates, not establish final evidence. Google documents that URL Context annotates generated response segments with source URLs and returns retrieval status; this is useful traceability, but it is not page-level proof. [Google URL Context](https://ai.google.dev/gemini-api/docs/url-context)

The source-discovery policy also needs a clearer legal and operational boundary. Google says Vertex Search grounding excludes pages that opt out through `Google-Extended`, but using Google's fetch does not grant SKUTruth permission to redistribute a document, does not prove that an artifact is current, and does not replace review of publisher terms. `robots.txt` is a crawl-control signal, not a content license. P0 should therefore use manually reviewed, attributed artifact URLs and a curated corpus; it should not operate a general crawler. For a live search hit, either ingest the artifact through an allowed, controlled path and verify it, or present it only as an unverified discovery candidate. [Vertex grounding and Google-Extended](https://cloud.google.com/vertex-ai/generative-ai/docs/multimodal/ground-with-google-search)

Smallest strong verification path:

1. Select a candidate manufacturer artifact.
2. Retrieve it through a controlled fetch path or from the curated corpus.
3. Hash it and render/extract it page by page.
4. Ask the model for value, raw quote, page, and conditions.
5. Normalize and locate the quote on that page.
6. Reject or downgrade evidence when the quote cannot be located.
7. In the UI, open the rendered page and highlight the supporting region.

Do not claim “we never let the model invent a value.” A model can still fabricate a quote or page. The accurate claim is: **“No value is accepted unless its supporting span is verified in a versioned source artifact.”**

# Source Independence Review

The concept is technically worthwhile, but a robust provenance graph is not achievable in 14 days and should not be P0.

The smallest defensible P1 implementation is conservative deduplication:

- Exact document hash collapses identical PDFs.
- Canonical publisher/document reference collapses localized mirrors of the same manufacturer artifact when known.
- Normalize the value plus 100–200 surrounding characters, then use token shingles or SimHash/MinHash to mark very high-similarity excerpts as `LIKELY_COPIED`.
- Treat all manufacturer-origin text and distributor copies of that text as one evidence root.
- Count agreement across distinct roots, not URLs.
- Display “likely same origin” rather than claiming proven dependence.

This can matter in a demo if one intentionally duplicated distributor case shows three URLs collapsing to one origin. It should not drive a calibrated probability. Near-duplicate text is evidence of common wording, not proof of data lineage; independent sites can quote the same official specification, and different wording can still copy the same error.

Likelihood of a judge noticing naive URL counting is medium; impact is high because it attacks the trust thesis. The smallest fix if P1 is not reached is simpler: never increase support merely because multiple distributor URLs agree. Count one manufacturer evidence root and label all secondary sources as non-independent unless demonstrated otherwise.

# Conflict Resolution Review

The proposed five categories are a good start but mix entity errors, context errors, representation differences, and temporal differences. Missing categories are:

- `ENTITY_SCOPE`: base product vs accessory, kit vs component, pack vs each.
- `QUALIFIER`: nominal/typical/min/max, input/output, phase, tolerance, duty, or test condition omitted.
- `REGION_STANDARD`: valid differences by market, certification, frequency, or standard.
- `EXTRACTION`: OCR/table alignment/model parsing error rather than source disagreement.
- `SCHEMA_MAPPING`: correct source value bound to the wrong ETIM feature.
- `APPLICABILITY`: a field does not apply to one variant rather than being missing.

Resolution order should be deterministic where possible:

1. Normalize units and formats.
2. Verify quote/page and re-extract failed spans.
3. Compare exact identity and pack/entity scope.
4. Bind all qualifiers and ETIM feature conditions.
5. Check document version/region without automatically assuming newer is applicable.
6. Only then label a genuine factual conflict.

LLM escalation is reasonable for classifying unresolved qualifier or entity language. It should not be allowed to silently resolve a factual conflict. Genuine contradictions should remain conflicted or go to human review unless a clear authority/version rule applies.

Do not report conflict-classification accuracy if the locked test contains only a few examples per category. In that case, show a case matrix with pass/fail and raw counts.

# Confidence & Calibration Review

Valid or useful factors:

- **SKU specificity:** strong and directly relevant.
- **Evidence modality:** useful when clearly defined; a table is not automatically correct, but it is less ambiguous to parse.
- **Verified source span:** essential and missing from the proposed factor list.
- **Independent evidence-root agreement:** useful only after conservative clustering.
- **Identity status and condition completeness:** essential.

Questionable factors:

- **Authority prior:** useful as a prior, unsafe as a decision rule; a manufacturer family page can be less specific than an exact distributor table.
- **ETIM validation:** proves syntactic/domain validity, not factual correctness.
- **Recency:** newer is not always applicable to an older or superseded SKU.
- **Physical consistency:** unsafe unless the rule's preconditions are fully represented and domain-reviewed.
- **Model agreement:** correlated models or repeated prompts are not independent evidence.

Fifty SKUs are enough for a hackathon proof-of-concept benchmark, not enough for defensible per-class probability calibration across 8–10 classes. Hundreds of attribute rows do not solve the dependence problem. A fitted model would be very sensitive to the product-family split and could leak document style from train to test.

P0 should expose a coarse, rule-based `support_grade`:

- `A — exact SKU, verified manufacturer span, complete conditions`
- `B — exact SKU, verified single secondary span or family evidence proven applicable`
- `C — partially supported; review required`
- no grade for conflicted, family-variable, or unverified values

Show the factor explanation, not a decimal. If later calibration is attempted, use grouped splits by family/manufacturer, fit only a very small model, publish bin counts and uncertainty intervals, and display rounded bands rather than three decimal places. Calibration is P2.

# Abstention Review

Abstention must occur at two levels:

- **Identity abstention:** do not claim an exact product when identity is family-level, unknown, or contradictory.
- **Attribute abstention:** do not accept a value without applicable, verified evidence.

One generic `INSUFFICIENT_EVIDENCE` state is too coarse. Users need to know whether a value is not found, not applicable, variant-dependent, contradicted, or supported only by an unverified source.

Thresholds should be chosen on the development set to satisfy a stated risk target, for example “at least 98% precision on committed values,” not to maximize a blended accuracy score. The held-out set then reports whether that target was met. With a small set, include raw counts and confidence intervals.

Tests should contain both answerable and deliberately unanswerable cases:

- nonexistent MPN;
- family stem;
- exact SKU with no authoritative document;
- conflicting exact-SKU sources;
- correct value under the wrong condition;
- missing field;
- inapplicable ETIM feature;
- malicious or irrelevant document.

Primary metrics are committed-value precision, unsupported-claim rate, and coverage. Compare the system at multiple abstention thresholds or support rules. Abstention improves correctness only if precision rises meaningfully without collapsing coverage. Report false commits and unnecessary abstentions separately.

# Evaluation Methodology Review

Fifty SKUs are sufficient for a credible hackathon case study if scope is narrow. They are not sufficient to claim general industrial performance, robust calibration, or 8–10 class generalization.

Recommended design:

- Use 3–4 ETIM classes in one coherent electrical vertical, not 8–10 shallow classes.
- Include at least three manufacturers and several product families per class.
- Pre-register the exact manifest before final prompt tuning: product input, expected identity disposition, source-artifact hash, labeled attributes, and trap type.
- Split by product family, never random attribute rows. Use roughly 30 development SKUs and 20 locked test SKUs. If possible, hold out at least one family per manufacturer.
- Have one person label and a second person verify every test label against manufacturer evidence. Record disagreements and adjudication.
- Do not let a model-proposed label become ground truth until a human verifies the exact page and conditions.
- Report raw numerator/denominator and Wilson or clustered bootstrap intervals; aggregate uncertainty by SKU.

What counts as ground truth:

- Exact manufacturer datasheet/product artifact for the exact commercial reference and applicable version/region.
- For family cases, an explicit family/variant table or multiple exact child records proving which attributes vary.
- Human-reviewed condition binding and normalized value.
- A recorded `UNKNOWN` when authoritative truth is genuinely unavailable; do not manufacture a label from distributor consensus.

Headline quality metrics:

1. Identity disposition accuracy and false-exact rate.
2. Attribute precision on committed values.
3. Unsupported-claim rate.
4. Attribute coverage/recall against applicable buyer-critical fields.
5. Citation validity: accepted claims whose quote/page/hash verifies.
6. Unit and condition normalization accuracy.
7. Selective risk versus coverage for abstention rules.

Operational metrics:

- end-to-end success rate;
- warm and cold p50/p95 latency;
- actual model/search cost per successful SKU;
- cache hit rate;
- retries and failure categories.

Metrics to remove or demote:

- “Catalog completeness improvement” unless it counts only correct, applicable, verified fields.
- A single confidence/calibration score.
- Conflict-class accuracy with tiny category counts.
- Evidence coverage unless precisely defined as verified claim-level support.
- A comparison to IndustryBench-MIPU as if it were the same task. That benchmark is multi-image, Chinese industrial product extraction and validates that completeness is hard, but its 49.9% result is not a direct baseline for PDF/web/ETIM extraction. Cite it as motivation only. [IndustryBench-MIPU paper](https://arxiv.org/abs/2606.14383)

Anti-cherry-picking controls are the public locked manifest, grouped split, inclusion of failures in the video/report, fixed metric code, and one final evaluation run whose artifacts are committed.

# Record/Replay Review

Verdict: good engineering and P0 in a small form; misleading if presentation is ambiguous.

Required semantics:

- `LIVE`: all external interactions are fresh and saved; show provider/model, start time, latency, and actual charge estimate.
- `REPLAY`: no external network; show a persistent banner such as `RECORDED REPLAY — captured 2026-08-12`; never animate it as though work is currently occurring.
- `MIXED`: some cassettes and some live calls; disable this in published evaluation and judge-facing demo, or label every stage individually.
- Avoid `auto` as a user-facing mode. It is convenient in development but makes results difficult to interpret.

Each cassette key should include normalized request, model ID, provider surface, system/prompt version, schema version, tool configuration, and relevant artifact hashes. Store the raw response, usage metadata, capture timestamp, and redaction status. Fail closed in replay when a cassette is absent.

Do not commit API keys, signed URLs, personal data, hidden prompts that contain secrets, or third-party artifacts without redistribution rights. Redaction must happen before commit. A cassette proves what a service returned at capture time; it does not prove the current model would return it.

Evaluation documentation must state: “Results were computed from frozen interactions captured on DATE using MODEL/PROVIDER and replayed deterministically.” The public app should offer replay by default and a separately gated live run. This is transparent resilience, not fake data.

# Scalability Review

A convincing scale story has four layers:

1. **Work durability:** persisted job/SKU/stage state, idempotency keys, retry limits, resumability, and no duplicate paid calls.
2. **Resource control:** bounded concurrency per provider/domain, backoff on 429/5xx, file/token/page caps, and per-run budgets.
3. **Cache economics:** document hashes, extraction keys that include schema/prompt/model versions, and measured family-document reuse.
4. **Measured operations:** success rate, throughput, p50/p95, cost, cache hit, retry count, and failure distribution.

Cloud Run services are suitable for the API, but not proof of durable background processing. Cloud Run Jobs can run parallel tasks to completion with retries; Cloud Tasks can enqueue asynchronous work to a private service. Either is credible P1 infrastructure. [Cloud Run jobs](https://cloud.google.com/run/docs/create-jobs), [Cloud Tasks](https://docs.cloud.google.com/run/docs/triggering/using-tasks)

For P0, do not build a distributed queue. Run a measured 25–50 SKU batch through the same idempotent stage functions, persist results, and document the concurrency limit. For P1, move the batch runner into a Cloud Run Job or task queue without changing business logic.

Gemini Batch's discount is real in documented pricing, but it is not automatically an end-to-end catalog engine. Search discovery, URL retrieval, and interactive identity decisions may remain outside batch, and tool compatibility must be tested. [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing)

A 100k projection is acceptable only as a scenario table with explicit assumptions: discovery calls/SKU, unique documents/SKU, average pages/tokens, cache hit rate, retry rate, concurrency/quota, and batch turnaround. Do not present the projection as tested capacity.

# Gemini / Model Routing Review

Routing cheap models for routine work and stronger models for ambiguous work is sensible in principle, but premature in P0. Every route adds prompts, failure modes, evaluation branches, and provider/model lifecycle risk.

Start with one tested extraction model on the exact Vertex/SDK surface. Choose it from a small bake-off on the development set, not from price alone. Dense tables and condition binding may require a stronger model than simple text extraction. Pin the model and SDK; record both.

Use deterministic code for:

- brand/MPN normalization and exact matching;
- ETIM lexical candidate generation;
- unit conversion and range parsing;
- enum/boolean/type validation;
- quote/page verification;
- document hashing and duplicate detection;
- unit/format conflict resolution;
- cache keys, budgets, and routing thresholds.

Use a model only for:

- choosing among plausible ETIM classes when lexical evidence is insufficient;
- extracting table/prose facts into the typed schema;
- interpreting ambiguous family/condition language;
- classifying unresolved conflicts.

Do not use a stronger model to “adjudicate” a true factual conflict into truth. Keep it conflicted or route it to a person. Cut commerce-copy generation from P0; it duplicates Unilog's existing Product Description Agent and consumes demo time without proving trusted facts. [Unilog HyperScale roadmap](https://www.unilogcorp.com/hyperscale/)

Google's current documentation supports URL Context, Search grounding, PDF inputs, and the cited model families, but capabilities and launch stages vary by API surface. A day-one compatibility test on the target Vertex project is mandatory. URL Context supports up to 20 URLs and 34 MB per URL, but those provider limits are not safe application limits. [Google URL Context limits](https://ai.google.dev/gemini-api/docs/url-context), [Google Cloud free-trial exclusions](https://docs.cloud.google.com/free/docs/free-cloud-features)

# Security Review

For a hackathon, implement the controls that block realistic catastrophic failures and avoid decorative enterprise security.

**Secrets and spend**

- Keep provider credentials server-side in Secret Manager or deployment secrets; use a least-privilege service account.
- Public demo runs replay only. Gate live mode with an admin secret and hard per-run/day budgets.
- Log usage and stop when budgets are exceeded. Never expose raw provider errors or tokens to the browser.

**URLs and SSRF**

- Prefer a curated domain/artifact allowlist in P0.
- If arbitrary fetching is enabled: HTTPS only; reject credentials and nonstandard schemes; resolve all IPv4/IPv6 addresses; reject loopback, private, link-local, multicast, reserved, and cloud metadata ranges; revalidate every redirect; cap redirects; and prevent DNS rebinding.
- Do not trust a `HEAD` response or `Content-Type` alone. Stream with byte/time limits and verify magic bytes.
- OWASP specifically recommends allowlisting when possible, validating all A/AAAA results, and controlling redirects. [OWASP SSRF guidance](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)

**PDFs and oversized content**

- Accept only PDF for the demo ingestion path; cap compressed bytes below provider limits, page count, rendered pixels, parse time, and extracted text.
- Generate filenames internally and store untrusted files outside the web root/private bucket.
- Parse/render in an isolated subprocess/container with no credentials and no outbound network.
- Reject encrypted, malformed, recursively embedded, or excessively expanding files. A full antivirus/CDR stack is optional; size/type/isolation/timeouts are P0.
- OWASP recommends allowlisted extensions, magic/type validation, generated filenames, authorization, safe storage, and size limits. [OWASP file-upload guidance](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html)

**Indirect prompt injection**

- Treat all PDF/web text as untrusted data, never as instructions.
- The extraction model gets no privileged tools, secrets, or ability to choose new URLs.
- Use a fixed schema and reject extra fields/tool requests.
- Do not rely on regex prompt-injection detection. Verify output claims against source spans.
- OWASP notes that prompt injection can be embedded in retrieved documents and that filters/guardrail models are not complete defenses. [OWASP prompt-injection guidance](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)

**Fake citations and HTML injection**

- Verify quote, page, identity scope, and artifact hash before an evidence object can support a value.
- Render source text as escaped text, never `dangerouslySetInnerHTML`; sanitize any unavoidable HTML and restrict link schemes to HTTPS.
- Serve cached documents as attachments or controlled rendered images, not active inline HTML/SVG.
- Use standard framework escaping plus a restrictive CSP. [OWASP XSS guidance](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html)

**Unsafe cache behavior**

- Partition live/replay and user-provided artifacts.
- Include document, prompt, schema, and model hashes in cache keys.
- Never cache authorization headers or signed URLs in committed cassettes.
- Set retention limits and do not make the object bucket public.

Do not spend the 14 days on RBAC, a WAF, VPC Service Controls, full malware scanning, or enterprise compliance claims. The public live-cost endpoint, SSRF, fake citations, and unsafe document rendering are the material risks.

# 14-Day Scope Review

The original plan is still a 4–6 week product compressed into 14 days. Claude Code may increase code throughput, but it does not eliminate product decisions, source licensing, ground-truth review, visual QA, deployment debugging, or video production.

The correct delivery shape is one excellent vertical slice completed early enough to test:

- Days 1–2: confirm rules/IP; freeze contract; five-SKU source/labeling pilot; Vertex capability spike; select 3–4 ETIM classes.
- Days 3–7: identity, curated ingestion, extraction, span verification, normalization, abstention, Golden Record/Evidence Drawer.
- Days 8–10: expand locked dataset, run evaluation, fix systematic failures, add strict replay.
- Days 11–12: deploy, security limits, measured small batch, README and architecture evidence.
- Days 13–14: video, full rehearsal, submission buffer. No new features.

If P0 is not end-to-end by day 7, cut batch, live mode, review queue, source clustering, and all dashboards except a static evaluation report.

# Demo Review

The concept can be memorable within 30 seconds if the identity decision is visual and concrete.

Recommended sequence:

1. Enter `Schneider Electric / LC1D18 / Contactor`.
2. Immediately show `Family or incomplete reference` and highlight the missing discriminator: coil voltage/type.
3. Show which fields are proven family-level and which are blocked as variant-dependent.
4. Select `230 V AC`; resolve to `LC1D18P7`.
5. The Golden Record updates.
6. Click `Rated operational current — 18 A`; open the actual Schneider PDF page with `18 A ... AC-3` highlighted and separately show `32 A ... AC-1` as a condition distinction.
7. End on a compact locked-test summary: false-exact count, committed-value precision, unsupported claims, coverage, and cost/SKU.

What makes it look fake:

- Instant “live” results that are actually replayed.
- A family detector that works only for `LC1D18`.
- Perfect decimal confidence with 50 products.
- Quotes that cannot be found on the displayed page.
- A conflict manufactured by comparing AC-1 with AC-3.
- A batch of repeated cached hero records presented as scale.
- Claims that no competitor or Unilog capability overlaps.

What can fail:

- Search returns a distributor or wrong region before the manufacturer.
- Schneider blocks/fails a document fetch.
- A model cites the wrong page or merges table rows.
- `LC1D18` is treated as a channel-level configurable reference by a judge.
- ETIM class/feature mapping omits qualifiers.
- Replay disclosure is missed and judges assume deception.
- Live latency consumes most of the video.

Highest wow-to-effort ratio: **clickable, verified PDF-page highlighting combined with a before/after identity status and variant matrix.**

Remove even if technically impressive: **the physical-consistency badge**. It invites a domain expert to challenge incomplete equations and distracts from stronger, provable validation.

# P0 — Must Build

1. Confirm and archive official deadline, submission artifacts, eligibility, and IP terms.
2. Freeze a small data contract covering identity, applicability, typed values, conditions, evidence verification, conflicts, abstention reasons, and live/replay mode.
3. Select one electrical vertical with 3–4 ETIM classes and a 30-dev/20-test product-family-grouped manifest; start with a five-SKU labeling-time pilot.
4. Implement exact/family-or-incomplete/unknown/contradictory identity gating, including the LC1D18 variant axis and non-Schneider traps.
5. Load and attribute the required ETIM 10 subset; validate types, units, ranges, enums, and referential integrity.
6. Use a curated, attributed document corpus as the reliable path; use Google Search only as an optional discovery input.
7. Ingest documents page-by-page with hashes, caps, and safe parsing.
8. Extract into the frozen schema and verify every accepted quote/page against the artifact.
9. Deterministically normalize units and resolve representation differences.
10. Implement explicit statuses for verified, single-root, variant-dependent, conflicted, not found, not applicable, and unsupported.
11. Apply a conservative abstention policy chosen on the development set.
12. Build one polished Golden Product Record and Evidence Drawer with page highlighting and condition display.
13. Implement strict replay fixtures for the hero flow and locked evaluation; show a persistent replay badge and capture date.
14. Report identity accuracy/false-exact rate, committed-value precision, unsupported-claim rate, verified evidence rate, coverage, normalization accuracy, raw counts, and operational cost/latency.
15. Deploy a public replay-only demo; gate live calls and spending.

# P1 — Strong Differentiators

1. Conservative source-root clustering using document hashes and high-threshold excerpt similarity, demonstrated on one copied-source trap.
2. Full conflict-cause pipeline after deterministic unit, quote, identity, qualifier, and version checks.
3. A small measured CSV batch with persisted/idempotent stage results, cache-hit rate, retries, p50/p95, and cost.
4. A review queue for only conflicted/unsupported decisions; capture human corrections as future labels without adding them to the locked test.
5. Verified before/after buyer-critical ETIM coverage, counting only correct applicable fields.
6. A separate, conspicuously live single-SKU run in the video if reliability is proven.
7. Model routing only after the development evaluation shows a cost/quality benefit.
8. A family-variant matrix that proves invariants across multiple children and makes the identity differentiator legible.

# P2 — Only If Ahead

1. Statistical confidence calibration with grouped cross-validation, adequate sample sizes, uncertainty intervals, and a locked test.
2. Cloud Run Jobs or Cloud Tasks for durable larger batches.
3. Broader manufacturer/source lineage beyond near-duplicate heuristics.
4. Domain-expert-approved cross-attribute constraints whose preconditions are fully modeled.
5. Golden-record version diff and regression view.
6. Nameplate/image extraction.
7. Distributor API connector.
8. Prompt/model bake-off dashboard.
9. BMEcat or ETIM xChange export.
10. Expansion beyond the initial 3–4 ETIM classes.

# CUT

- The contactor power/current “physical consistency” formula and generic physics badge.
- Decimal confidence, reliability diagram, ECE, and AURC claims from the 50-SKU set.
- Full ETIM coverage as a demonstrated capability.
- Generic vector database/RAG, knowledge graph, multi-agent framework, microservices, message broker, and fine-tuning.
- Commerce-copy generation as a headline or P0 stage.
- Live SSE token/cost theater.
- A broad dashboard, marketing site, animations, mobile optimization, auth/RBAC, billing, and chatbot.
- The claim that Google-grounded citations are page-level evidence.
- The claim that source similarity proves independence/dependence.
- The claim that all ETIM features are required gaps.
- The claim that the system “never lets the model invent”; use the verifiable-span claim instead.
- Any “millions of SKUs” or 100k capacity claim not backed by a clearly labeled scenario model.
- Shipping full third-party PDFs or raw cassettes without rights and secret review.

# Top 10 Failure Modes

| # | Failure | Likelihood / judging impact | Smallest strong fix |
|---:|---|---|---|
| 1 | Wrong exact identity enriches the wrong variant | Medium / Critical | Hard identity gate; report false-exact rate; prove variant choice |
| 2 | Model fabricates or mislocates a citation | High / Critical | Page-map ingestion and normalized quote verification; reject unverifiable evidence |
| 3 | Scope overruns and no polished end-to-end flow exists | High / Critical | Enforce reduced P0 and day-7 cut gate |
| 4 | Judge says Unilog already does enrichment/gap fill | High / High | Position as audit/triage automation; show expert-review reduction |
| 5 | Replay is mistaken for a live result | Medium / High | Persistent `RECORDED REPLAY` badge, capture date, strict separate modes |
| 6 | ETIM coverage is presented as mandatory completeness | Medium / High | Buyer-critical subset plus not-applicable status and careful wording |
| 7 | Decimal confidence/calibration collapses under scrutiny | High / High | Coarse support grades and raw factors; defer calibration |
| 8 | AC-1/AC-3 or another qualifier difference becomes a fake conflict | Medium / High | First-class conditions and deterministic resolution order |
| 9 | Public live endpoint is abused for SSRF or cloud spend | Medium / High | Public replay only; allowlisted fetching; gated budgets and safe URL validation |
| 10 | “Scale” demo loses/duplicates work or extrapolates from cache | Medium / Medium-High | Persisted idempotency, measured small batch, explicit scenario assumptions |

# Recommended Changes Before Implementation

1. Replace the current positioning with: **“SKUTruth is an auditable product-fact verification and triage layer for long-tail catalog enrichment, designed to feed existing PIM workflows.”**
2. Accept the reduced P0 in this review and delete the original P0 checklist from the implementation brief.
3. Make identity P0 and rename its ambiguous outcome `FAMILY_OR_INCOMPLETE_REFERENCE`.
4. Freeze the revised contract before UI/backend work; add conditions, applicability, evidence verification, and run mode.
5. Recheck ETIM record counts excluding headers, add ODC-BY attribution, and stop calling all features required.
6. Choose 3–4 classes in one electrical vertical and pre-register a family-grouped 30/20 evaluation manifest.
7. Run four spikes before full build: one exact PDF/table extraction, one page/quote verification, one Vertex Search+URL Context compatibility/cost check, and one five-SKU labeling-time study.
8. Use search for discovery only. Make ingested, hashed, page-mapped artifacts the evidence authority.
9. Replace numerical confidence with explainable support grades. Log factors from day one; calibration is P2.
10. Remove cross-attribute physics from the plan unless a domain expert supplies exact rules and preconditions.
11. Make replay strict, conspicuous, and immutable; keep mixed/auto mode out of published evaluation.
12. Measure unsupported claims, false exacts, verified citations, coverage, expert review effort, cost, and latency. Do not optimize for fill rate alone.
13. Gate the public live path and implement the minimal URL, PDF, prompt-injection, output-escaping, and budget controls listed above.
14. Script the 30-second demo around identity resolution and verified evidence highlighting, not pipeline telemetry.

# Final Go / No-Go Recommendation

**GO, with conditions.**

If the team implements the original scope, the recommendation is NO-GO because too many partially credible features will dilute the one differentiator judges can understand. If the team implements the reduced vertical slice, the architecture and product strategy are strong enough to be competitive and potentially difficult to beat.

The submission wins on trust only if trust is demonstrated mechanically:

- identity is resolved or explicitly withheld;
- accepted values have verified source spans;
- conditions are preserved;
- unsupported fields visibly abstain;
- evaluation cases are locked and failures remain visible;
- replay is unmistakably replay;
- scale claims are measured or explicitly modeled.

The final pitch should be: **“We do not automate filling every field. We automate deciding which product facts are safe to accept, show the evidence for each decision, and send only the unresolved remainder to an expert.”** That is aligned with the challenge, relevant to Unilog's actual operating model, technically defensible in 14 days, and more differentiated than another AI catalog generator.
