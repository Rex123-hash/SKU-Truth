# Unilog data pack — audit and architecture reconciliation

Audit milestone. No pipeline code was written. Derived observations only; the organizer
files live in `data/unilog_source/` (gitignored) and no organizer table is reproduced here.

- **Date:** 2026-08-17
- **Repo at audit:** `2493e65`, 686 tests passing

---

## 1. What actually arrived

**Two files, not ten.** The brief and the organizer guide describe a ten-file pack. Only
two CSVs exist on disk. Everything below is grounded in those two; nothing about the
missing files is inferred.

| # | File | Status |
|---|---|---|
| 1 | `Unihack_ Sample Dataset - Input.csv` | **PRESENT** — 1,000 rows × 6 cols |
| 2 | `Unihack_ Expected Output - Delivery Format.csv` | **PRESENT** — **2** rows × 252 cols |
| 3 | `Unilog-Sample_200_Items-Input-vs-Output.xlsx` | **MISSING** |
| 4 | `UNILOG_INTERNAL_CONTENT_GUIDELINES.docx` | **MISSING** |
| 5 | `Unilog_Master_UOM_Standards_…xlsx` | **MISSING** |
| 6 | `Decimal_Fraction.xlsx` | **MISSING** |
| 7 | `UniCat_Manufacturer_and_Brand_List.xlsx` | **MISSING** |
| 8 | `Unicat_Lov_v1_0_Updated_With_Remarks.xlsx` | **MISSING** |
| 9 | `FAUCETS_LOV.xlsx` | **MISSING** |
| 10 | `Fittings_LOV.xlsx` | **MISSING** |
| 11 | `Reference_Documents_Summary.xlsx` | **MISSING** |

### Two corrections to the brief's assumptions

1. **There is no 200-row labelled ground truth.** The delivery file contains **2 data
   rows**, both built-in dishwashers. It is a *format specimen*, not a scored training or
   test set. Every accuracy metric the brief proposes is currently uncomputable.
2. **The input CSV is the 1,000-row scale file, not the 200-item input.** Its columns are
   exactly the six documented for `Sample-1000_Items`, with no `Dept`/`Class`/`Fine`/`SKU`.
   Those four *do* appear inside the delivery file, so the 200-item input sheet is
   genuinely absent rather than renamed.

Consequence: this is a **schema-and-rules** pack right now, not an evaluation pack.

---

## 2. Input file — 1,000 raw rows

Columns: `Mfg_Part_Num`, `Part_Desc`, `E1_Brand`, `Unilog_Brand`, `DIB_Brand`, `Part_Manuf`.
Every row is exactly 6 fields; no merged cells or multi-row headers.

### Placeholder burden is the headline

| Column | Real values | Placeholder | Distinct real |
|---|---|---|---|
| `Mfg_Part_Num` | 1,000 | 0 | 999 |
| `Part_Desc` | 1,000 | 0 | 998 |
| `E1_Brand` | 201 | **799** | 12 |
| `Unilog_Brand` | **0** | **1,000** | 0 |
| `DIB_Brand` | 245 | 755 | 23 |
| `Part_Manuf` | 1,000 | 0 | 76 |

Exact placeholder strings: `-- Unbranded --`, `-- No Unilog Brand --`, `-- No DIB Brand --`.

**`Unilog_Brand` is 100% placeholder** — it carries no information at all.
**An undocumented placeholder also exists:** `Part_Manuf == "-"` on **41 rows**. The
brief's placeholder list does not mention it, so a policy keyed only to `-- … --` would
admit 41 junk manufacturers.

### `Part_Manuf` is structured, and it is the only reliable identity signal

959/1,000 values parse as `Name (CODE)` — e.g. `Kichler Lighting (KICLI)`. Code lengths
are 4 (583) or 5 (376); the 41 unparseable values are all `-`. So a supplier code is
already embedded and extractable deterministically, before any fuzzy matching.

Spellings that will need canonicalisation (**cannot be confirmed — master list missing**):
`Phillips Lighting` (111 rows; likely *Philips*), `Black & Decker/dewlt` (55 rows; likely
*DeWalt*), `Makita Usa Inc`, `Freud Inc`.

Only **1 duplicate** MPN across 1,000 rows, so de-duplication is not a live problem here.

### Category mix — and the finding that changes the demo choice

Keyword scan of `Part_Desc`:

| Bucket | Rows |
|---|---|
| Lighting | 166 |
| Decking / lumber (TREX, TimberTech) | 159 |
| Power-tool accessory | 132 |
| Appliance | 58 |
| Electrical | 16 |
| Window / door | 2 |
| **Faucets** | **0** |
| **Fittings** | **0–3** |
| unmatched | 468 |

`Part_Desc` is short — median 35 chars, max 70 — and heavily abbreviated
(`3M 775L Stikit Film P150 - Cubitron II 50 Disc/Box`).

---

## 3. Delivery format — 252 columns, 2 examples

All 252 columns classify cleanly; nothing was left ungrouped.

