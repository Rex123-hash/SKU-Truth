"""Conservative product classification; all organizer-shaped rows are synthetic."""

from __future__ import annotations

import csv
import io

from skutruth.unilog import (
    AuthorityLevel,
    CanonicalCatalog,
    CanonicalRule,
    ClassificationAuthority,
    ClassificationDecision,
    ClassificationReason,
    DeliverySchema,
    DeterministicNormalizer,
    DeterministicProductClassifier,
    InternalProductFamily,
    OrganizerExampleCatalog,
    RawProductRow,
    organizer_example_rule,
    read_rows,
    record_from_raw_row,
)

HEADERS = (
    "Mfg_Part_Num",
    "Part_Desc",
    "E1_Brand",
    "Unilog_Brand",
    "DIB_Brand",
    "Part_Manuf",
)


def row(
    description: str,
    *,
    mpn: str = "A1",
    manufacturer: str = "Acme Supply (ACME)",
) -> RawProductRow:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer)
    writer.writerow(HEADERS)
    writer.writerow(
        [
            mpn,
            description,
            "-- Unbranded --",
            "-- No Unilog Brand --",
            "-- No DIB Brand --",
            manufacturer,
        ]
    )
    buffer.seek(0)
    return next(read_rows(buffer))


def example_catalog(source: RawProductRow) -> OrganizerExampleCatalog:
    values = dict(source.raw)
    values.update(
        {
            "Dept": "Appliances",
            "Class": "Large Appliances",
            "Fine": "Dishwashers",
            "Classpath": (
                "Appliances & Consumer Electronics>Kitchen Appliances>"
                "Built-In Dishwashers"
            ),
            "UNSPSC": "",
        }
    )
    return OrganizerExampleCatalog(
        (
            organizer_example_rule(
                values, source="synthetic expected output", example_number=1
            ),
        )
    )


def test_single_strong_lexical_family_commits_deterministically():
    source = row("45297BK Kichler Wall Light", mpn="45297BK")
    classifier = DeterministicProductClassifier()
    first = classifier.classify(source)
    second = classifier.classify(source)
    assert first == second
    assert first.internal_family is InternalProductFamily.LIGHTING
    assert first.decision is ClassificationDecision.COMMIT
    assert first.authority is ClassificationAuthority.DETERMINISTIC_INTERNAL
    assert "wall light" in first.normalized_cues


def test_overlapping_unrelated_family_cues_require_review():
    result = DeterministicProductClassifier().classify(
        row('DPH2R1B 1" Phillips Drywall Screws Drive Bit', mpn="DPH2R1B")
    )
    assert result.internal_family is InternalProductFamily.UNKNOWN
    assert result.decision is ClassificationDecision.REVIEW
    assert result.reason is ClassificationReason.OVERLAPPING_FAMILY_CUES
    assert set(result.candidate_families) == {
        InternalProductFamily.DECKING_LUMBER,
        InternalProductFamily.POWER_TOOL_ACCESSORY,
    }


def test_specific_accessory_cue_precedes_general_tool_word():
    result = DeterministicProductClassifier().classify(
        row('D123 Diablo 7-1/4" Circular Saw Blade', mpn="D123")
    )
    assert result.internal_family is InternalProductFamily.POWER_TOOL_ACCESSORY
    assert result.decision is ClassificationDecision.COMMIT
    assert result.reason is ClassificationReason.SPECIFIC_FAMILY_PRECEDENCE


def test_insufficient_description_is_withheld():
    result = DeterministicProductClassifier().classify(row("A1 Widget"))
    assert result.internal_family is InternalProductFamily.UNKNOWN
    assert result.decision is ClassificationDecision.WITHHOLD
    assert result.reason is ClassificationReason.INSUFFICIENT_DESCRIPTION


def test_placeholder_and_empty_descriptions_are_not_classified():
    placeholder = DeterministicProductClassifier().classify(
        row("-- No Description --")
    )
    empty = DeterministicProductClassifier().classify(row(""))
    assert placeholder.reason is ClassificationReason.PLACEHOLDER_DESCRIPTION
    assert empty.reason is ClassificationReason.INSUFFICIENT_DESCRIPTION
    assert placeholder.internal_family is InternalProductFamily.UNKNOWN
    assert empty.internal_family is InternalProductFamily.UNKNOWN


