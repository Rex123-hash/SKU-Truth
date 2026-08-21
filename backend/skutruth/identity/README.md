# Identity resolution

The first product-intelligence decision stage. Minimal input plus typed identity
evidence produces one frozen `IdentityDisposition`:

```
brand + MPN + typed identity evidence
        ↓
EXACT | FAMILY_OR_INCOMPLETE_REFERENCE | UNKNOWN | CONTRADICTORY
```

## Exact identity is a hard gate

The rule the whole package exists to enforce:

> **Constructing a candidate reference is not the same operation as confirming that the
> reference exists.**

`BASE1` plus a documented rule `control_circuit/ac_230 -> X1` yields the candidate
`BASE1X1`. That the concatenation succeeded proves only that the rule applied. A
catalogue's code table lists *codes*, not which combinations a manufacturer actually
builds — so a candidate is a question, not an answer.

`EXACT` therefore requires an `ExactReferenceFact` anchored to the candidate itself.

This asymmetry is deliberate. A confidently wrong exact SKU is worse than an honest
"which coil voltage?", because a buyer acts on the first and asks a question about the
second.

## Evidence facts

The resolver never reads document text or model prose. It adjudicates over four typed
facts, so the pipeline stays:

```
document parser → evidence facts → identity resolver
```

| Fact | Means |
|---|---|
| `ReferenceCompletionFact` | base reference X is incomplete; it needs discriminator K |
| `DiscriminatorMappingFact` | for X, K = V is written as code C, via a construction template |
| `ExactReferenceFact` | reference X exists as an exact manufacturer product |
| `VariationAxisFact` | X also varies along axis A |

## Stored HTML identity is resolved separately from search relevance

`identity.html` is an additive parser-to-fact adapter for a stored `HtmlArtifact`.
Search `EXACT` is not one of its inputs: search relevance licenses acquisition, while
artifact identity is decided only from the hashed page representation. The adapter also
requires the artifact's stored final authority to be `APPROVED_MANUFACTURER` and its
publisher context to match the requested brand.

The conservative exact rule requires a deterministically primary Product JSON-LD object
whose direct `mpn` matches the target under the frozen `canonical_mpn`. A matching direct
`sku`, visible-text occurrence, document title, and canonical URL are retained only as
corroboration. None can grant `EXACT_SKU` alone; Offer SKUs and nested recommendation or
accessory Products are never promoted to page identity.

Conflicting peer Product MPNs produce `REVIEW`. Missing structure, malformed JSON-LD,
publisher/authority failure, sibling MPNs, and title/text/URL-only matches produce
`WITHHOLD`. The exact path creates an `ExactReferenceFact` with its JSON pointer retained
in the derived HTML resolution record, then calls the unchanged generic resolver. The
record carries `identity_scope=EXACT_SKU` and `covers_mpn` without mutating
`metadata.json`, `original.html`, or `html-content.json`.

This does not claim every HTML page is resolvable or that JSON-LD is inherently correct.
It claims only that this narrow, manufacturer-authoritative Product structure is strong
enough to supply one typed identity fact under explicit ambiguity checks.

Construction lives in the *evidence*, not the resolver: how a completed reference is
spelled is a property of a publisher's numbering scheme. A template carrying a
placeholder this version cannot apply is rejected (`MalformedConstructionRule`) rather
than applied partially.

## Dispositions

**`EXACT`** — either the input MPN itself has an `ExactReferenceFact`, or a constructed
candidate does, matching on brand and on `canonical_mpn`. That fact's anchor must be
`EXACT_SKU`-scoped. `exact_mpn` is set; `candidate_exactness_confirmed` is true only in
the second case.

**`FAMILY_OR_INCOMPLETE_REFERENCE`** — completion evidence applies and at least one of:
a required discriminator was not supplied; the supplied selection has no mapping rule; a
candidate was constructed but nothing confirms it. The model forbids `exact_mpn` here, so
a candidate cannot be mistaken for a resolution.

**`UNKNOWN`** — no applicable evidence. "We have never seen this reference" never becomes
"it must be exact."

