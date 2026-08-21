"""Unilog attribute foundations; organizer-shaped examples are synthetic and local."""

from __future__ import annotations

import csv
from decimal import Decimal

import pytest
from skutruth.contracts import EvidenceVerification
from skutruth.unilog import (
    AttributeAuthority,
    AttributeCandidate,
    AttributeEvidence,
    AttributeProfile,
    AttributeProfileScope,
    AttributeProfileSlot,
    AttributeReason,
    AttributeValueKind,
    ClassificationDecision,
    DeliveryRecord,
    DeliverySchema,
    UomResolution,
    load_organizer_attribute_catalog,
    map_organizer_attribute_example,
    parse_boolean,
    parse_controlled_value,
    parse_decimal,
    parse_integer,
    parse_number,
    parse_number_with_unit,
    parse_simple_range,
    parse_text,
    resolve_attribute_candidates,
)

LABELS = tuple(f"Observed Attribute {index}" for index in range(1, 16))

ROW_ONE = (
    ("Alpha", ""),
    ("", ""),
    ("5", ""),
    ("120", "V"),
    ("15", "A"),
    ("Option A", ""),
    ("", ""),
    ("24 in W x 25 in D", ""),
    ("50.25", "in"),
    ("8 in section A, 11 in section B", ""),
    ("10 in section A, 13 in section B", ""),
    ("47", "dBA"),
    ("Material A", ""),
    ("", ""),
    ("Additional example information A", ""),
)

ROW_TWO = (
    ("Beta", ""),
    ("", ""),
    ("", ""),
    ("120", "V"),
    ("10", "A"),
    ("Option B", ""),
    ("", ""),
    ("33 in H x 24 in W x 23 in D", ""),
    ("50.50", "in"),
    ("33.25", "in"),
    ("", ""),
    ("41", "dBA"),
    ("Material A", ""),
    ("Finish B", ""),
    ("Additional example information B", ""),
)

CLASSPATH = "Synthetic>Example Class"


def delivery_headers() -> list[str]:
    headers = ["Mfg_Part_Num", "Classpath"]
    for index in range(1, 51):
        headers.extend(
            (
                f"ATTRIBUTE_LABEL {index}",
                f"ATTRIBUTE_VALUE {index}",
                f"ATTRIBUTE_UOM {index}",
            )
        )
    headers.extend(f"EXTRA_{index}" for index in range(1, 101))
    assert len(headers) == 252
    return headers


def example_row(record_key: str, values: tuple[tuple[str, str], ...]) -> dict[str, str]:
    row = dict.fromkeys(delivery_headers(), "")
    row["Mfg_Part_Num"] = record_key
    row["Classpath"] = CLASSPATH
    for index, (label, (value, uom)) in enumerate(zip(LABELS, values, strict=True), start=1):
        row[f"ATTRIBUTE_LABEL {index}"] = label
        row[f"ATTRIBUTE_VALUE {index}"] = value
        row[f"ATTRIBUTE_UOM {index}"] = uom
    return row


@pytest.fixture
def example_file(tmp_path):
    path = tmp_path / "delivery_examples.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=delivery_headers())
        writer.writeheader()
        writer.writerow(example_row("SKU-A", ROW_ONE))
        writer.writerow(example_row("SKU-B", ROW_TWO))
    return path


def one_slot_profile(
    *,
    authority: AttributeAuthority = AttributeAuthority.ORGANIZER_EXAMPLE,
    exact_records: tuple[str, ...] = ("SKU-1",),
    internal_family: str | None = None,
    candidate_classpath: str | None = None,
    expected_kind: AttributeValueKind | None = None,
    expected_uom: str | None = None,
) -> AttributeProfile:
    return AttributeProfile(
        profile_id="profile-1",
        slots=(
            AttributeProfileSlot(
                index=1,
                source_key="source:one",
                label="Voltage Rating",
                expected_value_kind=expected_kind,
                expected_uom=expected_uom,
            ),
        ),
        authority=authority,
        evidence=(),
        scope=AttributeProfileScope(
            exact_record_keys=exact_records,
            internal_family=internal_family,
            candidate_classpath=candidate_classpath,
        ),
    )


