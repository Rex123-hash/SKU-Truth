"""Adjudication: deciding whether a verified fact is safe to commit, and where.

Everything here is synthetic. No organizer file, no manufacturer document, no model.

The load-bearing tests are the refusals. Committing a verified value is easy; the
milestone is only worth anything if a verified value that would lose its operating
point, or contradict a sibling, or need a conversion nobody can justify, reliably
fails to reach the record.
"""

from __future__ import annotations

import pytest
from skutruth.adjudication import (
    AdjudicatedFact,
    AdjudicationDecision,
    AdjudicationReason,
    AssemblySummary,
    AttributeMappingSpec,
    ConditionPolicy,
    MalformedMappingError,
    MappedUnilogAttribute,
    MappingAuthority,
    MappingRegistry,
    SlotCapacityError,
    adjudicate_one,
    assemble_verified_attributes,
    load_registry,
    parse_registry,
    resolve_conflicts,
)
from skutruth.contracts import (
    AlphanumericValue,
    Condition,
    ConditionKind,
    ConditionSet,
    EvidenceVerification,
    IdentityScope,
    NumericValue,
    ProductInput,
    RangeValue,
)
from skutruth.identity import (
    EvidenceAnchor,
    ExactReferenceFact,
    IdentityEvidence,
    ReferenceCompletionFact,
    resolve_identity,
)
from skutruth.unilog.schema import DeliverySchema
from skutruth.verification import (
    VERIFIER_VERSION,
    EvidenceMode,
    EvidenceUnit,
    TextMatchMode,
    VerificationFailure,
    VerificationOutcome,
)

MPN = "BASE100X1"
BRAND = "TestCo"
SHA = "a" * 64


def conditions(*pairs) -> ConditionSet:
    return ConditionSet(conditions=tuple(Condition(kind=k, value=v) for k, v in pairs))


def verified(
    key: str = "SRC001",
    *,
    value=None,
    conds: ConditionSet | None = None,
    page: int = 2,
    mpn: str = MPN,
    text: str = "18 A stated here",
) -> VerificationOutcome:
    """A `VerificationOutcome` as the frozen verifier would emit it."""
    return VerificationOutcome(
        key=key,
        exact_mpn=mpn,
        value=value if value is not None else NumericValue(number=18.0, unit="A", raw="18 A"),
        conditions=conds if conds is not None else ConditionSet(),
        artifact_sha256=SHA,
        page_number=page,
        status=EvidenceVerification.EXACT_SPAN,
        evidence_mode=EvidenceMode.TEXT_UNIT,
        match_mode=TextMatchMode.LITERAL,
        proposed_fragment="18 A",
        matched_text="18 A",
        evidence=EvidenceUnit(mode=EvidenceMode.TEXT_UNIT, text=text, start=0, end=len(text)),
        verifier_version=VERIFIER_VERSION,
    )


def unverified(
    key: str = "SRC001", failure: VerificationFailure = VerificationFailure.OPERATOR_MISMATCH
) -> VerificationOutcome:
    return VerificationOutcome(
        key=key,
        exact_mpn=MPN,
        value=NumericValue(number=18.0, unit="A", raw="18 A"),
        conditions=ConditionSet(),
        artifact_sha256=SHA,
        page_number=2,
        status=EvidenceVerification.UNVERIFIED,
        failure=failure,
        failure_detail="source states '<= 440 V' (LE)",
        proposed_fragment="18 A",
        verifier_version=VERIFIER_VERSION,
    )


def spec(
    source_key: str = "SRC001",
    target_label: str = "Amperage Rating",
    *,
    priority: int = 10,
    target_uom: str | None = None,
    expected_value_kind: str | None = None,
    condition_policy: ConditionPolicy = ConditionPolicy.REJECT_IF_CONDITIONED,
    required_conditions: ConditionSet | None = None,
    authority: MappingAuthority = MappingAuthority.DEMO,
) -> AttributeMappingSpec:
    return AttributeMappingSpec(
        source_key=source_key,
        target_label=target_label,
        authority=authority,
        priority=priority,
        target_uom=target_uom,
        expected_value_kind=expected_value_kind,
        condition_policy=condition_policy,
        required_conditions=required_conditions or ConditionSet(),
    )


