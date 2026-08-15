# SKUTruth

SKUTruth is an auditable product-fact verification and triage layer for long-tail
industrial catalog enrichment, designed to feed existing PIM workflows.

> **No value is accepted unless its supporting span is verified in a versioned source
> artifact.**

That claim is mechanical, not aspirational. An accepted attribute must trace to text
located in a document that was ingested and hashed, and the data contracts refuse to
represent a record where it does not.

## What SKUTruth does

Given a sparse input — a brand, a manufacturer part number, and perhaps a few words of
description — SKUTruth produces a structured, ETIM-typed product record in which every
accepted value carries its evidence, and everything else is explicitly withheld with a
reason a person can act on.

- **Identity before enrichment.** The system first determines what the input actually
  refers to: an exact commercial reference, a family or incomplete reference, unknown,
  or contradictory. A correct record attached to the wrong variant is worse than no
  record, so identity is a hard gate rather than a hint.
- **Condition-aware technical attributes.** Operating qualifiers — utilization
  category, voltage, frequency, temperature, measurement basis — are structured data
  bound to each value. A contactor rated `18 A` and `32 A` is not contradicting itself;
  those are its AC-3 and AC-1 ratings, and the system treats them accordingly.
- **Verified page and span evidence.** Search is used to discover candidate documents.
  Provenance comes from artifacts that were ingested, hashed, and page-mapped, with the
  supporting text located in them.
- **Deterministic normalisation.** Units, ranges, enumerations, and booleans are
  normalised in code against ETIM's own tables. Conversions such as `18000 mA → 18 A`
  are versioned transforms with recorded lineage, not model output.
- **Explicit abstention.** A field can be empty because nothing stated it, because it
  does not apply, because it varies across an unresolved family, because sources
  genuinely conflict, or because a proposed span could not be verified. These are
  distinct outcomes, and the user is told which one applies.
- **Selective human review.** Only unresolved decisions reach a person. Reducing expert
  verification effort is the point; filling every field is not.

## Current status

Implemented and tested:

- **Frozen data contracts** covering identity, applicability, typed values with
  derivation lineage, structured conditions, evidence and span verification, conflicts,
  abstention reasons, coverage, and run provenance. Core invariants are enforced by
  validators rather than convention.
- **ETIM 10.0 loader** over the vendored release, with referential-integrity checks and
  a reproducible statistics script.
- **Deterministic ETIM validation** of extracted values: feature membership, value type,
  units and dimensions, picklist membership, range ordering, and condition completeness.
- **Unit conversion boundary** with a reviewed unit registry, exact decimal arithmetic,
  and explicit refusal of unknown units, cross-dimension conversions, and affine
  temperature scales.
- **Per-class extraction schema generation** that constrains a model to real ETIM
  feature identifiers, closed picklists, and dimensionally compatible units.

Not yet implemented: document ingestion, span verification, the identity resolver,
model-backed extraction, the evaluation harness, and the web interface.

## Architecture and pipeline

Six observable decisions, implemented as a typed pipeline rather than an agent
framework:

```
identify → classify → discover / ingest → extract / verify → normalize / adjudicate → present
```

- **identify** — resolve the supplied brand and part number to an exact reference, or
  report precisely which discriminator is unbound.
- **classify** — select the ETIM class. Candidates are generated lexically from ETIM's
  own synonym set, so a model only ever chooses from a short list and cannot invent a
  class identifier.
- **discover / ingest** — locate candidate documents, then fetch, hash, and page-map the
  ones that will be used as evidence.
- **extract / verify** — extract into a generated, schema-constrained target, then
  locate every proposed span in the ingested artifact. A span that cannot be found
  cannot support an accepted value.
- **normalize / adjudicate** — deterministic unit, range, and enumeration handling,
  followed by conflict classification and a rule-derived support grade.
- **present** — the golden record and an evidence drawer showing, for each value, what
  the system believes and which span in which document supports it.

Deliberately not used: vector databases, retrieval-augmented generation, knowledge
graphs, multi-agent frameworks, message brokers, and model fine-tuning. Datasheets are
small enough for whole-document extraction with a deterministic page map, and each
omission is a recorded engineering decision rather than an oversight.

Language models are used where interpretation is genuinely required — choosing among
plausible ETIM classes, extracting facts into a typed schema, reading ambiguous family
or condition language, and classifying unresolved conflicts. Identifier normalisation,
unit conversion, enumeration validation, span verification, hashing, and cache keys are
all deterministic code.

## ETIM 10.0

SKUTruth is built on the ETIM technical product classification standard, which supplies
stable class and feature identifiers, four explicit feature types, units for numeric and
range features, fixed allowed values for alphanumeric features, and class synonyms.

The ETIM 10.0 release is vendored in `data/etim/` under the Open Data Commons
Attribution Licence v1.0; see `data/etim/ATTRIBUTION.md`. Parsed record counts are
reproduced by `scripts/etim_stats.py`.

ETIM defines what characterises a product class. It does not define what a buyer
requires, and a feature that does not apply to a product is not a gap. Coverage is
therefore reported separately as ETIM feature coverage, buyer-critical coverage,
accepted values, and inapplicable features — with only applicable, buyer-critical,
accepted values feeding the buyer-facing figure. The buyer-critical subset and the
qualifier rules for each demonstration class are hand-reviewed and version-controlled in
`data/demo_classes/`.

## Development

```bash
uv venv --python 3.12
uv pip install -e ".[dev]"

python -m pytest              # test suite
python -m ruff check backend tests scripts
python scripts/etim_stats.py  # ETIM statistics and integrity check
```

Python 3.12, FastAPI, and Pydantic on the backend. The data contracts in
`backend/skutruth/contracts/` are frozen: components adapt to the contract rather than
the other way round, and changing one requires a concrete failure case demonstrating the
contract is wrong. See `backend/skutruth/contracts/README.md` for the invariants and the
reasoning behind them.
