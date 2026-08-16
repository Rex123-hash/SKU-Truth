# Mechanical evidence verification

## LOCATING A QUOTE IS NOT VERIFYING A CLAIM

Finding `18 A` on a page proves the characters `18 A` are on the page. It does not
establish that *this product* is rated 18 A, still less that it is rated 18 A **under
AC-3 at 440 V**. A model that returns a page number and a quote has asserted something
about itself; it has not been checked.

This is the layer that checks.

```
Gemini proposal → schema validation → ValidatedExtractionCandidate
                                              ↓
                                   MECHANICAL VERIFICATION
                                              ↓
                                     verified candidate
```

## What `EXACT_SPAN` requires

All six, from **one coherent unit** of the real artifact:

1. the artifact is the one the claim's provenance names, and its stored bytes still hash
   to that digest;
2. the page exists and the model's fragment actually occurs on it;
3. the occurrence is unambiguous, or every occurrence supports the claim identically;
4. the artifact's own text states the claimed value, in a compatible unit, **with a
   matching relation**;
5. every bound condition is supported by that same unit;
6. the unit belongs to the target product.

There is no partial credit. A claim whose number checks out but whose operating point
does not is not "mostly verified" — it is a rating attached to the wrong conditions.

## The model's quote is a locator, not the evidence

```
model fragment → find it in the artifact → take the artifact's own line → verify against that
```

Both strings are retained on the outcome (`proposed_fragment` and `matched_text`). A
divergence between them is itself a finding, and only the second one is evidence.

## Operators are first-class

These are four different statements, and the verifier never conflates them:

```
< 60 °C     <= 60 °C     = 60 °C     > 60 °C
```

Three failures from the first live Gemini run all reduce to a dropped relation:

| Source says | Model proposed | Result |
|---|---|---|
| `< 60 °C` | `60 °C` | `OPERATOR_MISMATCH` |
| `<= 440 V` | `440 V` / `400 V` | `OPERATOR_MISMATCH` |
| `50/60 Hz` | `50 Hz` | **supported** — see below |

"Rated up to 440 V" and "measured at 440 V" are not the same claim. A value sitting
*inside* a bound is not a value the document states.

## Enumerations are not ranges

`50/60 Hz` asserts two discrete alternatives, both of which the document claims. So a
condition of `50 Hz` **or** `60 Hz` is supported by set membership.

This is not a guess about the model's intent: ETIM encodes `Rated control supply voltage
AC 50 Hz` and `… AC 60 Hz` as separate features, each with a reviewed rule expecting its
own frequency. A source phrase covering both legitimately supports both.

A *range* like `100-250 V` is deliberately not treated this way.

## The one-evidence-unit rule

Value and every condition must be supported **within a single unit**:

* **text** — one source line. A datasheet states a rating and its operating point on one
  row, so bounding the unit to that line makes the rule mechanical: a qualifier three
  paragraphs away is simply not inside the region being examined.
* **table** — one body row plus the header cells above it. That is not Frankenstein
  evidence, because the page itself asserts the relationship by drawing the column.

A number from paragraph A married to a voltage from paragraph B and a category from
footer C is never one verified claim.

## Product and artifact binding

Row identity is a **gate**. Before a table row may support a claim, a cell in it must
carry a reference matching the target under the frozen `canonical_mpn` comparison. A
correct number in the wrong row is a wrong answer, and a family placeholder such as
`LC1D18pp` does not support its own child — that is the family-to-exact leap the identity
gate exists to prevent.

Artifacts are always loaded through `ArtifactStore` with integrity re-checked. A hash
mismatch, a missing page, or a tampered page file **fails closed**: verification whose
provenance is uncertain is not weaker evidence, it is none.

A `RANGE` catalogue may still be evidence, but it stays range evidence.
`artifact_scope_supports_exact` returns False for it rather than manufacturing exact
applicability, and nothing here sets `proves_family_scope`.

## Source typography, not OCR

`TextMatchMode.NORMALIZED` covers representation-only differences — NBSP, exotic spaces,
Unicode form. No character is substituted and no number is altered, so a normalized hit is
as exact as a literal one. Both map to `EXACT_SPAN`.

**`FUZZY_OCR_SPAN` is never emitted.** No OCR runs in this system, and borrowing OCR
terminology for whitespace folding would misdescribe what was checked.

Unit *typography* is resolved separately: manufacturers write `KW` for kilowatt and `Mm`
for millimetre. `resolve_source_unit` tries every case variant and resolves **only if
exactly one registry symbol matches**. In the current registry that guard fires on
exactly one pair — `mW` against `MW` — which is precisely where guessing would be a
thousand-fold error. The `units` module itself still refuses to fold case, correctly: it
is the conversion authority. Reading a publisher's typography is a different job.

## Vocabulary independence

`ProductClaim` reuses the frozen `AttributeValue` and `ConditionSet` but knows nothing
about ETIM classes — `key` is opaque. The engine modules import nothing from
`skutruth.extraction`; only `adapters.py` does, and a test enforces it.

That seam matters now that the competition-facing vocabulary is Unilog. A Unilog
LOV-backed claim will verify through exactly the same engine.

## Verified is not accepted

This milestone ends at verified evidence. It never builds a `ProductAttribute`, never
assigns a support grade, and has no confidence or probability field anywhere — a test
enforces that. Grading depends on authoritativeness and scope as well, and deciding
whether a fact reaches a Unilog delivery slot is adjudication's job.

Every failure carries a specific reason: `ARTIFACT_MISMATCH`, `ARTIFACT_UNREADABLE`,
`PAGE_NOT_FOUND`, `SOURCE_FRAGMENT_NOT_FOUND`, `AMBIGUOUS_MATCH`, `VALUE_NOT_SUPPORTED`,
`UNIT_NOT_SUPPORTED`, `OPERATOR_MISMATCH`, `CONDITION_NOT_SUPPORTED`,
`TABLE_STRUCTURE_UNRESOLVED`, `PRODUCT_REFERENCE_MISMATCH`, `PRODUCT_SCOPE_NOT_SUPPORTED`,
`UNSUPPORTED_VALUE_KIND`. Never a bare "unverified".

## Known limitations

* **Range and logical values are not verified** — withheld as `UNSUPPORTED_VALUE_KIND`
  rather than approximated. A wrong range is a wrong specification.
* **Controlled-vocabulary mapping is not verification.** A source saying `screw clamp
  terminals` does not textually support the picklist label `Screw connection`. That is a
  legitimate mapping, but it is not something text matching can establish, so it stays
  unverified until a vocabulary-aware adapter exists.
* Mixed-inch fractions (`24-1/4 in`) are not parsed; the pattern is ambiguous with a
  hyphenated range.