def registry(*specs: AttributeMappingSpec, name: str = "test-demo") -> MappingRegistry:
    return MappingRegistry(specs or (spec(),), name=name)


def schema(slots: int = 4) -> DeliverySchema:
    headers = ["Mfg_Part_Num", "Part_Desc"]
    for index in range(1, slots + 1):
        headers += [
            f"ATTRIBUTE_LABEL {index}",
            f"ATTRIBUTE_VALUE {index}",
            f"ATTRIBUTE_UOM {index}",
        ]
    return DeliverySchema(headers)


def exact_identity(mpn: str = MPN):
    anchor = EvidenceAnchor(
        artifact_sha256=SHA, identity_scope=IdentityScope.EXACT_SKU, observed_statement="exists"
    )
    return resolve_identity(
        ProductInput(brand=BRAND, mpn=mpn, description="x"),
        IdentityEvidence(
            exact_facts=(ExactReferenceFact(brand=BRAND, exact_mpn=mpn, anchor=anchor),)
        ),
    )


class TestCommitPolicy:
    def test_verified_and_mapped_commits(self):
        """A."""
        fact = adjudicate_one(verified(), registry())
        assert fact.decision is AdjudicationDecision.COMMIT
        assert fact.reason is AdjudicationReason.ELIGIBLE
        assert fact.value is not None

    def test_unverified_is_withheld_even_with_a_mapping(self):
        """B."""
        fact = adjudicate_one(unverified(), registry())
        assert fact.decision is AdjudicationDecision.WITHHOLD
        assert fact.reason is AdjudicationReason.VERIFICATION_FAILED
        assert fact.value is None

    def test_verified_without_a_mapping_is_unmapped_not_an_error(self):
        """C."""
        fact = adjudicate_one(verified(key="SRC999"), registry())
        assert fact.decision is AdjudicationDecision.UNMAPPED
        assert fact.reason is AdjudicationReason.NO_MAPPING
        assert fact.is_verified is True

    def test_a_mapping_cannot_upgrade_an_unverified_fact(self):
        """D. The synonym case: a correct mapping is still not a located span."""
        outcome = unverified(failure=VerificationFailure.VALUE_NOT_SUPPORTED)
        fact = adjudicate_one(
            outcome, registry(spec(target_label="Type of Electrical Connection"))
        )
        assert fact.decision is AdjudicationDecision.WITHHOLD
        assert fact.outcome.failure is VerificationFailure.VALUE_NOT_SUPPORTED
        assert fact.outcome.status is EvidenceVerification.UNVERIFIED

    @pytest.mark.parametrize(
        "failure",
        [
            VerificationFailure.OPERATOR_MISMATCH,
            VerificationFailure.VALUE_NOT_SUPPORTED,
            VerificationFailure.UNSUPPORTED_VALUE_KIND,
            VerificationFailure.PRODUCT_SCOPE_NOT_SUPPORTED,
        ],
    )
    def test_every_verification_failure_is_carried_not_reinterpreted(self, failure):
        fact = adjudicate_one(unverified(failure=failure), registry())
        assert fact.outcome.failure is failure
        assert fact.reason is AdjudicationReason.VERIFICATION_FAILED

    def test_non_exact_identity_blocks_everything(self):
        anchor = EvidenceAnchor(
            artifact_sha256=SHA, identity_scope=IdentityScope.RANGE, observed_statement="base"
        )
        family = resolve_identity(
            ProductInput(brand=BRAND, mpn="BASE100", description="x"),
            IdentityEvidence(
                completion_facts=(
                    ReferenceCompletionFact(
                        brand=BRAND,
                        base_mpn="BASE100",
                        discriminator_key="control_circuit",
                        anchor=anchor,
                    ),
                )
            ),
        )
        fact = adjudicate_one(verified(), registry(), identity=family)
        assert fact.reason is AdjudicationReason.IDENTITY_NOT_EXACT

    def test_identity_for_a_different_reference_blocks_commit(self):
        fact = adjudicate_one(verified(), registry(), identity=exact_identity("BASE100Y2"))
        assert fact.reason is AdjudicationReason.IDENTITY_NOT_EXACT

    def test_matching_identity_permits_commit(self):
        fact = adjudicate_one(verified(), registry(), identity=exact_identity())
        assert fact.decision is AdjudicationDecision.COMMIT