def candidate(
    raw_value: str = "120",
    *,
    raw_uom: str = "V",
    decision: ClassificationDecision = ClassificationDecision.COMMIT,
    authority: AttributeAuthority = AttributeAuthority.ORGANIZER_EXAMPLE,
    label: str = "Voltage Rating",
    source_key: str = "source:one",
) -> AttributeCandidate:
    return AttributeCandidate(
        source_key=source_key,
        label=label,
        value=parse_number(raw_value, raw_uom=raw_uom),
        decision=decision,
        reason=AttributeReason.ELIGIBLE,
        authority=authority,
    )


def test_real_shape_is_discovered_dynamically_and_ordered(example_file):
    catalog = load_organizer_attribute_catalog(example_file)
    assert catalog.schema.field_count == 252
    assert catalog.schema.attribute_slot_count == 50
    assert tuple(slot.index for slot in catalog.examples[0].slots) == tuple(range(1, 51))
    assert catalog.examples[0].labels_populated == 15
    assert catalog.examples[0].values_populated == 12
    assert catalog.examples[0].uoms_populated == 4
    assert catalog.examples[1].labels_populated == 15
    assert catalog.examples[1].values_populated == 11
    assert catalog.examples[1].uoms_populated == 5
    assert all(
        not slot.label and not slot.value and not slot.uom
        for row in catalog.examples
        for slot in row.slots[15:]
    )


def test_shared_profile_is_derived_from_rows_not_a_builtin_label_list(example_file):
    catalog = load_organizer_attribute_catalog(example_file)
    profile = catalog.derive_profile(internal_family="DISHWASHER")
    assert tuple(slot.label for slot in profile.slots) == LABELS
    assert tuple(slot.index for slot in profile.slots) == tuple(range(1, 16))
    assert profile.authority is AttributeAuthority.ORGANIZER_EXAMPLE
    assert profile.scope.exact_record_keys == ("SKU-A", "SKU-B")
    assert profile.scope.internal_family == "DISHWASHER"
    assert profile.scope.detail == "exact organizer example records only"


@pytest.mark.parametrize("record_key", ["SKU-A", "SKU-B"])
def test_example_attribute_block_round_trips_all_50_triplets(example_file, record_key):
    catalog = load_organizer_attribute_catalog(example_file)
    profile = catalog.derive_profile(internal_family="DISHWASHER")
    example = catalog.example(record_key)
    assert example is not None
    mapping = map_organizer_attribute_example(example, profile)
    record = DeliveryRecord(catalog.schema)
    assert record.apply_attribute_mapping(mapping) == 15
    actual = tuple(
        (slot.index, slot.label, slot.value, slot.uom) for slot in record.attribute_slots()
    )
    expected = tuple(
        (slot.index, slot.label, slot.value, slot.uom) for slot in example.slots
    )
    assert actual == expected


def test_label_present_with_blank_value_is_not_an_absent_slot(example_file):
    catalog = load_organizer_attribute_catalog(example_file)
    profile = catalog.derive_profile()
    example = catalog.example("SKU-A")
    assert example is not None
    record = DeliveryRecord(catalog.schema)
    record.apply_attribute_mapping(map_organizer_attribute_example(example, profile))
    model = record.attribute_slots()[1]
    assert model.label == "Observed Attribute 2"
    assert model.value == "" and model.uom == ""
    assert model.is_declared_but_blank
    assert record.attribute_slots()[15].is_declared is False


def test_raw_and_normalized_value_and_uom_remain_separate():
    value = parse_number_with_unit("120 volts")
    assert value.raw_value == "120 volts"
    assert value.normalized_value == Decimal("120")
    assert value.raw_uom == "volts"
    assert value.normalized_uom == "V"
    assert value.uom_resolution is UomResolution.ALIAS


def test_integer_decimal_and_number_with_unit_preserve_decimal_representation():
    assert parse_integer("005").normalized_value == Decimal("5")
    decimal = parse_decimal("12.50", raw_uom="A")
    assert decimal.normalized_value == Decimal("12.50")
    assert decimal.delivery_value() == "12.50"
    assert parse_number_with_unit("0.125 in").delivery_value() == "0.125"


