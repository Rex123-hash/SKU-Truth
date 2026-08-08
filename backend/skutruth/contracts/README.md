# Frozen data contracts

These types are the interface between every pipeline stage, the API, the frontend, and the
evaluation harness. **Components adapt to the contract. The contract does not adapt to
components.**

## Change policy

| Change | Allowed? |
|---|---|
| Adding an optional field | Yes |
| Adding an enum member | Yes |
| Adding a validator that tightens an existing invariant | Yes, with a test |
| Renaming or removing a field | Only with an explicit decision recorded in `docs/decisions/` |
| Loosening an invariant below because a stage found it inconvenient | **No.** Fix the stage. |

## Invariants the contract enforces, and why

These are enforced by Pydantic validators, not by convention, so a stage physically cannot
emit a record that breaks them.

1. **No committed value without evidence.** `ProductAttribute` with a non-null `value` must
   carry at least one `EvidenceCluster`. This is the central promise of the system: we do not
   ask a model to invent product information, we make it construct product information from
   evidence.

2. **Abstention carries no value.** `INSUFFICIENT_EVIDENCE` and `VARIANT_DEPENDENT` must have
   `value is None`, and every other status must have a value. There is no half-abstention.

3. **`VERIFIED` requires ≥2 *independent* evidence clusters.** Clusters, not URLs. Three
   distributors that copied one manufacturer datasheet collapse into one cluster and therefore
   yield `SINGLE_SOURCE`, not `VERIFIED`. Counting copies as corroboration is how a
   provenance system manufactures false confidence, and the type system refuses to let us.

4. **A `FAMILY` identity must declare how its members differ.** A `ProductIdentity` of kind
   `FAMILY` with no `variant_axes` and no `candidate_mpns` is indistinguishable from an
   `EXACT_SKU` and is rejected. This keeps family detection honest.

5. **ETIM range values satisfy min ≤ max.** Definitional, not physical — an ETIM `R` feature
   with min > max is malformed by construction.

## What confidence means here

`ProductAttribute.confidence` is computed by deterministic code from
`ConfidenceFactors`, which are measurable properties of the evidence. **No language model
emits a confidence number anywhere in this system.**

`ConfidenceFactors.calibrated` records whether the aggregate was mapped through a calibration
curve fitted on held-out data. While it is `False`, the number is an **uncalibrated ordinal
score** — useful for ranking and routing, not interpretable as a probability — and the UI and
documentation say exactly that. We only claim calibrated confidence once the held-out
evaluation set is large enough for the result to be defensible.

## What `run_mode` means here

`GoldenRecord.run_mode` is `LIVE` or `REPLAY`. A `REPLAY` run replays network and model
interactions that were really made and recorded earlier; it is not synthetic data and it is
not a fresh live run. Both statements are surfaced verbatim in the UI. Presenting a replayed
run as a live one is a correctness bug, not a presentation choice.