class TestValueNormalisation:
    def test_compatible_unit_converts_with_lineage(self):
        """E. Reuses the reviewed registry; no Unilog unit rule is invented."""
        outcome = verified(value=NumericValue(number=18000.0, unit="mA", raw="18000 mA"))
        fact = adjudicate_one(outcome, registry(spec(target_uom="A")))
        assert fact.decision is AdjudicationDecision.COMMIT
        assert fact.value.number == pytest.approx(18.0)
        assert fact.value.unit == "A"
        assert fact.value.derivation.transform_id == "unit_conversion@v1"
        # The original is untouched, so provenance still points at what was verified.
        assert fact.outcome.value.number == 18000.0

    def test_incompatible_target_unit_goes_to_review(self):
        """F. Never guessed at."""
        fact = adjudicate_one(verified(), registry(spec(target_uom="V")))
        assert fact.decision is AdjudicationDecision.REVIEW
        assert fact.reason is AdjudicationReason.UNIT_INCOMPATIBLE

    def test_unknown_target_unit_goes_to_review(self):
        fact = adjudicate_one(verified(), registry(spec(target_uom="furlong")))
        assert fact.reason is AdjudicationReason.UNIT_INCOMPATIBLE

    def test_alphanumeric_value_maps_verbatim(self):
        """G. No synonym licensing, no casing games."""
        outcome = verified(value=AlphanumericValue(text="AC", raw="AC"))
        fact = adjudicate_one(
            outcome, registry(spec(expected_value_kind="alphanumeric", target_label="Voltage Type"))
        )
        assert fact.decision is AdjudicationDecision.COMMIT
        assert fact.value.text == "AC"

    def test_value_kind_mismatch_goes_to_review(self):
        outcome = verified(value=AlphanumericValue(text="AC", raw="AC"))
        fact = adjudicate_one(outcome, registry(spec(expected_value_kind="numeric")))
        assert fact.reason is AdjudicationReason.VALUE_KIND_MISMATCH

    def test_unrepresentable_value_kind_goes_to_review(self):
        """Ranges never reach EXACT_SPAN today; if one arrived it would not be guessed at."""
        outcome = verified(
            value=RangeValue(minimum=100.0, maximum=250.0, unit="V", raw="100-250 V")
        )
        fact = adjudicate_one(outcome, registry())
        assert fact.reason is AdjudicationReason.VALUE_KIND_MISMATCH
        assert fact.decision is AdjudicationDecision.REVIEW


