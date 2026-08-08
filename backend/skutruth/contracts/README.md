# Frozen data contracts

These types are the interface between every pipeline stage, the API, the frontend, and the
evaluation harness. **Components adapt to the contract. The contract does not adapt to
components.**

Revised at Checkpoint 1 in response to `CODEX_REVIEW.md`. The change log at the bottom
records what moved and why.

## The core claim these types exist to support

> **No value is accepted unless its supporting span is verified in a versioned source
> artifact.**

Not "the model never invents a value" — a model can fabricate a quote or a page number.
What we can defend mechanically is narrower and stronger: we located the span ourselves, in
an artifact we ingested and hashed, and we can re-open it at that page.

## Change policy

| Change | Allowed? |
|---|---|
| Adding an optional field | Yes |
| Adding an enum member | Yes |
| Adding a key to `SupportFactors.factors` | Yes — the bag is open on purpose |
| Adding a validator that tightens an existing invariant | Yes, with a test |
| Renaming or removing a field | Only with a decision recorded in `docs/decisions/` |
| Loosening an invariant because a stage found it inconvenient | **No.** Fix the stage. |

## Invariants, and why each exists

Enforced by Pydantic validators, so a stage physically cannot emit a record that breaks them.

1. **No acceptance without a verified span.** `AttributeStatus.ACCEPTED` requires at least one
   `Evidence` whose `verification` is `EXACT_SPAN` or `FUZZY_OCR_SPAN`. `UNVERIFIED` evidence
   may be stored and displayed as a discovery candidate, but it can never license acceptance.

2. **A verified span must be re-openable.** Any non-`UNVERIFIED` evidence must record a page.
   A span we cannot open is not verified. `FUZZY_OCR_SPAN` must also record the
   `match_score` it was accepted at.

3. **Status, applicability, and reason are three separate axes.** `AttributeStatus` is only
   `ACCEPTED`/`WITHHELD`. Strength lives in `SupportGrade`; the reason for withholding lives
   in `WithheldReason` (`NOT_FOUND`, `NOT_APPLICABLE`, `VARIANT_DEPENDENT`, `CONFLICTED`,
   `UNSUPPORTED_SPAN`, `OUT_OF_IDENTITY_SCOPE`). A user must always be able to tell *why* a
   field is empty. `WITHHELD` without a reason is rejected.

4. **A `NOT_APPLICABLE` feature is not a gap.** It cannot carry an accepted value and it
   leaves the coverage denominator.

5. **The support grade is derived, never asserted.** `ProductAttribute` recomputes the grade
   from its own evidence via `support.derive_support_grade` and rejects a mismatch. See
   *The support rule* below.

6. **Identity gates acceptance.** When `ProductIdentity.disposition` is not `EXACT`, every
   accepted attribute must carry `family_invariance=PROVEN`. Observing one child does not
   prove invariance across a family; `PROVEN` requires a family/variant table or agreement
   across multiple exact child references. Conversely an `EXACT` identity must not claim
   family proofs — the question does not arise.

7. **An incomplete reference must name its discriminator.**
   `FAMILY_OR_INCOMPLETE_REFERENCE` requires a `VariantAxis` or candidate MPNs, otherwise the
   disposition is unfalsifiable. `CONTRADICTORY` requires at least two rival readings.

8. **Values are bound to their ETIM feature type and unit.** A `N` feature takes a
   `NumericValue`; an `R` feature takes a `RangeValue`; the unit must equal the unit ETIM
   mandates for that class-feature. Normalize before accepting.

9. **A model may not resolve a `FACTUAL` conflict.** It stays conflicted or goes to a person.
   A model *may* classify a conflict's cause.

10. **ETIM range values satisfy min ≤ max.** Definitional, not physical.

11. **A replayed run must state its capture date.** `RunProvenance` with mode `REPLAY` or
    `MIXED` requires `captured_at`.

## The support rule

`SupportGrade` is a coarse, rule-derived band, **not a probability**. With a 50-SKU corpus
whose attribute rows are correlated within families, documents, and manufacturers, a decimal
would be statistical theatre. Calibration is P2, and until it exists nothing in this system
displays a probability-like number.

```
none  no verified span, or family invariance unproven  →  the value must be WITHHELD
A     verified span + manufacturer origin + exact-SKU scope + complete conditions
B     verified span, in scope, exactly one of those three missing
C     verified span, in scope, two or more missing
```

**Cluster count is deliberately not an input.** The earlier rule — "VERIFIED requires ≥2
independent clusters" — was wrong in a specific way: it made a second, weaker corroborating
source *necessary*, so a single exact-SKU manufacturer datasheet with a mechanically verified
span could never reach top support, while two mutually-copied distributor pages could. One
exact-SKU manufacturer datasheet whose span we located ourselves is the strongest evidence
available for an industrial part, and the rule now says so.

`independent_root_count` is logged from day one so P1 evidence-root deduplication has history
to work with, but it does not influence the P0 grade. Until that clustering exists, **extra
agreeing members never raise a grade** — which is the conservative direction.

`SupportFactors.factors` is an open mapping with a `rule_version`, so the factor set can grow
without a contract break. Only the documented keys participate in the rule.