**`CONTRADICTORY`** — the evidence cannot be reconciled, and picking a reading would be
arbitrary. Raised when the same literal reference is called both exact and incomplete;
when one selection yields two different candidates; or when exact evidence points at
rival targets. Conflicting facts stay in the trace. The resolver never prefers whichever
fact was listed first.

## Range evidence establishes incompleteness; only exact-SKU evidence confirms

A catalogue is `IdentityScope.RANGE` — good enough to prove a reference is a family stem,
never good enough to confirm a specific child, because it lists *codes* rather than which
combinations a manufacturer actually builds. `FAMILY` has the same problem one level down.

So `ExactReferenceFact` — the only fact that can license `EXACT` — **requires its anchor
to be `IdentityScope.EXACT_SKU`**, and refuses to be constructed otherwise. A missing
scope is rejected too: unrecorded provenance is not exact provenance. The scope is never
silently upgraded to fit, since rewriting it would forge the very thing being checked.

That invariant is on the model, not in the resolver. Inadmissible evidence therefore
cannot sit in an `IdentityEvidence` bundle waiting for a future refactor to trust it.

The restriction is deliberately narrow. `ReferenceCompletionFact`,
`DiscriminatorMappingFact`, and `VariationAxisFact` all still accept `RANGE`-scoped
catalogue evidence — proving a reference is incomplete is exactly what a catalogue is
good for.

Evidence for a *sibling* confirms the sibling: matching uses the frozen contract's
conservative `canonical_mpn`, which folds only case and whitespace. Hyphens, packaging
suffixes, and regional suffixes are left alone, because every one of those can
distinguish genuinely different parts. This stage is not a fuzzy MPN matcher.

## Brand binding

Evidence must match the requested manufacturer. `canonical_brand` folds case and
whitespace only — `Schneider` does **not** match `Schneider Electric`. Facts about the
same MPN under another brand are counted, surfaced as a warning, and otherwise ignored.
If an alias map is ever needed it belongs in explicit configuration, not in a normaliser
that quietly widens.

## Variation axes

Real catalogues vary along more axes than the one completing the printed reference.
`VariationAxisFact` is **informational by default**: it produces a warning and appears in
`known_variation_axes`, but does not block resolution. Only `blocks_resolution=True` —
which the evidence must state explicitly — makes an axis a required discriminator.

This stops the eventual UI from implying "choose the coil voltage and all ambiguity
disappears" when the catalogue is more nuanced.

## No confidence scores

There is no probability field anywhere in this package, and a test enforces that. A
`0.9` would invite callers to treat it as "exact enough". The disposition is the answer
and the trace is the justification.

## Trace

`IdentityResolution.explain()` renders numbered steps built only from explicit facts,
each carrying the anchor it rests on. Nothing is hidden and nothing is added.

## Not claimed here

Anchors record artifact hash, page, publisher, and a short observed statement. They carry
no `EvidenceVerification` — span verification does not exist yet, and stamping
`EXACT_SPAN` on a curated fact would claim a mechanical check nobody ran. Nothing here
sets `proves_family_scope` or builds a `ProductAttribute`; the control-circuit selection
is an *identity discriminator*, not an extracted attribute.

## The LC1D18 vertical slice

Validated locally against real Schneider evidence, as an **example of supplying facts** —
not as resolver logic. No brand name, base reference, or completion code appears in any
of this package's Python; a test asserts it, and this README is the only file here that
names one. The real facts are built in an uncommitted local adapter from the reviewed
research in `research/lc1d18_artifact_note.md`, and committed tests use synthetic
references (`TestCo`, `BASE100`) only.

Its shape, for orientation:

1. catalogue records `LC1D18` as a basic/partial reference needing a control-voltage code
2. no selection supplied → `FAMILY_OR_INCOMPLETE_REFERENCE`, unresolved `control_circuit`
3. selection `ac_230v_50_60hz` → catalogue rule maps it to `P7` → candidate `LC1D18P7`
4. the exact `LC1D18P7` product data sheet confirms it → `EXACT`

Step 4 is not optional. Without it, step 3 stops at
`FAMILY_OR_INCOMPLETE_REFERENCE` with `candidate_exactness_confirmed = false`.