def test_text_controlled_boolean_and_range_are_distinct_value_kinds():
    text = parse_text("Stainless Steel")
    controlled = parse_controlled_value("Built-in")
    logical = parse_boolean("yes")
    span = parse_simple_range("1 to 12 V")
    assert text.value_kind is AttributeValueKind.TEXT
    assert controlled.value_kind is AttributeValueKind.ENUM
    assert logical.value_kind is AttributeValueKind.BOOLEAN
    assert logical.normalized_value is True
    assert span.value_kind is AttributeValueKind.RANGE
    assert span.normalized_value.minimum == Decimal("1")
    assert span.normalized_value.maximum == Decimal("12")
    assert span.delivery_value() == "1 to 12"
    assert span.delivery_uom() == "V"


def test_unknown_uom_remains_raw_and_unresolved():
    value = parse_number("3.40", raw_uom="mystery-unit")
    assert value.raw_uom == "mystery-unit"
    assert value.normalized_uom is None
    assert value.uom_resolution is UomResolution.UNRESOLVED
    result = resolve_attribute_candidates(
        one_slot_profile(),
        [candidate(raw_uom="mystery-unit")],
        record_key="SKU-1",
    )
    assert result.resolutions[0].decision is ClassificationDecision.REVIEW
    assert result.resolutions[0].reason is AttributeReason.UNKNOWN_UOM
    assert result.delivery_slots()[0].value == ""


def test_duplicate_candidates_agree_and_are_merged_deterministically():
    first = candidate()
    second = candidate(authority=AttributeAuthority.HUMAN_APPROVED)
    forward = resolve_attribute_candidates(
        one_slot_profile(), [first, second], record_key="SKU-1"
    )
    reverse = resolve_attribute_candidates(
        one_slot_profile(), [second, first], record_key="SKU-1"
    )
    assert forward == reverse
    assert forward.resolutions[0].decision is ClassificationDecision.COMMIT
    assert forward.resolutions[0].reason is AttributeReason.DUPLICATE_AGREEMENT
    assert len(forward.resolutions[0].candidates) == 2


def test_conflicting_candidates_require_review_and_emit_no_value():
    result = resolve_attribute_candidates(
        one_slot_profile(), [candidate("120"), candidate("240")], record_key="SKU-1"
    )
    assert result.decision is ClassificationDecision.REVIEW
    assert result.resolutions[0].reason is AttributeReason.CONFLICTING_VALUES
    assert result.delivery_slots()[0].value == ""


@pytest.mark.parametrize(
    ("candidate_decision", "expected"),
    [
        (ClassificationDecision.COMMIT, ClassificationDecision.COMMIT),
        (ClassificationDecision.REVIEW, ClassificationDecision.REVIEW),
        (ClassificationDecision.WITHHOLD, ClassificationDecision.WITHHOLD),
    ],
)
def test_commit_review_withhold_are_preserved(candidate_decision, expected):
    result = resolve_attribute_candidates(
        one_slot_profile(),
        [candidate(decision=candidate_decision)],
        record_key="SKU-1",
    )
    assert result.resolutions[0].decision is expected


def test_candidate_label_cannot_replace_authorized_profile_label():
    result = resolve_attribute_candidates(
        one_slot_profile(),
        [candidate(label="Invented Label")],
        record_key="SKU-1",
    )
    record = DeliveryRecord(DeliverySchema(delivery_headers()))
    record.apply_attribute_mapping(result)
    assert record.attribute_slots()[0].label == "Voltage Rating"
    assert "Invented Label" not in record.to_row()
    assert record.attribute_slots()[0].value == ""


def test_candidate_for_unknown_profile_slot_is_audited_but_never_mapped():
    result = resolve_attribute_candidates(
        one_slot_profile(),
        [candidate(source_key="source:unknown", label="Invented Label")],
        record_key="SKU-1",
    )
    assert len(result.unmapped_candidates) == 1
    assert result.delivery_slots()[0].label == "Voltage Rating"
    assert result.delivery_slots()[0].value == ""


def test_etim_reference_alone_cannot_authorize_unilog_label():
    profile = one_slot_profile(authority=AttributeAuthority.ETIM_REFERENCE)
    mapping = resolve_attribute_candidates(profile, [candidate()], record_key="SKU-1")
    record = DeliveryRecord(DeliverySchema(delivery_headers()))
    assert record.apply_attribute_mapping(mapping) == 0
    assert mapping.reason is AttributeReason.PROFILE_AUTHORITY_INSUFFICIENT
    assert not any(slot.is_declared for slot in record.attribute_slots())


