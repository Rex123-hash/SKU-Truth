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
identity resolution              EXACT / FAMILY / UNKNOWN / CONTRADICTORY
      ↓  exact reference required before anything is enriched
manufacturer artifact ingestion  bytes hashed · pages mapped · text preserved
      ↓
Gemini structured extraction     schema-constrained proposals, through record/replay
      ↓
deterministic validation         units, picklists, ranges, condition completeness
      ↓
mechanical evidence verification EXACT_SPAN, or UNVERIFIED with a specific reason
      ↓
[next] adjudication → 252-column Unilog delivery record
```

The two ends of that diagram exist and work. **They are not yet wired to each other**: the
Unilog adapter reads and writes the organizer's format, the evidence pipeline verifies
facts about a product, and the mapping stage that joins them is the next milestone. Nothing
here does end-to-end enrichment today, and the demo path is currently two halves.

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
| Unilog input/output | streaming CSV reader, placeholder policy, `Part_Manuf → (name, code)`, runtime-derived 252-column delivery schema with fingerprint, exact-order export |
| Identity resolution | `EXACT` / `FAMILY_OR_INCOMPLETE_REFERENCE` / `UNKNOWN` / `CONTRADICTORY`, with exact-SKU evidence required for `EXACT` |
| Artifact ingestion | byte and page hashing, page-preserving text, content-addressed store that validates and never repairs |
| Table extraction | ruled-table structure as an additive fallback; pypdf text stays canonical |
| Gemini structured extraction | Vertex, schema-constrained, gated on exact identity, always through record/replay |
| Record and replay | LIVE / REPLAY, fail-closed replay, versioned cassette keys |
| Deterministic validation | ETIM units, picklists, ranges, condition completeness; exact-decimal unit conversion |
| Mechanical verification | the section above |
| Evaluation framework | manifests, scoring, reporting |

**Next** — verified facts → Unilog attribute mapping and adjudication: deciding which
verified facts reach which delivery slot, and in whose format.

**Not yet implemented** — range and logical value verification; controlled-vocabulary
synonym licensing; manufacturer and brand canonicalisation; classpath classification; UOM
and fraction normalisation; description construction; batch export; any user interface.

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

## Development

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"

python -m pytest                                   # test suite
python -m ruff check backend tests scripts
python scripts/etim_stats.py                       # ETIM statistics and integrity check
python scripts/verify_extraction_run.py --cassette <path>   # re-derive a recorded run
```

Python 3.12 and Pydantic on the backend. The data contracts in
`backend/skutruth/contracts/` are frozen: components adapt to the contract rather than the
other way round, and changing one requires a concrete failure case demonstrating the
contract is wrong. See [`backend/skutruth/contracts/README.md`](backend/skutruth/contracts/README.md)
for the invariants and the reasoning behind them.
