# Table parser fallback — investigation and decision

Narrow engineering investigation prompted by a concrete failure on a real Schneider
document. Derived observations only; no Schneider bytes or whole tables are in this
repository.

- **Date:** 2026-08-16
- **Decision:** **A — selective fallback justified** (opt-in, additive)
- **Implementation:** [`backend/skutruth/ingest/tables.py`](../backend/skutruth/ingest/tables.py)

---

## 1. The failure being solved

Artifact A (TeSys Contactors catalogue extract), SHA-256
`ca5977404d8aef9e9b3c1fd6339b7039b3aede4536f635a105ea9d1212bb8fdd`,
**PDF page 4 / printed B8/2**.

pypdf preserves every character but destroys the column grouping. The header's ten
voltage labels are emitted across seven lines whose breaks do not fall on column
boundaries:

```
'220 V ' / '230 V' / '380 V' / '400 V' / '415 V 440 V 500 V 660 V ' / '690 V' / '1000 V'
```

against a units line of seven `kW` tokens and a body row of seven kW values. Reading each
label as its own column yields **`400 V -> 9 kW`**. Schneider's own LC1D18P7 data sheet
says **`380/400 V -> 7.5 kW`**.

This is not lost recall. It is a **semantic structure loss that produces a confidently
wrong attribute**, which is the one failure mode this project cannot tolerate. Hashes,
page maps, and span location all pass on that text — none of them can see that the column
semantics are gone.

---

## 2. Candidates and licences

Licence checked on PyPI metadata and again on the installed distribution.

| Candidate | Version | Licence | Outcome |
|---|---|---|---|
| **pdfplumber** | **0.11.10** | **MIT** (OSI classifier) | **adopted** |
| pdfminer.six (its backend) | 20260107 | MIT (`License-Expression`) | pulled in |
| pypdfium2 (its backend) | 5.13.0 | BSD-3-Clause / Apache-2.0 | pulled in |
| camelot-py | 2.0.0 | MIT | rejected — needs OpenCV + Ghostscript (itself AGPL) for lattice mode; disproportionate |
| PyMuPDF | 1.28.2 | **AGPL-3.0 or commercial** | **rejected** — copyleft, exactly the submission/IP risk to avoid |

No OCR, no cloud parser, no VLM. Everything is deterministic and local.

---

## 3. What was built

pypdf remains the default and only ingestion parser. Structured extraction is a **second
representation**, requested per page by a caller. `IngestedPage.raw_text` and its hash are
untouched, so `"the parser emitted this text"` stays distinguishable from `"the table
reconstructor placed these words in these cells"`.

The page draws its own column boundaries as vertical ruling lines, so those lines — not
whitespace — are the ground truth:

1. cluster vertical ruling edges into bands sharing a y-extent (a *rule frame*);
2. merge vertically adjacent bands, because a header's label row and unit row are ruled
   separately but form one table;
3. bin words into columns by midpoint and into rows by baseline;
4. project body rows down the same boundaries below the ruling, which is where catalogue
   data rows live unruled.

Versioned as `table-extract@v1` alongside the engine name and engine version, since a
parser upgrade can move a word into a different cell.

**Step 3 is done in our code rather than by handing explicit column lines back to
pdfplumber.** Doing the latter was tried first and pdfplumber *silently dropped a column*
on catalogue page 10 — the reference column, so rows lost their identity while still
looking well-formed. A silent column drop is the same class of defect this module exists
to prevent, so the binning is kept inspectable.

### Failure semantics

| Situation | Result |
|---|---|
| No vertical ruling on the page | `NO_TABLE_STRUCTURE` |
| Ruling present, no usable rows | `TABLE_STRUCTURE_UNRESOLVED` |
| Reconstructed | `TABLES_EXTRACTED` |

Nothing is inferred from whitespace. A page that *looks* columnar but draws no rules
returns `NO_TABLE_STRUCTURE` — withholding beats `400 V -> 9 kW`.

---

## 4. Real-page result

Extraction ran on catalogue page 4 **alone**. The LC1D18P7 data sheet was consulted only
afterwards, as an independent check — never to guide reconstruction, and no per-reference
rule was hard-coded.

Recovered column headers, with the LC1D18 row projected onto them:

| Column | 0 | 1 | 2 | 3 | 4 | 5 | 6 | (A) |
|---|---|---|---|---|---|---|---|---|
| Header | 220/230 V | **380/400 V** | 415 V | 440 V | 500 V | 660/690 V | 1000 V | AC-3 ≤440 V |
| LC1D18 | 4 kW | **7.5 kW** | 9 kW | 9 kW | 10 kW | 10 kW | – | 18 A |

The grouping pypdf destroyed — `220/230` and `380/400` each being *one* column — is
recovered from the page's own ruling geometry.

### Independent validation

| Relationship | Data sheet (artifact B) | Catalogue (reconstructed) | |
|---|---|---|---|
| 220/230 V | 4 kW | 4 kW | MATCH |
| **380/400 V** | **7.5 kW** | **7.5 kW** | **MATCH** |
| 415/440 V | 9 kW | 9 kW (split into two columns, both 9) | MATCH |
| 500 V | 10 kW | 10 kW | MATCH |
| 660/690 V | 10 kW | 10 kW | MATCH |
| AC-3 ≤440 V | 18 A | 18 A | MATCH |

Every value agrees. The specific error the naive read produced (`400 V -> 9 kW`) is gone.

---

## 5. Control pages

| Page | Case | Result |
|---|---|---|
| cat p4 [B8/2] AC-3 | target | **GOOD** — validated above |
| cat p6 [B8/4] AC-1 | GOOD under pypdf | **GOOD** — `32 \| 3 \| 1 \| 1 \| LC1D18pp \| 0.330` |
| cat p6 voltage-code table | GOOD under pypdf | **GOOD** — volts and codes land in matching columns, so `230 ↔ P7` is a column alignment rather than the index-position coincidence pypdf leaves |
| cat p10 [B8/8] HP/NEMA | DEGRADED under pypdf | **GOOD** — reference recovered |
| cat p15 [B8/13] Green | DEGRADED under pypdf | **GOOD** — `LC1D18ppp` row recovered |
| LC1D18P7 data sheet p1 | GOOD under pypdf | **`NO_TABLE_STRUCTURE`** — correctly abstains; label/value text is unruled, and pypdf already handles it |

No control case regressed: `raw_text` is untouched everywhere, and the one page where
reconstruction has nothing to work with reports that instead of inventing cells.

---

## 6. Limitations

- **Ruling-dependent by design.** A table drawn without vertical rules is invisible to
  this module. That is deliberate — the alternative is inferring columns from whitespace,
  which is what produced the original wrong answer.
- **Header labels are not named.** Header rows are emitted verbatim and never collapsed
  into one label per column. A catalogue header band also contains title text shredded
  across columns, so *which* header row carries the column labels is not deterministically
  derivable and is left to the caller.
- **Header/body boundary can bleed.** Where a frame's ruling extends past the first data
  row, that row is reported as a header row. Harmless while header rows are raw, but it
  means `header_row_count` is a layout fact, not a semantic one.
- **Spurious frames.** A page yields several frames, some of which are page furniture. The
  caller selects; frames are not ranked.
- **Validated on one document.** Six pages of one catalogue plus one data sheet. The
  geometry assumption (columns are ruled) is a property of this publisher's layout, not a
  law.
- **No automatic trigger.** There is no malformed-table detector, and inventing an
  unreliable one would be worse than asking. Extraction is opt-in per page, which §9 of
  the brief explicitly permits for P0.

---

## 7. Not claimed

Locating a cell is infrastructure for the span verifier, not verification. This milestone
sets no `EXACT_SPAN`, no `FUZZY_OCR_SPAN`, and no `proves_family_scope`, and builds no
`ProductAttribute`. The identity findings in
[`lc1d18_artifact_note.md`](lc1d18_artifact_note.md) are unchanged.

The `SourceType` gap for manufacturer catalogues remains open and unpatched; artifact A
still carries `source_type=null`. Nothing in this milestone needed that field.

---

## 8. Decision

**A — selective fallback justified.**

It recovers the exact relationship that motivated the investigation, validated against an
independent official document; it improves three further catalogue pages; it regresses
nothing, because it is additive and `raw_text` is untouched; it abstains explicitly where
it has nothing to work with; and it is deterministic, local, and MIT-licensed.

It is wired in as an opt-in call, **not** into the ingestion path.