## Conditions are data, not label text

`18 A` and `32 A` on one contactor are not a contradiction: they are its AC-3 and AC-1
ratings. `ConditionSet.key()` is the order-independent identity of an operating point, and two
observations may only be compared for factual agreement when their keys match. Anything else
is a `QUALIFIER` difference. `ConditionCompleteness` records whether every qualifier the
feature requires was actually bound; `PARTIAL` conditions cap the grade at B, because we do
not fully know what the value is a measurement of.

## Discovery is not provenance

`DiscoveryMethod` (how we found a candidate — including Google Search grounding and URL
Context) and `EvidenceVerification` (whether we located the span ourselves) are separate
fields, and only the latter can license acceptance. `SourceArtifact` keeps both
`discovery_url` and `final_url`, because a search citation URL is frequently not the artifact
we actually read.

## Evidence must work for tables

A datasheet specification is usually a cell in a row, not a prose sentence. `SpanLocator`
carries page, section, table/row/column indexes and headers, character offsets where text
extraction is reliable, and a bounding box where it is not. `Evidence` keeps both
`raw_fragment` (the source's own words, including a flattened table row) and
`normalized_quote` (what span verification matched), so a reviewer sees the source while the
machine check stays exact.

## Derived values keep lineage, not a second quote

`18000 mA → 18 A` is supported by the quote covering `18000 mA` plus a deterministic,
versioned `Derivation` (`transform_id`, `detail`). A normalized value does not need its own
quote; it needs traceable lineage back to a verified raw fragment. No language model
participates in any derivation.

## Coverage is counted four ways

ETIM features characterize a class; they are not a mandatory field list for a commerce
channel. Reporting `accepted / all ETIM features` would penalise inapplicable fields and
reward filling them. `CoverageReport` therefore separates:

- `etim_features_total` — what ETIM maps to the class;
- `applicable_total` / `not_applicable_total` / `applicability_unknown_total`;
- `accepted_total` — applicable features with an accepted value;
- `buyer_critical_*` — the hand-reviewed subset per class.

`buyer_critical_coverage` is the buyer-facing number. `etim_feature_coverage` is a diagnostic
and must never be presented as business completeness.

## Run modes

`LIVE`, `REPLAY`, `MIXED`. A `REPLAY` run replays interactions that were really captured
earlier — it is not synthetic and it is not fresh, and `RunProvenance.banner()` states both
along with the capture date. `MIXED` exists so a partially-recorded run can be represented
honestly rather than mislabelled; `is_publishable_evaluation` is `False` for it, and it is
barred from published evaluation and the public demo. Presenting a replayed run as live is a
correctness bug, not a presentation choice.

---

## Change log

### Checkpoint 1 reconciliation (`CODEX_REVIEW.md`)

| Was | Now | Why |
|---|---|---|
| `IdentityKind.{EXACT_SKU, FAMILY, AMBIGUOUS, UNKNOWN}` | `IdentityDisposition.{EXACT, FAMILY_OR_INCOMPLETE_REFERENCE, UNKNOWN, CONTRADICTORY}` | "Not a SKU" was too absolute; some channels list a family stem as orderable. The defensible claim is that a discriminator is unbound. |
| — | `Applicability` | ETIM features characterize a class; they are not required fields. |
| Conditions implied by the feature label | `Condition` / `ConditionSet`, first-class | So AC-3 18 A vs AC-1 32 A is a `QUALIFIER` difference, not a `FACTUAL` conflict. |
| `Evidence.quote` | `raw_fragment` + `normalized_quote` + `SourceArtifact` + `SpanLocator` with table coordinates | Specifications are table cells; and a search citation is not the artifact. |
| — | `EvidenceVerification`, `DiscoveryMethod` | Search grounding is discovery, not page-level provenance. |
| `AttributeStatus` with 5 mixed members | `AttributeStatus` (2) + `Applicability` (3) + `WithheldReason` (6) + `SupportGrade` (3) | One `INSUFFICIENT_EVIDENCE` was too coarse to tell a user why. |
| `VERIFIED` requires ≥2 independent clusters | Derived `SupportGrade` on evidence quality; cluster count unused in P0 | A single exact manufacturer span can be the strongest evidence available. |
| `EvidenceCluster` claimed independence | `EvidenceGroup` claims only agreement; `origin_note` says "likely same origin" | A robust provenance graph is P1. Near-duplicate text is not proof of lineage. |
| `confidence: float` + 6 frozen factors | `SupportGrade` + open, versioned `SupportFactors` | 50 correlated SKUs do not support probability calibration. |
| `completeness = accepted / all features` | `CoverageReport`, four counts | ETIM coverage is not business completeness. |
| `RunMode.AUTO` | `RunMode.MIXED`, barred from published evaluation | `auto` silently mixed recorded and fresh calls. |
| — | `Derivation` on every value | Normalized values need lineage, not a second quote. |
| Planned cross-attribute physics checks | **Removed entirely** | The contactor power/current relation carries assumed cosφ and efficiency; it would flag correct manufacturer data as inconsistent. Only definitional constraints remain. |