class TestConditionPreservation:
    def test_conditions_are_retained_on_the_adjudicated_fact(self):
        """H."""
        conds = conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))
        fact = adjudicate_one(
            verified(conds=conds),
            registry(spec(condition_policy=ConditionPolicy.PRESERVE_AS_METADATA)),
        )
        assert fact.decision is AdjudicationDecision.COMMIT
        assert fact.conditions.key() == conds.key()

    def test_a_scalar_target_refuses_a_conditioned_fact(self):
        """I. The whole point: 7.5 kW is not 'Power', it is power under AC-3 at 400 V."""
        conds = conditions(
            (ConditionKind.UTILIZATION_CATEGORY, "AC-3"), (ConditionKind.VOLTAGE, "400 V")
        )
        fact = adjudicate_one(
            verified(value=NumericValue(number=7.5, unit="kW", raw="7.5 kW"), conds=conds),
            registry(spec(target_label="Power")),
        )
        assert fact.decision is AdjudicationDecision.REVIEW
        assert fact.reason is AdjudicationReason.CONDITION_LOSS
        assert fact.value is None

    def test_a_label_that_encodes_the_operating_point_may_commit(self):
        """J."""
        conds = conditions(
            (ConditionKind.UTILIZATION_CATEGORY, "AC-3"), (ConditionKind.VOLTAGE, "400 V")
        )
        fact = adjudicate_one(
            verified(value=NumericValue(number=7.5, unit="kW", raw="7.5 kW"), conds=conds),
            registry(
                spec(
                    target_label="Rated Operational Power at AC-3, 400 V",
                    condition_policy=ConditionPolicy.TARGET_ENCODES_CONDITIONS,
                    required_conditions=conds,
                )
            ),
        )
        assert fact.decision is AdjudicationDecision.COMMIT

    def test_an_encoded_label_refuses_a_different_operating_point(self):
        """The exact-set match is what makes the policy checkable rather than a promise."""
        declared = conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))
        actual = conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-1"))
        fact = adjudicate_one(
            verified(conds=actual),
            registry(
                spec(
                    condition_policy=ConditionPolicy.TARGET_ENCODES_CONDITIONS,
                    required_conditions=declared,
                )
            ),
        )
        assert fact.reason is AdjudicationReason.CONDITION_LOSS

    def test_an_encoded_label_refuses_a_superset_of_its_conditions(self):
        declared = conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))
        actual = conditions(
            (ConditionKind.UTILIZATION_CATEGORY, "AC-3"), (ConditionKind.VOLTAGE, "400 V")
        )
        fact = adjudicate_one(
            verified(conds=actual),
            registry(
                spec(
                    condition_policy=ConditionPolicy.TARGET_ENCODES_CONDITIONS,
                    required_conditions=declared,
                )
            ),
        )
        assert fact.reason is AdjudicationReason.CONDITION_LOSS

    def test_preserved_conditions_reach_the_mapped_attribute(self):
        conds = conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))
        result = assemble_verified_attributes(
            [verified(conds=conds)],
            registry(spec(condition_policy=ConditionPolicy.PRESERVE_AS_METADATA)),
            schema(),
        )
        assert result.attributes[0].conditions.key() == conds.key()


class TestConflicts:
    def _shared_target(self):
        """One rule, reached by several verified facts.

        Two *rules* for one target are refused at authoring time, so a runtime contest
        arises the other way: one source key yielding more than one verified fact — the
        same feature read on two pages, or under two operating points.
        """
        return spec(
            "SRC001", "Amperage Rating", condition_policy=ConditionPolicy.PRESERVE_AS_METADATA
        )

    def _facts(self, outcomes):
        rules = registry(self._shared_target())
        return resolve_conflicts([adjudicate_one(o, rules) for o in outcomes])

    def test_identical_facts_deduplicate(self):
        """K."""
        value = NumericValue(number=18.0, unit="A", raw="18 A")
        facts = self._facts([verified(value=value), verified(value=value)])
        committed = [f for f in facts if f.decision is AdjudicationDecision.COMMIT]
        merged = [f for f in facts if f.reason is AdjudicationReason.DUPLICATE_MERGED]
        assert len(committed) == 1
        assert len(merged) == 1
        assert committed[0].merged_source_keys == ("SRC001",)

    def test_different_values_under_the_same_conditions_conflict(self):
        """L."""
        facts = self._facts(
            [
                verified(value=NumericValue(number=18.0, unit="A", raw="18 A")),
                verified(value=NumericValue(number=32.0, unit="A", raw="32 A")),
            ]
        )
        assert all(f.decision is AdjudicationDecision.REVIEW for f in facts)
        assert all(f.reason is AdjudicationReason.CONFLICT for f in facts)

    def test_same_value_under_different_conditions_is_not_a_conflict(self):
        """M."""
        value = NumericValue(number=18.0, unit="A", raw="18 A")
        ac3 = conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3"))
        ac1 = conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-1"))
        facts = self._facts(
            [verified(value=value, conds=ac3), verified(value=value, conds=ac1)]
        )
        assert all(f.reason is AdjudicationReason.MULTIPLE_OPERATING_POINTS for f in facts)
        assert all(f.reason is not AdjudicationReason.CONFLICT for f in facts)

    def test_different_values_under_different_conditions_are_not_a_factual_conflict(self):
        """N. 18 A at AC-3 and 32 A at AC-1 are two ratings, not a disagreement."""
        facts = self._facts(
            [
                verified(
                    value=NumericValue(number=18.0, unit="A", raw="18 A"),
                    conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-3")),
                ),
                verified(
                    value=NumericValue(number=32.0, unit="A", raw="32 A"),
                    conds=conditions((ConditionKind.UTILIZATION_CATEGORY, "AC-1")),
                ),
            ]
        )
        assert all(f.reason is AdjudicationReason.MULTIPLE_OPERATING_POINTS for f in facts)
        assert all(f.decision is AdjudicationDecision.REVIEW for f in facts)

    def test_no_contested_fact_is_ever_silently_chosen(self):
        """No first-wins, no last-wins, no dictionary overwrite."""
        facts = self._facts(
            [
                verified(value=NumericValue(number=18.0, unit="A", raw="18 A")),
                verified(value=NumericValue(number=32.0, unit="A", raw="32 A")),
            ]
        )
        assert not [f for f in facts if f.decision is AdjudicationDecision.COMMIT]

    def test_conflicts_are_counted_in_the_summary(self):
        rules = registry(self._shared_target())
        result = assemble_verified_attributes(
            [
                verified(value=NumericValue(number=18.0, unit="A", raw="18 A")),
                verified(value=NumericValue(number=32.0, unit="A", raw="32 A")),
            ],
            rules,
            schema(),
        )
        assert result.summary.conflicts == 1
        assert result.summary.attributes_written == 0