def test_internal_family_alone_cannot_authorize_example_profile():
    profile = one_slot_profile(exact_records=(), internal_family="DISHWASHER")
    mapping = resolve_attribute_candidates(profile, [candidate()], record_key="SKU-1")
    assert mapping.labels_authorized is False
    assert mapping.reason is AttributeReason.PROFILE_OUT_OF_SCOPE
    assert mapping.delivery_slots() == ()


def test_lov_classpath_scope_must_match_caller_context():
    profile = one_slot_profile(
        authority=AttributeAuthority.ORGANIZER_LOV,
        exact_records=(),
        candidate_classpath="A>B",
    )
    refused = resolve_attribute_candidates(
        profile, [candidate(authority=AttributeAuthority.HUMAN_APPROVED)], record_key="SKU-1"
    )
    allowed = resolve_attribute_candidates(
        profile,
        [candidate(authority=AttributeAuthority.HUMAN_APPROVED)],
        record_key="SKU-1",
        candidate_classpath="A>B",
    )
    assert refused.delivery_slots() == ()
    assert allowed.delivery_slots()[0].label == "Voltage Rating"


def test_profile_value_kind_and_uom_are_validated():
    wrong_kind = resolve_attribute_candidates(
        one_slot_profile(expected_kind=AttributeValueKind.TEXT),
        [candidate()],
        record_key="SKU-1",
    )
    wrong_uom = resolve_attribute_candidates(
        one_slot_profile(expected_uom="A"), [candidate()], record_key="SKU-1"
    )
    assert wrong_kind.resolutions[0].reason is AttributeReason.VALUE_KIND_MISMATCH
    assert wrong_uom.resolutions[0].reason is AttributeReason.UOM_MISMATCH


def test_manufacturer_authority_requires_located_evidence():
    unsupported = candidate(authority=AttributeAuthority.MANUFACTURER_EVIDENCE)
    supported = AttributeCandidate(
        source_key="source:one",
        label="Voltage Rating",
        value=parse_number("120", raw_uom="V"),
        decision=ClassificationDecision.COMMIT,
        reason=AttributeReason.ELIGIBLE,
        authority=AttributeAuthority.MANUFACTURER_EVIDENCE,
        evidence=(
            AttributeEvidence(
                artifact_id="sha256:example",
                source_locator="https://manufacturer.example/spec.pdf",
                page=2,
                source_fragment="Voltage 120 V",
                span_start=10,
                span_end=23,
                verification=EvidenceVerification.EXACT_SPAN,
            ),
        ),
    )
    first = resolve_attribute_candidates(
        one_slot_profile(), [unsupported], record_key="SKU-1"
    )
    second = resolve_attribute_candidates(one_slot_profile(), [supported], record_key="SKU-1")
    assert first.resolutions[0].reason is AttributeReason.MANUFACTURER_EVIDENCE_UNVERIFIED
    assert second.resolutions[0].decision is ClassificationDecision.COMMIT


def test_schema_remains_immutable_at_252_fields_and_50_triplets():
    schema = DeliverySchema(delivery_headers())
    before = schema.headers
    mapping = resolve_attribute_candidates(
        one_slot_profile(), [candidate()], record_key="SKU-1"
    )
    record = DeliveryRecord(schema)
    record.apply_attribute_mapping(mapping)
    assert schema.headers == before
    assert schema.field_count == 252
    assert schema.attribute_slot_count == 50
    assert len(record.to_row()) == 252


def test_profile_order_is_not_sorted_or_repaired():
    with pytest.raises(ValueError, match="authoritative slot order"):
        AttributeProfile(
            profile_id="unordered",
            slots=(
                AttributeProfileSlot(2, "second", "Second"),
                AttributeProfileSlot(1, "first", "First"),
            ),
            authority=AttributeAuthority.HUMAN_APPROVED,
            evidence=(),
            scope=AttributeProfileScope(exact_record_keys=("SKU-1",)),
        )
