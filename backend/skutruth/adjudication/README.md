# Adjudication and Unilog mapping

## VERIFIED IS NOT THE SAME AS SAFE TO PUBLISH

The verifier answers one question: *does the manufacturer evidence support this claim?*
That is necessary and it is not sufficient. `7.5 kW` is genuinely stated by the document,
genuinely located, genuinely about this exact reference — and writing it into a column
labelled `Power` still produces a wrong specification, because the document said 7.5 kW
**under AC-3 at 400 V, 50/60 Hz**.

So three questions are kept apart, and this package answers the second and third:

```
verification   does the evidence support this claim?          (frozen, upstream)
adjudication   is a supported claim safe to commit here?      ← this package
mapping        where and how should it appear in the record?  ← this package
```

Collapsing them is how a trustworthy pipeline quietly becomes an untrustworthy one.

## The bridge

```
VerificationOutcome ─┐
                     ├→ adjudicate ─→ resolve conflicts ─→ attribute slots ─→ DeliveryRecord
AttributeMappingSpec ┘
```

Everything else — manufacturer, brand, classpath, titles, descriptions, assets — is
untouched. Those need organizer rule data we do not have.

## Commit policy

A fact reaches an output cell only when all of these hold:

1. verification reached `EXACT_SPAN`;
2. its value is of a kind that can be represented (`numeric` or `alphanumeric`);
3. it belongs to the resolved exact product;
4. a mapping rule explicitly names its target;
5. any unit change is one the reviewed registry can perform;
6. applying the mapping does not discard the operating point;
7. no unresolved contest exists for that target.

Anything else is `WITHHOLD`, `REVIEW`, or `UNMAPPED` — never a quiet omission.

| Decision | Meaning |
|---|---|
| `COMMIT` | verified, mapped, safe; occupies a slot |
| `WITHHOLD` | must not populate any value |
| `REVIEW` | a person decides; visible, not discarded |
| `UNMAPPED` | verified, and no rule says where it goes — **not an error** |

`UNMAPPED` is deliberately its own state. "We believe this and have nowhere approved to
put it" is a different and more useful statement than either a failure or a silence.

## Mapping cannot upgrade verification

A future mapping may know that `screw clamp terminals` and `Screw connection` are the
same thing. It still cannot make that `UNVERIFIED` outcome committable here. Licensing a
controlled-vocabulary substitution is a separate deterministic stage backed by a
published synonym list; until it exists, `UNVERIFIED` means no commit, and this package
never reinterprets a verification failure — it carries it verbatim.

`AdjudicatedFact` holds the whole `VerificationOutcome`, which is frozen. This stage
structurally cannot rewrite a verification result.

## Conditions cannot vanish

Every condition policy either refuses conditions, matches them exactly, or keeps them.
There is no option that silently drops them.

| Policy | Behaviour |
|---|---|
| `REJECT_IF_CONDITIONED` | plain scalar target; any bound condition → review. The default |
| `TARGET_ENCODES_CONDITIONS` | the label names the operating point; the fact's conditions must match the declared set **exactly** |
| `PRESERVE_AS_METADATA` | conditions travel on the mapped attribute and the result, though not into the CSV cell |

`TARGET_ENCODES_CONDITIONS` must declare `required_conditions`, and a spec that declares
them under any other policy is rejected. Without that, "the label covers it" would be an
unfalsifiable claim — silent condition loss wearing a policy's clothing.

## Conflicts, and the difference that matters

| Values | Operating points | Outcome |
|---|---|---|
| same | same | merged; one attribute written, the rest recorded as merged |
| different | same | `CONFLICT` → review |
| same | different | `MULTIPLE_OPERATING_POINTS` → review |
| different | different | `MULTIPLE_OPERATING_POINTS` → review |

Rows three and four are the point. `18 A at AC-3` and `32 A at AC-1` do not disagree
about anything — they are two ratings of one device, and calling that a conflict is the
classic mistake. A single scalar cell cannot hold both either, so they go to review under
a reason that says which problem it actually is.

**Nothing is ever resolved by first-wins**, model order, or dictionary overwrite. Facts
merge only when identical; every other multiplicity becomes a reviewed outcome.

## Authority

`MappingAuthority` records where a rule came from: `OFFICIAL` (organizer-supplied),
`DEMO` (hand-written), `LOCAL` (operator). We hold **no** official Unilog LOV, UOM
master, or category attribute rules, so every rule in the repository today is `DEMO`, and
`AssemblyResult.authoritative_mapping` is `False`.

That flag is what stands between a demonstration and a compliance claim. SKUTruth can
write verified attributes into the official delivery schema through explicit mappings. It
cannot yet say those attributes are Unilog-compliant, and the code will not let a caller
pretend otherwise: `is_authoritative` is false if even one rule was hand-written.

Rules are data — TOML in `data/mappings/`, loaded by `load_registry`. The engine treats
`source_key` as opaque and never inspects it; a test parses the package and asserts no
ETIM identifier appears as a code literal. `EF000008 → Width` today,
`unilog:raw_width → Width` later, same engine.

## Slots

Order comes from mapping `priority`, never the alphabet and never the order the model
proposed facts in; target label breaks ties so runs are reproducible. Official category
sequences will set `priority` and plug straight in.

Capacity is a hard edge: more committed attributes than declared slots raises
`SlotCapacityError`. Truncating the tail would drop verified facts into a row that looks
complete — every slot it has would be full — and nothing downstream could detect it.

Unused slots are left untouched, so a declared-but-blank slot still means what
`unilog/delivery.py` says it means.

## Provenance survives

The 252-column contract has nowhere to put an artifact hash, a page number, the
document's own wording, or a verifier version, and inventing a column would break the one
instruction the organizer gave explicitly. So none of it is written to the CSV — and none
of it is lost. `MappedUnilogAttribute` carries all of it, and `AssemblyResult.provenance()`
renders it for a reviewer.

## Why not `ProductAttribute`

The frozen `ProductAttribute` is right for an ETIM golden record and wrong here, on four
counts that are structural rather than stylistic:

1. `etim_feature_id` is `^EF\d{6}$` — it cannot express an opaque or Unilog-shaped key;
2. `feature_type: EtimFeatureType` is mandatory, and a Unilog attribute has none;
3. `ACCEPTED` requires `licensing_evidence` built from `Evidence`/`EvidenceGroup`, a
   richer record than verification produces — synthesising them would mean inventing the
   provenance the contract exists to check;
4. its validator *requires* a derived `SupportGrade` on every accepted attribute. Grade
   depends on publisher authority and source policy, which this stage does not assess.
   Grading here would manufacture a grade out of `EXACT_SPAN` alone.

Hence a narrow `AdjudicatedFact` that reuses `AttributeValue`, `ConditionSet`, and
`VerificationOutcome` unchanged. **No support grade, no confidence, no probability** — a
test enforces it.

## Known limitations

* Only `numeric` and `alphanumeric` values are representable; ranges and logicals never
  reach `EXACT_SPAN` under the frozen verifier, so supporting them here would be dead
  code claiming a capability.
* Unit conversion is whatever the reviewed ETIM registry supports. No Unilog UOM rule is
  invented, because the UOM master is not in the pack.
* One rule per target label. A target legitimately fed by several sources needs a
  precedence concept, which needs organizer rules to define.
* No value formatting for Unilog conventions — mixed-inch fractions, closed-up invoice
  units, `|` separators. Those are description-building rules and are not implemented.