class TestSlotAssembly:
    def _three(self):
        outcomes = [verified(key=f"SRC{n:03d}") for n in (1, 2, 3)]
        rules = registry(
            spec("SRC001", "Zulu", priority=30),
            spec("SRC002", "Alpha", priority=20),
            spec("SRC003", "Mike", priority=10),
        )
        return outcomes, rules

    def test_priority_controls_slot_order(self):
        """O."""
        outcomes, rules = self._three()
        result = assemble_verified_attributes(outcomes, rules, schema())
        assert [a.label for a in result.attributes] == ["Mike", "Alpha", "Zulu"]

    def test_alphabetical_order_does_not_override_priority(self):
        """P."""
        outcomes, rules = self._three()
        result = assemble_verified_attributes(outcomes, rules, schema())
        labels = [a.label for a in result.attributes]
        assert labels != sorted(labels)

    def test_equal_priority_is_still_deterministic(self):
        outcomes = [verified(key="SRC001"), verified(key="SRC002")]
        rules = registry(
            spec("SRC001", "Zulu", priority=10), spec("SRC002", "Alpha", priority=10)
        )
        first = assemble_verified_attributes(outcomes, rules, schema())
        second = assemble_verified_attributes(list(reversed(outcomes)), rules, schema())
        assert [a.label for a in first.attributes] == [a.label for a in second.attributes]

    def test_triplets_stay_aligned(self):
        """Q."""
        outcomes, rules = self._three()
        result = assemble_verified_attributes(outcomes, rules, schema())
        slots = result.record.declared_attribute_slots()
        assert [(s.index, s.label) for s in slots] == [(1, "Mike"), (2, "Alpha"), (3, "Zulu")]
        assert all(s.value == "18" and s.uom == "A" for s in slots)

    def test_unused_slots_remain_blank(self):
        """R."""
        outcomes, rules = self._three()
        result = assemble_verified_attributes(outcomes, rules, schema(slots=8))
        blank = [s for s in result.record.attribute_slots() if not s.is_declared]
        assert len(blank) == 5
        assert all(not s.value and not s.uom for s in blank)

    def test_slot_overflow_fails_explicitly(self):
        """S. Never truncated: a full row would look complete."""
        outcomes = [verified(key=f"SRC{n:03d}") for n in range(1, 6)]
        rules = registry(*[spec(f"SRC{n:03d}", f"Attr {n}", priority=n) for n in range(1, 6)])
        with pytest.raises(SlotCapacityError, match="Refusing to truncate"):
            assemble_verified_attributes(outcomes, rules, schema(slots=3))

    def test_only_attribute_fields_are_touched(self):
        outcomes, rules = self._three()
        result = assemble_verified_attributes(outcomes, rules, schema())
        assert all(f.startswith("ATTRIBUTE_") for f in result.record.assigned_fields)


