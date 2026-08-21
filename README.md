# SKUTruth

SKUTruth turns messy industrial catalogue rows into Unilog-ready product content, while
requiring important enriched facts to be backed by manufacturer evidence.

> **AI proposes. SKUTruth verifies. Unilog's rules decide the final format.**

That middle step is mechanical, not aspirational. A fact reaches "verified" only when the
system has located it in a hashed, page-mapped manufacturer document, checked that the
document's own wording states that value under those operating conditions, and confirmed
the evidence belongs to the exact product in question. Everything else is withheld with a
reason a person can act on.

## The problem

A distributor row looks like this: a part number, forty characters of abbreviated
description, and three brand columns that are mostly placeholders. The delivery format
asks for 252 columns, including fifty ordered attribute slots, five distinct description
forms, and units in Unilog's own vocabulary. The gap between the two is filled today by
expert time.

Filling that gap with a language model is easy and produces confident, unfalsifiable
output. The hard part — and the part that decides whether the result can be trusted into a
PIM — is knowing which of those proposals are actually supported.

## Pipeline

```
raw Unilog row
      ↓  placeholder policy · Part_Manuf structural parse
site-restricted search           human-reviewed domains only · locators, never evidence
      ↓  exact caller query · no model in the loop
manufacturer source discovery    approved domains only · exact reference required
      ↓  bounded, SSRF-checked acquisition
manufacturer artifact ingestion  bytes hashed · pages mapped · text preserved
      ↓
identity resolution              EXACT / FAMILY / UNKNOWN / CONTRADICTORY
      ↓  exact reference required before anything is enriched
Gemini structured extraction     schema-constrained proposals, through record/replay
      ↓
deterministic validation         units, picklists, ranges, condition completeness
      ↓
mechanical evidence verification EXACT_SPAN, or UNVERIFIED with a specific reason
      ↓
adjudication + explicit mapping  commit / withhold / review / unmapped
      ↓
252-column Unilog delivery record
```

That path now runs end to end for attributes: a verified fact reaches an
`ATTRIBUTE_LABEL` / `ATTRIBUTE_VALUE` / `ATTRIBUTE_UOM` triplet in the organizer's real
252-column schema, and a refused one reaches no cell.

**What that does not mean.** The mapping rules that decide where a fact goes are
hand-written and marked non-authoritative, because the official Unilog LOV, UOM master,
and category attribute rules are not in the supplied pack. The other field groups —
manufacturer and brand normalisation, classpath, the five description forms, digital
assets — are not built. So SKUTruth can write verified attributes into the official
delivery schema through explicit mappings; it cannot yet claim those attributes are
Unilog-compliant, and the code refuses to pretend otherwise.

Discovery is likewise a foundation, not a solved problem. Agent Search basic website
search is the selected deterministic manufacturer-site search mechanism, and manufacturer
domains must be human reviewed before they can license evidence — the reviewed set *is*
the search corpus, so a domain becomes searchable only after a person has checked it.

**No product has been acquired from the open web, and no live search has run**, because
no domain has been reviewed yet and the corpus is therefore empty. That is the honest
state and the next step is a human one, not an engineering one.

Two earlier providers were implemented and removed, both for reasons outside our control.
The Custom Search JSON API is closed to new customers. Google Search grounding is not
used because its terms do not permit SKUTruth's automated link-collection and fetch flow.
Both are recorded in
[`backend/skutruth/discovery/README.md`](backend/skutruth/discovery/README.md). Several of
the organizer input's largest `Part_Manuf` values are also buying groups rather than
manufacturers, so no manufacturer site exists to find for them at all.

## What the verification actually checks

Given a proposed fact, the verifier requires all of the following from **one coherent unit**
of a real artifact — one source line, or one table row with the headers above it:

- the artifact hashes to the digest the claim names, and its stored pages are intact;
- the model's quote occurs on the cited page, unambiguously;
- the *artifact's own text* — not the model's paraphrase — states the value, in a
  compatible unit, **with a matching relation** (`< 60 °C` is not `60 °C`);
- every bound operating condition is supported by that same unit;
- the evidence is bound to the exact product, by the document's scope or by a table row
  that identifies itself.

