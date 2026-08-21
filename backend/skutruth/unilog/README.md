# Unilog adapter

The deterministic boundary between the organizer's files and the rest of SKUTruth.

```
raw organizer CSV → safe parse → placeholder cleaning → Part_Manuf parsing
                                                              ↓
                                                       RawProductRow
                                                              ↓
                          deterministic manufacturer/brand normalization
                       (injected authorities; unknowns stay review/withhold)
                                                              ↓
                         deterministic internal product family
                    (lexical cues; separate scoped taxonomy authority)
                                                              ↓
                            DeliverySchema (252 ordered headers, runtime-derived)
                                                              ↓
                                          DeliveryRecord → exact-order CSV export
```

**No AI, fuzzy matching, or content generation.** Internal family classification uses
inspectable lexical rules. Organizer delivery classification remains authority-gated;
see [Deliberately absent](#deliberately-absent).

## Raw and cleaned are both kept

`RawProductRow.raw` is exactly what the file said. The cleaned accessors
(`.e1_brand`, `.part_manuf`, …) trim whitespace and turn placeholders into `None`.

Both are kept because *"the source wrote `-- Unbranded --`"* and *"the source wrote
nothing"* are different facts. Only the raw form can tell a reviewer which happened, and
the delivery file's own passthrough block echoes the placeholder back — so cleaning at the
boundary would disagree with the organizer's own output.

## Placeholder semantics

A placeholder means **the field is empty**, not that the product is unbranded. Two rules,
deliberately different in scope:

| Form | Recognised in | Why |
|---|---|---|
| `-- … --` | any field | A distinctive sentinel; no real catalogue value looks like this |
| bare `-` | **only** `Part_Manuf` | Observed there on 41/1,000 rows. A lone hyphen is legitimate in a part number, a size range, or a description |

`is_placeholder(field_name, value)` is field-aware for exactly this reason. Turning every
`-` into `None` globally would silently destroy real data. Empty and whitespace-only
values are *not* placeholders — they are simply empty, and the distinction is preserved.

## Manufacturer parsing

`Part_Manuf` arrives as `Kichler Lighting (KICLI)` — a name with a supplier code appended.
Splitting that is pure structure, and it yields a code needing no matching at all.

Five outcomes, because "could not parse" is not one thing:

| Status | Meaning |
|---|---|
| `NAME_WITH_CODE` | both recovered |
| `NAME_ONLY` | usable name, no identifiable code — not a failure |
| `PLACEHOLDER` | documented placeholder; no manufacturer |
| `MISSING` | blank |
| `UNRESOLVED` | malformed: unbalanced or reversed parens, empty code, code with no name |

**Nothing is canonicalised here.** `Phillips Lighting` stays `Phillips Lighting`;
`Black & Decker/dewlt` stays as written. Both look like misspellings of real
manufacturers, but the approved manufacturer master is not in the pack, and a correction
we cannot check against the approved list is a guess wearing a rule's clothing. Codes are
preserved verbatim, and their length is not constrained — 4 and 5 characters is an
observation about one sample, not a contract.

## Manufacturer and brand normalization foundation

`DeterministicNormalizer` keeps raw `E1_Brand`, `Unilog_Brand`, `DIB_Brand`, and
`Part_Manuf` signals in every audit result. It emits a canonical proposal, decision,
reason, authority level, and authority source. No authority level is called official:
the organizer manufacturer/brand master is still absent.

Canonical rules are injected. Case, whitespace, punctuation, and legal-suffix folding
may select an existing authorized rule; they never create one. Exact alias collisions
remain `REVIEW`, unknown manufacturers remain `REVIEW`, malformed/placeholder inputs are
`WITHHOLD`, and no edit-distance or model match exists. Independent brand fields that
agree after case/punctuation folding may commit as `DATASET_CONSENSUS`; one brand signal
alone remains review unless an injected authority covers it.

`reviewed_manufacturer_catalog()` adapts only licensing entries and authority hints from
the human-reviewed manufacturer-domain registry. Locator hints are excluded. That review
supports the manufacturer-name/domain binding only; it does not prove an MPN, product
identity, brand, description, or attribute.

## Internal family is not delivery classpath

`DeterministicProductClassifier` assigns coarse SKUTruth routing families from exact
tokens and phrases in `Part_Desc`. Manufacturer and brand values travel as context but
are never sufficient classification evidence. Unrelated family overlaps become
`REVIEW`; no cue becomes `UNKNOWN`/`WITHHOLD`. The only precedence rules are documented
product hierarchies: `DISHWASHER` over general `APPLIANCE`, and a named accessory such as
`saw blade` over the `saw` it fits.

These are internal analytical families, not Unilog values. The organizer output has
`Dept`, `Class`, `Fine`, `Classpath`, and `UNSPSC`, while the input supplies none of them.
The two output rows are represented as exact six-passthrough-field example rules. Their
classification values may be replayed only onto those exact rows; another dishwasher
does not inherit them. ETIM remains an internal reference and cannot populate organizer
delivery classification.

## The delivery schema is derived at runtime

The 252 header names are **not** checked into this repository. The organizer pack carries
no stated redistribution grant, and while a list of column *names* is far less sensitive
than data rows, "probably fine" is not a licence. `DeliverySchema.from_csv()` reads the
contract from the local file instead.

That also buys a real property: `fingerprint()` — SHA-256 over the ordered header names —
detects the organizer quietly changing the expected format, which a checked-in copy would
instead silently disagree with. Row *values* are deliberately not hashed; the schema is
the contract, and hashing data would move the fingerprint for the wrong reason.

Tests build synthetic schemas and never read the organizer pack.

## Exact headers, exact order

The portal says *"Please do not change or modify the headers."* So the header sequence is
immutable: never sorted, never renamed, never reordered for tidiness. `to_row()` emits
values in schema order regardless of assignment order, and unassigned fields export as
`""` — never `None`, never the literal `"None"`. Unicode survives, so `FRIGIDAIRE®` and
`CleanBoost™` round-trip intact.

`groups()` buckets headers for analysis only; membership never affects export order.

## Attribute slots

The schema declares repeating `ATTRIBUTE_LABEL n` / `VALUE n` / `UOM n` triplets. The
count is **discovered**, not assumed — the sample has 50, but a template with a different
depth must load without a code change. A triplet missing one member makes the schema
invalid: a label with nowhere to put its value is a broken contract.

**Blank is not absent.** The worked examples emit labels whose values are empty (`Model`,
`Plug Type`). That is meaningful — the classpath template says the attribute applies and
the source did not establish it. So slots are never compacted, and `AttributeSlot`
separates `is_declared` (has a label) from `has_value`. Dropping blank slots would destroy
the difference between *not applicable* and *not found*.

## Passthrough is conservative

Only input columns whose delivery header is **byte-identical** are carried across:
`Mfg_Part_Num`, `Part_Desc`, `E1_Brand`, `Unilog_Brand`, `DIB_Brand`, `Part_Manuf`.

`PART_NUMBER` and `MANUFACTURER_PART_NUMBER` are **not** populated. Their names merely
*look* like `Mfg_Part_Num`, and two examples do not prove the mapping.
`MANUFACTURER_NAME` and `BRAND_NAME` remain blank by default. When a caller supplies a
`RowNormalization`, only `COMMIT` values with delivery-eligible authority are mapped into
those two exact identity fields. Classification fields remain blank unless a supplied
`ClassificationProposal` carries record-scoped organizer-example, organizer-LOV, or
human-approved authority. Every description stays empty.

## Deliberately absent

| Not implemented | Blocked on |
|---|---|
| Organizer-official manufacturer/brand LOV conformance | `UniCat_Manufacturer_and_Brand_List.xlsx` |
| Organizer-wide classpath LOV mapping | `Unicat_Lov_v1_0_….xlsx` |
| UOM normalisation | `Unilog_Master_UOM_Standards_….xlsx` |
| Decimal↔fraction conversion | `Decimal_Fraction.xlsx` |
| Title / description construction | `UNILOG_INTERNAL_CONTENT_GUIDELINES.docx` |
| Field-level accuracy scoring | the 200-row labelled file |

The two worked examples suggest formatting conventions — invoice descriptions in caps
under 40 characters, mixed-inch fractions, a space between number and unit, `|` as a
multi-value separator. **These are recorded as observations in `research/`, not
implemented as rules.** Two rows is not enough to elevate a pattern into a contract, and
the guideline document that would confirm them is not in the pack.

Likewise, the 15 attribute labels shared by both examples are **not** hard-coded as a
dishwasher template. This package reads slot labels off records; it does not define
category semantics. The LOV is the authoritative source for that when it arrives.

## Organizer files stay local

The pack lives in `data/unilog_source/`, which is gitignored. No organizer row, header
list, or export is committed. A test asserts the directory stays ignored and that no
committed test names an organizer file.