| Group | Cols | Populated in ≥1 example |
|---|---|---|
| Attributes (`LABEL`/`VALUE`/`UOM` × 50) | **150** | 33 |
| Digital assets | 25 | 6 |
| Feature bullets (`ITEM_FEATURES_1..20`) | 20 | 11 |
| Input passthrough | 11 | 11 |
| Content / descriptions | 7 | 7 |
| Source URLs (`MFR URL`, `Ref URL 1–5`) | 6 | 3 |
| Identity | 5 | 3 |
| Commercial | 5 | 1 |
| Content extras (`With`, `Standard/Approvals`, …) | 5 | 2 |
| Pack dimensions | 10 | 0 |
| Identifiers (UPC/EAN/GTIN) | 3 | 0 |
| Classification (`Classpath`, `UNSPSC`) | 2 | 1 |
| Flags | 3 | 1 |

Fill: **55** columns populated in both examples, 24 in one, **173 empty in both**. Sixty
percent of the schema is the attribute block, and only 15 of its 50 slots are used.

### The most important structural finding

**The attribute block is a fixed, ordered, classpath-driven template.** Both examples
emit the *identical label sequence*, including deliberately blank slots (`Model`,
`Plug Type`):

`Series · Model · Number of Wash Cycles · Voltage Rating · Amperage Rating · Mounting
Type · Plug Type · Size · Depth With Door Open · Minimum Height · Maximum Height · Sound
Level · Material · Color · Additional Information`

This is not free-form extraction into arbitrary columns. It is **fill a known ordered slot
list for a classpath** — which maps directly onto our existing per-class schema generator,
and means position carries meaning and empty slots must be preserved.

### Observable formatting rules (derived from the 2 examples, since the rulebook is missing)

- **Value/UOM split is conditional.** Scalars split (`Depth With Door Open = 50-1/4`,
  `uom = in`); compound values keep units inline with an empty UOM column
  (`Size = 24 in W x 24-1/4 in D`).
- **Fractions**, mixed-inch `WHOLE-NUM/DEN`: `50-1/4`, `33-7/16`, `22-5/8`, `10-3/8`.
- **Space between number and unit** in long/short/attribute text: `120 V`, `47 dBA`, `24 in`.
- **`INVOICE_DESC`**: ALL CAPS, 38 and 39 chars (≤40), and units are **closed up**:
  `120V`, `15A`, `41DBA`, `50-1/4IN`.
- **Multi-value separator is `|`** (`Standard/Approvals`: 6 pipe-separated values).
- `RETAIL_DESC` reads as `SHORT_DESC` minus brand and MPN.
- Lengths observed: MOBILE 64/75, SHORT 96/115, LONG 390/405.

---

## 4. Data-quality problems found

1. **Manufacturer/brand mismatch in example 1.** `MANUFACTURER_NAME = Rheem
   Manufacturing` with `BRAND_NAME = FRIGIDAIRE®` and `MFR URL = frigidaire.com`. Rheem
   does not make Frigidaire dishwashers. The organizer guide flags such a row as expected;
   **reported, not corrected.**
2. **The delivery data violates the stated space-before-unit rule** in `INVOICE_DESC`
   (`120V`, `41DBA`). Most likely a deliberate exception for the 40-char invoice line, but
   the rulebook that would confirm it is missing, so this stays an open question rather
   than an assumption.
3. **`MOBILE_DESC` is internally inconsistent.** Example 1 leads with manufacturer +
   brand (`Rheem Manufacturing FRIGIDAIRE, …`); example 2 leads with brand only and
   **drops the ® symbol** (`Whirlpool, …`) that `SHORT_DESC` keeps.
4. **Undocumented placeholder** `-` in `Part_Manuf` (41 rows).
5. `UNSPSC`, `Country Of Origin`, all UPC/EAN/GTIN and all pack dimensions are empty in
   both examples — the schema is far wider than the demonstrated content.
6. Example 2 carries 11 feature bullets and a marketing paragraph; example 1 carries
   none. Content depth is not uniform even within one classpath.
7. `Part_Desc` contains retail-operations noise (`- Display Only`) that is not product
   specification.

---

## 5. What this means for SKUTruth

The trust architecture survives; the *output vocabulary* changes.

| Capability | Organizer need | Current status | Verdict |
|---|---|---|---|
| Raw row ingestion (CSV/XLSX) | High | **None** | **New** — small, deterministic |
| Placeholder policy | High | None | **New** — trivial, high value |
| Manufacturer/brand canonicalisation | High | None | **New** — *blocked*: master list missing |
| Classpath classification | High | None | **New** — *blocked*: LOV missing |
| Ordered attribute template per classpath | High | `schema_gen` (ETIM-shaped) | **Reuse + retarget** |
| Identity resolution | Medium | **Done** | **Reuse as-is** |
| PDF artifact ingestion | Medium | **Done** | **Reuse as-is** |
| Table extraction | Medium | **Done** | **Reuse as-is** |
| Gemini structured extraction | High | **Done** | **Reuse**, swap the schema source |
| Record/replay | Infrastructure | **Done** | **Reuse as-is** |
| Deterministic validators | High | **Done** (ETIM) | **Reuse the machinery**, new vocabulary |
| UOM / fraction normalisation | High | Partial (`units`) | **Extend** — *blocked*: UOM sheet missing |
| Description building (5 forms) | High | None | **New** — rules partly inferable |
| Digital assets | Medium | None | **New** — naming convention observable |
| Evaluation | High | **Done** (framework) | **Reuse**, *blocked*: no labelled truth |
| Batch output | High | None | **New** |