Failures are specific: `OPERATOR_MISMATCH`, `CONDITION_NOT_SUPPORTED`,
`PRODUCT_SCOPE_NOT_SUPPORTED`, `AMBIGUOUS_MATCH`, and ten more. Never a bare "unverified",
and never a confidence score — the answer is not probabilistic. See
[`backend/skutruth/verification/README.md`](backend/skutruth/verification/README.md).

On the one real product measured so far, 14 model proposals produce 9 verified and 5
refused. The refusals are the interesting half: two ratings where the model turned a source
bound into a point value, one controlled-vocabulary mapping that text cannot license, and
two range-valued features the verifier does not yet handle. Re-derive it yourself with
`scripts/verify_extraction_run.py`; the procedure is versioned even though the copyrighted
datasheet it reads cannot be committed.

## Status

**Implemented and tested**

| | |
|---|---|
| Frozen data contracts | identity, applicability, typed values with lineage, conditions, evidence, conflicts, abstention, coverage, run provenance |
| Unilog input/output | streaming CSV reader, placeholder policy, authority-aware manufacturer/brand normalization, conservative internal lexical families, record-scoped organizer example classification, runtime-derived 252-column delivery schema with fingerprint, exact-order export |
| Identity resolution | `EXACT` / `FAMILY_OR_INCOMPLETE_REFERENCE` / `UNKNOWN` / `CONTRADICTORY`, with exact-SKU evidence required for `EXACT` |
| Source discovery foundation | deterministic queries, reviewed manufacturer-domain authority, exact-reference policy, inspectable ranking, SSRF-bounded PDF acquisition into the artifact store |
| Live search provider | Agent Search basic website search — caller's query executed verbatim, real publisher URLs, one `siteSearch` filter per reviewed domain (basic search has no `OR`), no model in the loop, bounded calls, typed failures, record/replay. Exercised offline; **no live run yet** |
| Human domain review workflow | review packets from organizer input, and an explicit `confirm` command that cannot default a reviewer from git config, the OS username, or the environment |
| Artifact ingestion | byte and page hashing, page-preserving text, content-addressed store that validates and never repairs |
| Table extraction | ruled-table structure as an additive fallback; pypdf text stays canonical |
| Gemini structured extraction | Vertex, schema-constrained, gated on exact identity, always through record/replay; PDF/ETIM proposals plus a narrow stored-HTML local lighting proposal path |
| Record and replay | LIVE / REPLAY, fail-closed replay, versioned cassette keys |
| Deterministic validation | ETIM units, picklists, ranges, condition completeness; exact-decimal unit conversion |
| Mechanical verification | frozen PDF text/table verifier plus an additive exact-rule HTML attribute adapter; verified HTML facts still have no Unilog lighting mapping authority |
| Adjudication and mapping | typed commit / withhold / review / unmapped decisions, explicit injected mapping rules with recorded authority, condition-preserving policies, conflict handling, attribute-slot assembly with provenance retained |
| Evaluation framework | manifests, scoring, reporting |

So: verification, adjudication, explicit non-authoritative mapping, and Unilog attribute-slot
assembly are implemented and run end to end.

**Not yet implemented** — official manufacturer/brand LOV mappings; organizer-wide
classpath LOV mapping; the five description forms; a batch product workflow; any user
interface. Also outstanding inside the parts that do exist: range and logical value
verification, controlled-vocabulary synonym licensing, UOM and fraction normalisation, and
HTML identity/attribute extraction beyond the safe snapshot foundation.

Two of those are worth separating from the rest. Every mapping rule in the repository is
hand-written, so **no output is claimed to conform to Unilog's published rules**. And no
row in the organizer's 1,000-row input has yet been enriched end to end: the provider,
policy, fetcher, and acquisition seam all exist, but nothing has been stored from the open
web, so **the open-web half is a wired seam rather than a working retrieval system**.

Against the organizer input, 291 of the 959 rows with a usable part number and
manufacturer hint are searchable through configured domains, and the 56 Kichler rows may
license manufacturer evidence because that entry carries a human review. That number
moves when a person reviews domains, not when more code is written.