class TestMappingValidation:
    """T. A malformed rule is caught where its author can still fix it."""

    def test_two_rules_for_one_source_key_are_rejected(self):
        with pytest.raises(MalformedMappingError, match="mapped twice"):
            registry(spec("SRC001", "Alpha"), spec("SRC001", "Beta"))

    def test_two_rules_for_one_target_are_rejected(self):
        with pytest.raises(MalformedMappingError, match="claimed by both"):
            registry(spec("SRC001", "Alpha"), spec("SRC002", "Alpha"))

    def test_encoded_conditions_must_be_named(self):
        with pytest.raises(ValueError, match="names no required_conditions"):
            spec(condition_policy=ConditionPolicy.TARGET_ENCODES_CONDITIONS)

    def test_required_conditions_without_the_policy_are_rejected(self):
        with pytest.raises(ValueError, match="does not use them"):
            spec(required_conditions=conditions((ConditionKind.VOLTAGE, "400 V")))

    def test_an_unreachable_value_kind_is_rejected(self):
        with pytest.raises(ValueError, match="could never fire"):
            spec(expected_value_kind="range")

    def test_declared_authority_must_match_the_rules(self):
        with pytest.raises(MalformedMappingError, match="declared authority"):
            MappingRegistry(
                [spec(authority=MappingAuthority.DEMO)],
                name="x",
                authority=MappingAuthority.OFFICIAL,
            )


class TestProvenance:
    def test_committed_attributes_keep_their_evidence_link(self):
        """U, W."""
        result = assemble_verified_attributes([verified()], registry(), schema())
        attribute = result.attributes[0]
        assert attribute.source_key == "SRC001"
        assert attribute.artifact_sha256 == SHA
        assert attribute.page_number == 2
        assert attribute.evidence_text == "18 A stated here"
        assert attribute.exact_mpn == MPN

    def test_verifier_version_is_retained(self):
        """V."""
        result = assemble_verified_attributes([verified()], registry(), schema())
        assert result.attributes[0].verifier_version == VERIFIER_VERSION

    def test_provenance_is_not_written_into_the_record(self):
        """The CSV has nowhere to put it; the result keeps it instead."""
        result = assemble_verified_attributes([verified()], registry(), schema())
        row = " ".join(result.record.to_row())
        assert SHA not in row
        assert VERIFIER_VERSION not in row
        assert "18 A stated here" not in row
        assert result.provenance()[0]["artifact_sha256"] == SHA

    def test_no_confidence_or_probability_anywhere(self):
        """X."""
        banned = {"confidence", "probability", "score", "certainty", "support_grade"}
        models = (
            AdjudicatedFact,
            MappedUnilogAttribute,
            AssemblySummary,
            AttributeMappingSpec,
        )
        for model in models:
            assert not banned & set(model.model_fields)

    def test_adjudication_cannot_modify_a_verification_outcome(self):
        """Y."""
        outcome = verified()
        fact = adjudicate_one(outcome, registry())
        assert fact.outcome is outcome
        with pytest.raises(ValueError, match="frozen"):
            fact.outcome.status = EvidenceVerification.UNVERIFIED  # type: ignore[misc]

    def test_the_authority_of_every_rule_travels_with_its_attribute(self):
        result = assemble_verified_attributes([verified()], registry(), schema())
        assert result.attributes[0].authority is MappingAuthority.DEMO
        assert result.attributes[0].is_authoritative is False
        assert result.authoritative_mapping is False