**Nothing built so far is wasted.** Identity resolution, ingestion, table extraction,
record/replay, and the extraction service are vocabulary-agnostic. What changes is that
the *schema source* becomes Unilog's classpath template instead of an ETIM class, and the
*validator vocabulary* becomes Unilog LOV/UOM instead of ETIM enums. Both were already
built behind interfaces.

### ETIM's new role

**Keep it as an internal normalisation aid and a secondary standards adapter — not the
competition-facing output.** Where the organizer supplies a controlled vocabulary, that
vocabulary wins. ETIM retains three concrete uses: it is the only working example of a
class→ordered-attribute-template we have while the LOV is missing; its unit registry and
validators already implement the conversion machinery UOM normalisation needs; and it
remains the right output for the electrical vertical. Removing it would delete working
infrastructure to gain nothing.

---

## 6. Demo category recommendation

**Primary: built-in dishwashers / large appliances. Do not pick faucets.**

The brief warned against defaulting to faucets, and the data agrees emphatically:

- faucets: **0 rows** in the 1,000-row file; fittings: **0–3**;
- both delivery examples are **built-in dishwashers**, so the only fully-worked output
  we possess — attribute template, all five description forms, asset naming — is appliance;
- the appliance bucket has 58 rows for a batch demo, 10 of them dishwashers;
- `FAUCETS_LOV.xlsx` and `Fittings_LOV.xlsx` are missing, so their depth cannot be assessed.

Second choice if breadth is wanted: **lighting** (166 rows, and the `Phillips Lighting`
misspelling across 111 rows is a vivid canonicalisation demo) or **decking** (159 rows,
concentrated in TREX/TimberTech, where `E1_Brand` actually carries real values).

**LC1D18P7 stays an engineering example, not the judge-facing demo** — it is not in the
organizer data.

---

## 7. Evaluation reality

With 2 labelled rows, **no accuracy metric is honestly computable**, and no train/dev/test
split is meaningful. Do not report field-level accuracy against n=2.

What *is* computable today, without labels:

- placeholder-filtering correctness (exact, deterministic);
- `Part_Manuf` code-extraction rate (**95.9%** parse as `Name (CODE)`);
- schema conformance: does output fill the 252-column contract in the right order;
- character-limit compliance (`INVOICE_DESC ≤ 40`, mobile 60–80);
- format compliance: fraction form, unit spacing, `|` separator;
- evidence-backed rate and unsupported-claim rate — our existing strength.

If the 200-row file arrives, split **by manufacturer** (not randomly): `Part_Manuf` is
only 76 distinct values and product families cluster hard inside them, so a random split
would leak family patterns. Roughly 140 dev / 60 locked test, grouped.

---

## 8. Positioning

The proposed line is close but overclaims one word. "Enriched from manufacturer sources"
is aspirational until retrieval exists, and "Unilog-ready" is the real product promise.

Suggested instead:

> **SKUTruth turns messy distributor catalogue rows into Unilog-ready product content —
> canonical manufacturer and brand, the right classpath, attributes filled to Unilog's own
> template, and every important fact traceable to the manufacturer document it came from.**
>
> **AI proposes. SKUTruth verifies. Unilog's rules decide the final format.**

The second line is the strongest asset we have and should stay verbatim — it is
differentiating precisely because the codebase already implements it.

---

## 9. Recommended next milestone

**Not** span verification (paused), and **not** the fuzzy matcher — the master list it
would match against is missing.

**Next: organizer-pack loaders + placeholder policy + delivery-schema contract.**

Rationale: it is the only substantial work that is *not blocked* by a missing file, it is
fully deterministic, and everything downstream needs it. Concretely — a reader for the two
CSVs; a placeholder policy covering `-- … --` **and** the undocumented `-`; a
`Part_Manuf → (name, code)` splitter; the 252-column delivery contract with its ordered
attribute-slot block; and a schema-conformance validator. All testable today against the
two real examples.

Then, in order, as files arrive: manufacturer/brand canonicalisation (needs file 7) →
classpath + LOV template (needs file 8) → UOM and fraction normalisation (needs files 5, 6)
→ description builders (needs file 4) → evaluation (needs file 3).

**The single most valuable thing to obtain is the missing 200-row labelled file.** Without
it there is no ground truth, and without files 4–8 the normalisation targets are unknown.
