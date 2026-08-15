# Evaluation data

Ground truth, and the discipline around it.

## The order of operations

```
define locked truth  ->  define metric code  ->  build the system  ->  measure honestly
```

Not the other way round. Metrics written after looking at a system's output are
metrics that system happens to score well on. The scorer in `backend/skutruth/eval/`
was written before the identity, extraction, and verification stages exist, precisely
so it cannot be tuned to flatter them.

## Splits

**`DEV`** may change during development. Look at it, debug against it, add to it.

**`LOCKED_TEST`** is for final reported numbers. Its truth is not edited because the
system did badly on it. If a locked case turns out to be *wrong* — mislabelled, a
misread datasheet, an ambiguity nobody spotted — fix it deliberately, say so, and note
that the fingerprint changed and why. Changing it because a metric was disappointing
is the one thing this whole apparatus exists to prevent.

There is no encryption and no access control here. This is process discipline, not DRM.

## Families never cross the split

A `product_family_id` belongs to exactly one split, and the manifest refuses to
validate otherwise.

The reason is specific. If `TEST-100-A` sits in `DEV` and its sibling `TEST-100-B`
sits in `LOCKED_TEST`, then every hour spent studying the first is preparation for the
second: the family's part-number grammar, its datasheet layout, its variant axis. The
locked score would measure how well we memorised one family, not how well the system
generalises. Splitting by family rather than by case is what keeps the locked set a
test.

## Failures stay in the report

A case that crashed, missed its cassette, or produced unparseable output is not
dropped. It stays in the denominators where it logically attempted something —
identity, coverage — because a system that fails to answer has not thereby avoided
being wrong. Silently excluding failures is the easiest way to make a bad run look
good, so the report counts them explicitly.

## Metric code is shared

`DEV` and `LOCKED_TEST` run through the same scoring functions. No split-specific
branches, no "locked mode" leniency.

## What a reported result must identify

Any number quoted anywhere — README, video, submission — must be traceable to:

- the **commit hash** of the code that produced it, and
- the **`manifest_fingerprint`** of the truth it was measured against.

The fingerprint is a SHA-256 over the canonical manifest: schema version, manifest id
and version, and every case's truth, with cases sorted by `case_id`. Reordering the
file does not change it — case ids are unique and order carries no meaning — but
changing any case's truth does. That is what lets us say *"these metrics came from
this set"* and have it checkable.

## Truth must be human-reviewed

A model-proposed label is not ground truth until a person has confirmed the value, the
page, and the operating conditions against the manufacturer artifact. `ReviewStatus`
records how far a case has got:

| Status | Meaning |
|---|---|
| `SYNTHETIC` | Structural fixture. Proves the scorer works. **Never a benchmark claim.** |
| `DRAFT` | Labelled once, not independently verified |
| `REVIEWED` | Labelled and verified against the artifact |

When authoritative truth genuinely is not available, record that rather than
manufacturing a label from distributor consensus.

## What is here now

`manifests/synthetic-smoke.json` — three obviously synthetic cases (`TestCo`,
`OtherCo`, `TEST-100`, `TEST-FAMILY-200`) that exercise the scorer's paths: an exact
identity, a family/incomplete reference, a correctly accepted attribute, a
citation-valid fixture, a citation-`NOT_EVALUATED` fixture, a `NOT_APPLICABLE`
feature, an expected withholding, and a locked-split case from a separate family.

**These are not real products, and their numbers are not SKUTruth performance.**

## The intended first real case

Documentation only — not yet a manifest entry, because there is no verified
manufacturer artifact in the repository to review truth against, and writing
specifications from memory would be exactly the fabrication this system is built to
refuse.

The shape it will take:

- **Input** — brand `Schneider Electric`, MPN `LC1D18`, description `Contactor`.
- **Expected identity** — `FAMILY_OR_INCOMPLETE_REFERENCE`, with the missing
  discriminator recorded as the coil voltage/type. The reference does not pin down
  every attribute until that is bound.
- **After resolution** — a separate case for a child such as `LC1D18P7`, expected
  identity `EXACT`, with attribute truth read off the manufacturer datasheet by a
  person, page and operating conditions recorded.

Attribute values, pages, and conditions get filled in from an ingested artifact, by a
reviewer, once document ingestion exists. Not before.