class TestOpaqueSourceKeys:
    def test_a_non_etim_source_key_maps_identically(self):
        """Z. The engine never inspects a key, so a Unilog key behaves the same."""
        width = NumericValue(number=45.0, unit="mm", raw="45 mm")
        outcome = verified(key="unilog:raw_width", value=width)
        result = assemble_verified_attributes(
            [outcome], registry(spec("unilog:raw_width", "Width")), schema()
        )
        assert result.summary.committed == 1
        assert result.attributes[0].label == "Width"
        assert result.attributes[0].source_key == "unilog:raw_width"

    def test_the_engine_holds_no_source_key_literals(self):
        """No `if source_key == "EF000008"` anywhere. Mappings are data.

        Checked against string constants in the parsed code, with docstrings excluded:
        documenting that a key *may* look like an ETIM id is the opposite of branching
        on one, and a substring scan cannot tell those apart.
        """
        import ast
        import re
        from pathlib import Path

        package = Path(__file__).resolve().parents[1] / "backend" / "skutruth" / "adjudication"
        for module in package.glob("*.py"):
            tree = ast.parse(module.read_text(encoding="utf-8"))
            docstrings = {
                ast.get_docstring(node, clean=False)
                for node in ast.walk(tree)
                if isinstance(
                    node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef
                )
            }
            literals = [
                node.value
                for node in ast.walk(tree)
                if isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and node.value not in docstrings
            ]
            offenders = [text for text in literals if re.search(r"EF\d{6}", text)]
            assert not offenders, f"{module.name} names an ETIM feature id: {offenders}"


class TestRegistryLoading:
    def test_a_toml_registry_round_trips(self):
        data = {
            "name": "loaded",
            "authority": "DEMO",
            "mapping": [
                {
                    "source_key": "SRC001",
                    "target_label": "Width",
                    "priority": 10,
                    "target_uom": "mm",
                    "expected_value_kind": "numeric",
                }
            ],
        }
        loaded = parse_registry(data)
        assert len(loaded) == 1
        assert loaded.spec_for("SRC001").target_label == "Width"
        assert loaded.is_authoritative is False

    def test_conditions_load_from_toml(self):
        data = {
            "name": "loaded",
            "authority": "DEMO",
            "mapping": [
                {
                    "source_key": "SRC001",
                    "target_label": "Power at AC-3",
                    "priority": 10,
                    "condition_policy": "TARGET_ENCODES_CONDITIONS",
                    "required_conditions": [{"kind": "UTILIZATION_CATEGORY", "value": "AC-3"}],
                }
            ],
        }
        loaded = parse_registry(data)
        assert loaded.spec_for("SRC001").required_conditions.conditions[0].value == "AC-3"

    def test_a_missing_authority_is_rejected(self):
        with pytest.raises(MalformedMappingError, match="must declare"):
            parse_registry({"name": "x", "mapping": []})

    def test_an_invalid_entry_names_itself(self):
        data = {
            "name": "x",
            "authority": "DEMO",
            "mapping": [{"source_key": "SRC001", "priority": 1}],
        }
        with pytest.raises(MalformedMappingError, match="SRC001"):
            parse_registry(data)

    def test_a_missing_file_is_reported(self, tmp_path):
        with pytest.raises(MalformedMappingError, match="no mapping file"):
            load_registry(tmp_path / "absent.toml")

    def test_the_committed_demo_registry_loads_and_is_not_authoritative(self):
        """The shipped LC1D18 mapping must never claim to be organizer-supplied."""
        from pathlib import Path

        path = (
            Path(__file__).resolve().parents[1] / "data" / "mappings" / "lc1d18-demo.toml"
        )
        loaded = load_registry(path)
        assert loaded.authority is MappingAuthority.DEMO
        assert loaded.is_authoritative is False
        assert all(s.authority is MappingAuthority.DEMO for s in loaded.specs)


class TestSummary:
    def test_counts_add_up(self):
        outcomes = [
            verified(key="SRC001"),
            verified(key="SRC404"),
            unverified(key="SRC002"),
        ]
        rules = registry(spec("SRC001", "Alpha"), spec("SRC002", "Beta", priority=20))
        result = assemble_verified_attributes(outcomes, rules, schema())
        s = result.summary
        assert s.input_facts == 3
        assert s.verified == 2
        assert s.committed + s.withheld + s.unmapped + s.review == s.input_facts
        assert s.committed == 1
        assert s.unmapped == 1
        assert s.withheld == 1
        assert s.attributes_written == 1
        assert s.slots_remaining == 3
