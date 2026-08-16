# LC1D18 — first real manufacturer source evidence

Evidence-acquisition note. Derived observations only; the Schneider documents themselves
are **not** in this repository (see [Redistribution](#redistribution)).

- **Target input:** brand `Schneider Electric`, MPN `LC1D18`, description `Contactor`
- **Retrieved:** 2026-08-16 (UTC)
- **Ingested with:** `pdf-ingest@v1`, pypdf 6.16.1, commit `3a02ad5`

Claims below are tagged **OBSERVED** (directly present in Schneider evidence),
**INFERRED** (reasoned from observed evidence), or **NOT YET ESTABLISHED**.

---

## 1. Artifacts

All three are Schneider-hosted (`download.se.com`), HTTPS, `application/pdf`. Each was
downloaded twice; both fetches produced identical SHA-256, so the bytes are stable.

| # | Role | SHA-256 | Bytes | Pages |
|---|------|---------|-------|-------|
| A | TeSys Contactors catalogue extract (**primary**) | `ca5977404d8aef9e9b3c1fd6339b7039b3aede4536f635a105ea9d1212bb8fdd` | 17,409,131 | 62 |
| B | `LC1D18P7` product data sheet | `3cd09da60af3d516a70b753252c13c0c0e69e4785b7e0b5d96f9a447b9191dee` | 88,845 | 4 |
| C | `LC1D18` product data sheet (empty shell) | `05c06bbfe5b0f249e0e7d4db1b175757a617b18177e9c4b63e622145ffd0da95` | 26,039 | 1 |

**A** — `discovery_url` and `final_artifact_url` differ only by Schneider's own 301 from
`download.schneider-electric.com` → `download.se.com`.
`document_version`: `Extract from Tesys Catalogue | 2017 - 2018` (printed on page 1).
`identity_scope=RANGE` (set only after inspecting: it covers many TeSys families).
`source_type` left **null** — see [Open questions](#7-open-questions).

**B** — discovered via the official `se.com` product page for `LC1D18P7`; the PDF URL was
then resolved through Schneider's documented `download.se.com` `p_Doc_Ref=<MPN>_DATASHEET`
pattern and confirmed by the response's `Content-Disposition` filename.
`source_type=MANUFACTURER_DATASHEET`, `identity_scope=EXACT_SKU`, `covers_mpn=LC1D18P7`.

**C** — same URL pattern with `p_Doc_Ref=LC1D18_DATASHEET`.
`identity_scope` left **null**: the document carries no characteristics, so its scope is
genuinely unknown rather than merely unrecorded.

Page numbers below are **PDF page indices**, with the catalogue's printed folio in
brackets — they do not coincide (`pdf p4` = printed `B8/2`).

---

## 2. What LC1D18 denotes

**OBSERVED (A).** On every selection table listing it, `LC1D18` never appears as a
standalone orderable reference. It appears under a column headed *"Basic reference, to be
completed by adding the control voltage code"* — and on `pdf p16 [B8/14]` the same column
is headed *"Partial reference, to be completed by adding the control voltage code"*.

**OBSERVED (A).** The reference is printed with trailing placeholder characters, which the
extractor renders as literal `p` (U+0070): `LC1D18pp` on `pdf p4 [B8/2]` and `pdf p6
[B8/4]`, `LC1D18ppp` on `pdf p15 [B8/13]`. The *printed* glyph is **NOT YET ESTABLISHED**
from text alone — `p` is a font/ToUnicode mapping artifact, not necessarily the ink.

**OBSERVED (A).** `LC1D18` occurs on 10 pages: `pdf p4–p10 [B8/2–B8/8]` and `pdf p15–p17
[B8/13–B8/15]`. Every occurrence is in placeholder form. The literal string `LC1D18P7`
occurs **zero** times in the catalogue.

**OBSERVED (C).** Schneider's datasheet generator returns a valid 1-page PDF for
`p_Doc_Ref=LC1D18_DATASHEET` containing only `Product data sheet / Characteristics /
LC1D18 / 16 Aug 2026` — 55 characters, and no product data whatsoever. The same generator
returns 4 populated pages for `LC1D18P7`.

**INFERRED.** `LC1D18` is a **base/partial reference, not an orderable product**. Two
independent official signals agree: the catalogue explicitly labels it as requiring
completion, and Schneider's own product database yields an empty characteristics sheet for
it while yielding a full one for a completed child.

**NOT YET ESTABLISHED.** Whether the empty sheet (C) means "no such product record" or is
a generator fallback for any unknown string. It corroborates but does not independently
prove the conclusion.

---

## 3. The discriminator axis

**OBSERVED (A, `pdf p4 [B8/2]`, repeated `p6 [B8/4]` and `p9 [B8/7]`).** The footnote
*"Standard control circuit voltages"* prints two aligned rows for a.c. supply — 13 voltages
and 13 codes, one-to-one:

```
Volts      24  42  48  110  115  220  230  240  380  400  415  440  500
50/60 Hz   B7  D7  E7  F7   FE7  M7   P7   U7   Q7   V7   N7   R7   S7
```

A parallel d.c. table gives `12→JD, 24→BD, 36→CD, 48→ED, …`.

**OBSERVED.** The completing code is therefore the **control-circuit (coil) voltage and
supply type**. The catalogue names no other axis as the thing that completes the reference.

**INFERRED.** `P7` = **230 V a.c. 50/60 Hz**. The catalogue mapping is positional (rows are
aligned by index, not explicitly paired), so on the catalogue alone this is inference — but
it is independently **confirmed** by artifact B, which states `[Uc] control circuit voltage
230 V AC 50/60 Hz` for `LC1D18P7`. Two official sources agree.

**OBSERVED — coil voltage is not the only variation axis.** The catalogue distinguishes
further, *orthogonal* variations that are encoded in the digits **before** the voltage code,
not by it:

- terminal/connection type — screw clamp `LC1D18pp` (`p4`), spring terminals `LC1D183pp`
  (`p5 [B8/3]`), and a `LC1D188pp` form on `p8 [B8/6]`;
- sub-range — *TeSys D Green* uses a **three**-character placeholder `LC1D18ppp`
  (`p15–p17 [B8/13–B8/15]`).

**INFERRED.** Placeholder width is not a reliable code-length rule: the standard table uses
two placeholders yet `FE7` is a three-character code.

**NOT YET ESTABLISHED.** Whether the base string `LC1D18` alone (no connection digit)
canonically implies the screw-clamp variant, or is ambiguous across connection types. The
catalogue prints `LC1D18pp` for screw clamp and `LC1D183pp` for spring, which suggests the
bare form is the screw-clamp family — but it is not stated.

---

## 4. LC1D18P7

**OBSERVED (B).** `LC1D18P7` is a real Schneider reference with a full product data sheet:
*"Contactor, TeSys Deca, 3P(3NO), AC-3/AC-3e, <=440V, 18A, 230V AC 50/60Hz coil, screw
clamp terminals"*, `Range of product TeSys Deca`, `Device short name LC1D`, and
`Product Life Status : Commercialised`.

**OBSERVED (A).** `LC1D18P7` as a literal string is **absent** from the catalogue.

**INFERRED.** `LC1D18P7` is the child of base reference `LC1D18` completed with coil code
`P7`. The catalogue supplies the construction rule; the datasheet supplies the completed
reference and confirms the coil voltage the rule predicts. No single document states the
composition explicitly.

### Conditioned ratings

Only values actually present are recorded. **Nothing here is a `ProductAttribute` and
nothing is span-verified** — this milestone creates no `Evidence`.

**OBSERVED (B, page 1)** — `[Ie] rated operational current`:

- `18 A (at <60 °C) at <= 440 V AC AC-3`
- `32 A (at <60 °C) at <= 440 V AC AC-1`
- `18 A (at <60 °C) at <= 440 V AC AC-3e`

**OBSERVED (A)** — `pdf p4 [B8/2]` column *"Rated operational current in AC-3 440 V up to"*
gives `18` A for the `LC1D18` row; `pdf p6 [B8/4]` column *"Non inductive loads maximum
current (θ ≤ 60 °C) utilisation category AC-1"* gives `32` A. Catalogue and datasheet agree.

> ⚠️ **Correction to a prior assumption.** The conditioning voltage is **≤ 440 V, not
> 400 V**. Both sources say `≤ 440 V`. The figure attached to 400 V is a *motor power*,
> not a current: **OBSERVED (B)** `7.5 KW at 380/400 V AC 50/60 Hz (AC-3)`. The phrase
> "400 V" does appear in the catalogue, but as a range-level section heading
> (*"TeSys D contactors for motor control up to 75 kW at 400 V, in category AC-3"*), which
> is about the whole range, not about `LC1D18`.

**OBSERVED.** `AC-3e` appears 5× in artifact B and **0×** in artifact A — the 2017–2018
catalogue predates that utilisation category.

---

## 5. Parser quality (pypdf 6.16.1)

Ingestion itself needed no code change and reported no warnings. Document-level status:
A = `PARTIALLY_EXTRACTABLE` (61 of 62 pages text-bearing), B and C = `TEXT_EXTRACTABLE`.

| Page(s) | Relationship | Verdict |
|---|---|---|
| A `p4 [B8/2]` | reference ↔ AC-3 current | **GOOD** |
| A `p4 [B8/2]` | reference ↔ kW ↔ voltage matrix | **UNUSABLE** |
| A `p6 [B8/4]` | reference ↔ AC-1 current ↔ poles | **GOOD** |
| A `p4/p6/p9` | voltage ↔ coil code footnote | **GOOD** |
| A `p5,p7,p8,p10,p15–p17` | multi-voltage rating matrices | **DEGRADED** |
| B (all 4) | label ↔ value pairs | **GOOD** |

**Why `p4`'s kW matrix is UNUSABLE — concrete failure.** The row extracts cleanly as
`4 7.5 9 9 10 10 – 18 1 1 LC1D18pp 0.330` (7 kW values). But the header's voltage labels
extract with line breaks that do not correspond to column boundaries:

```
'220 V ' / '230 V' / '380 V' / '400 V' / '415 V 440 V 500 V 660 V ' / '690 V' / '1000 V'
```

Ten labels, seven kW columns, and the breaks fall in the wrong places. Reading each label
as its own column yields **400 V → 9 kW**. Artifact B says **380/400 V → 7.5 kW**. The true
grouping is `[220/230][380/400][415][440][500][660/690][1000]`, which is *not recoverable
from the extracted text*. This is worse than missing data: the naive reading is silently
**wrong**, and only a second document caught it.

The GOOD rows survive because their columns are single-valued and sit adjacent to the
reference on the same output line.

**No parser fallback has been added.** Recording the concrete failure first, per plan.

---

## 6. Identity conclusion

**SUPPORTED** — the evidence is sufficient to treat `LC1D18` as a family / incomplete
reference whose unresolved axis is the control-circuit (coil) voltage and supply type.

Supporting chain: the catalogue explicitly calls it a *basic* / *partial* reference "to be
completed by adding the control voltage code" (OBSERVED); the completing code table is the
coil-voltage table (OBSERVED); a completed child `LC1D18P7` exists as a commercialised
Schneider product with the coil voltage that code predicts (OBSERVED); and Schneider's own
datasheet generator has no product data for the bare string (OBSERVED).

Two caveats the resolver must not paper over:

1. Coil voltage is the axis that *completes the printed reference*, but it is **not the
   only** variation axis — connection type and the Green sub-range vary in the digits before
   the code. A resolver that treats "coil voltage" as the sole missing discriminator will be
   right about this reference for the wrong reason.
2. `identity_scope=RANGE` for the catalogue means it is **not** exact-SKU evidence. Ratings
   read from it apply to the `LC1D18` family; only artifact B binds them to `LC1D18P7`.

---

## 7. Open questions

- `SourceType` has no member for a manufacturer-published **catalogue**.
  `MANUFACTURER_DATASHEET` is wrong (it is not a datasheet) and `TRUSTED_CATALOG` reads as
  third-party. Artifact A was therefore ingested with `source_type=null`. The frozen enum
  may need a `MANUFACTURER_CATALOGUE` member.
- Artifact B's page 1 carries `Price*: 43781.42 NGN`, i.e. the download endpoint is
  **geolocated**. The same `p_Doc_Ref` may return locale-varying bytes and therefore a
  different SHA-256 from another network. Hash stability was confirmed only for this host.
- Whether bare `LC1D18` canonically implies screw-clamp connection (see §3).
- Whether artifact C's empty sheet is a meaningful "no such product" signal or a generic
  fallback.

---

## Redistribution

The three PDFs are Schneider Electric copyright. They were downloaded for local analysis
only; redistribution rights are **not** established. They live in `data/artifacts/runtime/`,
which is gitignored, and each carries a `license_note` recording this. They must never be
committed nor promoted to `data/artifacts/fixtures/`. This note deliberately contains only
short structural excerpts and derived observations.