def test_manufacturer_context_is_preserved_but_never_sufficient_by_itself():
    source = row(
        "Z9 Decorative Product",
        mpn="Z9",
        manufacturer="Kichler Lighting (KICLI)",
    )
    normalizer = DeterministicNormalizer(
        manufacturers=CanonicalCatalog(
            (
                CanonicalRule(
                    "Kichler Lighting",
                    (),
                    AuthorityLevel.HUMAN_APPROVED,
                    "synthetic human review",
                ),
            )
        )
    )
    result = DeterministicProductClassifier().classify(
        source, normalization=normalizer.normalize(source)
    )
    assert result.evidence[0].manufacturer_context == "Kichler Lighting"
    assert result.internal_family is InternalProductFamily.UNKNOWN
    assert result.decision is ClassificationDecision.WITHHOLD


def test_unknown_description_remains_unknown():
    result = DeterministicProductClassifier().classify(
        row("LNL65301 Digital Tire Pressure Inflator Gauge", mpn="LNL65301")
    )
    assert result.internal_family is InternalProductFamily.UNKNOWN
    assert result.reason is ClassificationReason.NO_FAMILY_CUE
    assert result.delivery.classpath is None


def test_internal_family_survives_when_delivery_classpath_is_blank():
    result = DeterministicProductClassifier().classify(
        row("KDFM404KPS Dishwasher SS", mpn="KDFM404KPS")
    )
    assert result.internal_family is InternalProductFamily.DISHWASHER
    assert result.decision is ClassificationDecision.COMMIT
    assert result.delivery.decision is ClassificationDecision.WITHHOLD
    assert result.delivery.delivery_values == ()


def test_exact_organizer_example_can_map_its_own_delivery_fields():
    source = row("PDSH4816AF Dishwasher SS - Display Only", mpn="PDSH4816AF")
    classifier = DeterministicProductClassifier(
        organizer_examples=example_catalog(source)
    )
    result = classifier.classify(source)
    assert result.delivery.decision is ClassificationDecision.COMMIT
    assert result.delivery.authority is ClassificationAuthority.ORGANIZER_EXAMPLE
    assert result.delivery.reason is ClassificationReason.EXACT_ORGANIZER_EXAMPLE
    assert result.delivery.classpath == (
        "Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers"
    )


def test_organizer_example_is_not_a_universal_dishwasher_lov():
    example = row("PDSH4816AF Dishwasher SS - Display Only", mpn="PDSH4816AF")
    another = row("KDFM404KPS Dishwasher SS", mpn="KDFM404KPS")
    result = DeterministicProductClassifier(
        organizer_examples=example_catalog(example)
    ).classify(another)
    assert result.internal_family is InternalProductFamily.DISHWASHER
    assert result.delivery.decision is ClassificationDecision.WITHHOLD
    assert result.delivery.classpath is None
    assert result.delivery.authority is ClassificationAuthority.UNRESOLVED


def test_etim_reference_is_not_delivery_authority():
    assert ClassificationAuthority.ETIM_REFERENCE.permits_delivery is False


def test_delivery_mapping_fails_closed_without_taxonomy_authority():
    source = row("45297BK Kichler Wall Light", mpn="45297BK")
    result = DeterministicProductClassifier().classify(source)
    schema = DeliverySchema(["Mfg_Part_Num", "Classpath", "UNSPSC"])
    record = record_from_raw_row(source, schema, classification=result)
    assert record.get("Mfg_Part_Num") == "45297BK"
    assert record.get("Classpath") == ""
    assert record.get("UNSPSC") == ""


def test_classification_does_not_mutate_the_delivery_schema():
    source = row("PDSH4816AF Dishwasher SS - Display Only", mpn="PDSH4816AF")
    result = DeterministicProductClassifier(
        organizer_examples=example_catalog(source)
    ).classify(source)
    headers = [
        "Mfg_Part_Num",
        "Dept",
        "Class",
        "Fine",
        "Classpath",
        "UNSPSC",
    ]
    for index in range(1, 51):
        headers.extend(
            (
                f"ATTRIBUTE_LABEL {index}",
                f"ATTRIBUTE_VALUE {index}",
                f"ATTRIBUTE_UOM {index}",
            )
        )
    headers.extend(f"EXTRA_{index}" for index in range(1, 97))
    schema = DeliverySchema(headers)
    assert schema.field_count == 252
    assert schema.attribute_slot_count == 50
    before = schema.headers
    record = record_from_raw_row(source, schema, classification=result)
    assert schema.headers == before
    assert record.get("Mfg_Part_Num") == "PDSH4816AF"
    assert record.get("Dept") == "Appliances"
    assert record.get("Class") == "Large Appliances"
    assert record.get("Fine") == "Dishwashers"
    assert record.get("Classpath") == (
        "Appliances & Consumer Electronics>Kitchen Appliances>Built-In Dishwashers"
    )
    assert record.get("UNSPSC") == ""
    assert len(record.to_row()) == 252
