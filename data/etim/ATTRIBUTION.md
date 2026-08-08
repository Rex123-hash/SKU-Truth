# ETIM 10.0 — attribution and licence

This directory contains a verbatim copy of:

- **File:** `ETIM-10.0-ALL-SECTORS-CSV-METRIC-EI-2024-12-05.zip`
- **SHA-256:** `9b2aa17f105315884661fe6a7a35f5fdbc8835d768a5906117cbc420420b6214`
- **Release:** ETIM 10.0, all sectors, CSV, metric, ETIM International master English
- **Retrieved:** 2026-08-09 from <https://www.etim-international.com/downloads/>

## Licence

The ETIM Classification Model ("ETIM Technical Information Model") and the ETIM MC
extension are published by ETIM International under the
**Open Data Commons Attribution Licence v1.0 (ODC-BY 1.0)**
— <https://opendatacommons.org/licenses/by/1-0/>.

ODC-BY 1.0 grants the right to share, create from, and adapt the database, provided the
source is attributed and licence notices are preserved. This file is that attribution.

> Contains information from the ETIM Classification Model, which is made available by
> ETIM International under the Open Data Commons Attribution Licence v1.0.

## What SKUTruth uses it for

- **Product class schema** — `ETIMARTCLASS` (5,641 classes), `ETIMARTGROUP` (160 groups)
- **Expected attributes per class** — `ETIMARTCLASSFEATUREMAP` (76,626 rows), typed
  `N`/`A`/`L`/`R` and bound to a unit. This is the denominator of our completeness metric
  and the driver of content-gap analysis.
- **Allowed values** — `ETIMARTCLASSFEATUREVALUEMAP` (201,285 rows). Used to constrain
  model output at the decoding layer, so a picklist attribute cannot be hallucinated.
- **Canonical units** — `ETIMUNIT` (189 units), for deterministic unit normalisation.
- **Class synonyms** — `ETIMARTCLASSSYNONYMMAP` (37,059 rows), for lexical class candidate
  generation without a model call.

The archive is committed unmodified. Nothing in this repository alters the ETIM model;
derived indexes are built at runtime into `build/` and are not redistributed.

## Note on national language versions

Only the master **ETIM English** model is used here, which requires no membership. Several
national language versions are member-restricted and are deliberately not included.