Several of those wait on organizer reference files that are not in the supplied pack — a
brand master, the LOV, the UOM standard, the decimal/fraction table, the content
guidelines, and a labelled ground-truth set. Their contents are not guessed at, and their
absence is recorded in [`research/unilog_data_pack_audit.md`](research/unilog_data_pack_audit.md)
rather than worked around. **With two labelled example rows in hand, no field-level
accuracy figure is honestly computable, and none is claimed.**

## Where ETIM fits

Unilog's format and vocabulary are the competition-facing output wherever the organizer
supplies them. ETIM is internal machinery: a working example of a class → ordered attribute
template, a reviewed unit registry and validation layer, and the right output for the
electrical vertical. The verification engine is deliberately vocabulary-agnostic — a claim
keyed `unilog:Amperage Rating` verifies through exactly the same code as one keyed
`EF001392`, and a test enforces that the engine imports no ETIM class machinery.

The ETIM 10.0 release is vendored in `data/etim/` under ODC-BY 1.0; see
`data/etim/ATTRIBUTION.md`. Counts are reproduced by `scripts/etim_stats.py`.

## Deliberately not used

Vector databases, retrieval-augmented generation, knowledge graphs, multi-agent frameworks,
message brokers, and fine-tuning. Datasheets are small enough for whole-document extraction
with a deterministic page map, and each omission is a recorded engineering decision rather
than an oversight. Language models are used where interpretation is genuinely required —
proposing facts into a typed schema, reading ambiguous family or condition language.
Identifier normalisation, unit conversion, enumeration validation, span verification,
hashing, and cache keys are deterministic code.

Third-party material stays out of the repository: manufacturer PDFs, runtime cassettes, and
the organizer data pack are all gitignored, and tests never depend on them.

## Running the demo API

```bash
python -m uvicorn skutruth.api.asgi:app --app-dir backend --port 8000
```

That is the whole setup. The default mode, `DEMO_REPLAY`, makes **zero external network
calls** and needs no cloud credentials, no environment variables, and no organizer data
pack — so the demo still works when Google, Vertex, or a manufacturer site does not.
`GET /api/health`, `GET /api/demo/products`, `GET /api/demo/products/{mpn}`,
`POST /api/analyze`, `GET /api/schema`; interactive docs at `/docs`.

The three demo cases are real runs, not mock-ups: Kichler `45297BK` reaching seven
verified manufacturer facts, SATCO `62-1875` blocked at acquisition by an HTTP 429, and
Feit `SHOP/4X2/840/V1` refusing to treat a hyphenated locator as the slashed organizer
reference. Every stage says whether it was re-derived now or observed once in a live run.
See [`backend/skutruth/api/README.md`](backend/skutruth/api/README.md).

## Development

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"

python -m pytest                                   # test suite
python -m ruff check backend tests scripts
python scripts/etim_stats.py                       # ETIM statistics and integrity check
python scripts/verify_extraction_run.py --cassette <path>       # re-derive a recorded run
python scripts/assemble_delivery_record.py --cassette <path>    # and map it into a record
python scripts/discover_sources.py --input <organizer csv>      # plan source discovery
python scripts/discover_sources.py --input <csv> --live         # run the live provider
python scripts/review_manufacturer_domains.py packet --input <csv>   # prepare a domain review
python scripts/analyze_normalization.py --input <csv>                # normalization report
python scripts/analyze_classification.py --input <csv> --delivery-format <csv>
python scripts/setup_agent_search.py                            # what to provision, from reviews
python scripts/build_demo_cases.py                              # regenerate the demo record
python scripts/build_demo_cases.py --check                      # and check it against the evidence
```

Live search runs on the project's existing GCP setup: `SKUTRUTH_GCP_PROJECT`,
`SKUTRUTH_AGENT_SEARCH_ENGINE_ID`, and Application Default Credentials
(`gcloud auth application-default login`). Without them the pilot refuses rather than
degrading to a plan and calling it a live run. No committed test reaches the network.

Python 3.12 and Pydantic on the backend. The data contracts in
`backend/skutruth/contracts/` are frozen: components adapt to the contract rather than the
other way round, and changing one requires a concrete failure case demonstrating the
contract is wrong. See [`backend/skutruth/contracts/README.md`](backend/skutruth/contracts/README.md)
for the invariants and the reasoning behind them.
