"""The bridge: a raw organizer row and a real PDF become a delivery row.

This is the first test in the project that exercises both halves in one pass. Everything
in it is synthetic — the PDF is built in-process, the mapping is hand-written here, and
no organizer file, manufacturer document, model, or network call is involved.

    RawProductRow            the messy input
          ↓
    ProductClaim             what a model proposed
          ↓
    verify_claim             located in a hashed artifact, or refused
          ↓
    AttributeMappingSpec     an explicit, non-authoritative rule
          ↓
    adjudication             safe to commit here?
          ↓
    DeliveryRecord           the ordered delivery contract
          ↓
    CSV                      byte-exact round trip

The negative half matters as much as the positive: the same run carries a claim the
document does not support, and the assertion is that it reaches no cell.
"""

from __future__ import annotations

import csv
import io

from conftest_pdf import build_pdf
from skutruth.adjudication import (
    AdjudicationDecision,
    AdjudicationReason,
    AttributeMappingSpec,
    ConditionPolicy,
    MappingAuthority,
    MappingRegistry,
    assemble_verified_attributes,
)
from skutruth.contracts import (
    AlphanumericValue,
    Condition,
    ConditionKind,
    ConditionSet,
    EvidenceVerification,
    IdentityScope,
    NumericValue,
)
from skutruth.ingest import ingest_pdf_bytes
from skutruth.ingest.models import SourceMetadata
from skutruth.ingest.storage import ArtifactStore
from skutruth.unilog.delivery import write_delivery_csv
from skutruth.unilog.input import RawProductRow
from skutruth.unilog.schema import DeliverySchema
from skutruth.verification import ProductClaim, verify_claim

MPN = "BASE100X1"
BRAND = "TestCo"

PAGES = [
    "TESTCO CONTACTOR DATA",
    "18 A (at <60 °C) at <= 440 V AC AC-3 for power circuit",
    "Width 45 mm\nHousing Stainless Steel\n7.5 kW at AC-3 400 V",
]

#: What the organizer input row said, placeholders and all.
RAW_INPUT = {
    "Mfg_Part_Num": MPN,
    "Part_Desc": "TESTCO CONTACTOR 18A",
    "E1_Brand": "-- Unbranded --",
    "Unilog_Brand": "-- No Unilog Brand --",
    "DIB_Brand": "",
    "Part_Manuf": "TestCo (TSTCO)",
}


def delivery_schema(slots: int = 6) -> DeliverySchema:
    """A miniature delivery contract with the organizer's triplet shape."""
    headers = [
        "Mfg_Part_Num",
        "Part_Desc",
        "E1_Brand",
        "Unilog_Brand",
        "DIB_Brand",
        "Part_Manuf",
        "MANUFACTURER_NAME",
        "Classpath",
        "SHORT_DESC",
    ]
    for index in range(1, slots + 1):
        headers += [
            f"ATTRIBUTE_LABEL {index}",
            f"ATTRIBUTE_VALUE {index}",
            f"ATTRIBUTE_UOM {index}",
        ]
    return DeliverySchema(headers)


def raw_row() -> RawProductRow:
    return RawProductRow(row_number=1, raw=dict(RAW_INPUT))


def demo_registry() -> MappingRegistry:
    """Explicit, hand-written, and marked as such."""
    encoded = ConditionSet(
        conditions=(
            Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3"),
            Condition(kind=ConditionKind.VOLTAGE, value="400 V"),
        )
    )
    return MappingRegistry(
        [
            AttributeMappingSpec(
                source_key="src:width",
                target_label="Width",
                authority=MappingAuthority.DEMO,
                priority=10,
                target_uom="mm",
                expected_value_kind="numeric",
            ),
            AttributeMappingSpec(
                source_key="src:housing",
                target_label="Material",
                authority=MappingAuthority.DEMO,
                priority=20,
                expected_value_kind="alphanumeric",
            ),
            AttributeMappingSpec(
                source_key="src:power",
                target_label="Rated Operational Power at AC-3, 400 V",
                authority=MappingAuthority.DEMO,
                priority=30,
                target_uom="kW",
                expected_value_kind="numeric",
                condition_policy=ConditionPolicy.TARGET_ENCODES_CONDITIONS,
                required_conditions=encoded,
            ),
            AttributeMappingSpec(
                source_key="src:current",
                target_label="Amperage Rating",
                authority=MappingAuthority.DEMO,
                priority=40,
                target_uom="A",
                expected_value_kind="numeric",
            ),
        ],
        name="bridge-demo",
        authority=MappingAuthority.DEMO,
    )


class TestVerifiedFactsBecomeADeliveryRow:
    def _run(self, tmp_path):
        store = ArtifactStore(tmp_path, writable=True)
        pdf = build_pdf(PAGES)
        artifact = ingest_pdf_bytes(
            pdf,
            source=SourceMetadata(
                publisher=BRAND,
                identity_scope=IdentityScope.EXACT_SKU,
                covers_mpn=MPN,
                final_artifact_url="https://example.invalid/datasheet.pdf",
            ),
        )
        store.save(artifact, pdf)

        power_conditions = ConditionSet(
            conditions=(
                Condition(kind=ConditionKind.UTILIZATION_CATEGORY, value="AC-3"),
                Condition(kind=ConditionKind.VOLTAGE, value="400 V"),
            )
        )
        proposals = [
            (
                "src:width",
                NumericValue(number=45.0, unit="mm", raw="45 mm"),
                3,
                "Width 45 mm",
                None,
            ),
            (
                "src:housing",
                AlphanumericValue(text="Stainless Steel", raw="Stainless Steel"),
                3,
                "Housing Stainless Steel",
                None,
            ),
            (
                "src:power",
                NumericValue(number=7.5, unit="kW", raw="7.5 kW"),
                3,
                "7.5 kW at AC-3 400 V",
                power_conditions,
            ),
            # Proposed but unsupported: the document states `<= 440 V`, not a point of
            # 440 V, and the verifier refuses it. It must reach no cell.
            (
                "src:current",
                NumericValue(number=18.0, unit="A", raw="18 A"),
                2,
                "18 A",
                ConditionSet(conditions=(Condition(kind=ConditionKind.VOLTAGE, value="440 V"),)),
            ),
        ]

        outcomes = [
            verify_claim(
                ProductClaim(
                    key=key,
                    value=value,
                    conditions=conds or ConditionSet(),
                    exact_mpn=MPN,
                    artifact_sha256=artifact.sha256,
                    page_number=page,
                    source_fragment=fragment,
                ),
                store=store,
            )
            for key, value, page, fragment, conds in proposals
        ]
        schema = delivery_schema()
        result = assemble_verified_attributes(
            outcomes, demo_registry(), schema, row=raw_row()
        )
        return schema, outcomes, result

    def test_the_whole_chain_produces_a_delivery_row(self, tmp_path):
        schema, outcomes, result = self._run(tmp_path)

        assert result.summary.input_facts == 4
        assert result.summary.verified == 3
        assert result.summary.committed == 3
        assert result.summary.withheld == 1
        assert result.summary.attributes_written == 3

        slots = result.record.declared_attribute_slots()
        assert [(s.index, s.label, s.value, s.uom) for s in slots] == [
            (1, "Width", "45", "mm"),
            (2, "Material", "Stainless Steel", ""),
            (3, "Rated Operational Power at AC-3, 400 V", "7.5", "kW"),
        ]

    def test_the_unsupported_claim_reaches_no_cell(self, tmp_path):
        """The negative half. A refused claim is invisible in the output."""
        _, _, result = self._run(tmp_path)

        refused = next(f for f in result.facts if f.source_key == "src:current")
        assert refused.decision is AdjudicationDecision.WITHHOLD
        assert refused.reason is AdjudicationReason.VERIFICATION_FAILED
        assert refused.outcome.status is EvidenceVerification.UNVERIFIED
        assert "Amperage Rating" not in " ".join(result.record.to_row())

    def test_input_passthrough_survives_and_nothing_else_is_invented(self, tmp_path):
        """Only proven passthrough columns are populated; content fields stay empty."""
        _, _, result = self._run(tmp_path)

        assert result.record.get("Mfg_Part_Num") == MPN
        assert result.record.get("E1_Brand") == "-- Unbranded --"
        for empty in ("MANUFACTURER_NAME", "Classpath", "SHORT_DESC"):
            assert result.record.get(empty) == ""

    def test_the_row_round_trips_through_csv(self, tmp_path):
        """AA. Byte-exact, header order preserved, Unicode intact."""
        schema, _, result = self._run(tmp_path)

        buffer = io.StringIO()
        written = write_delivery_csv([result.record], schema, buffer)
        assert written == 1

        rows = list(csv.reader(io.StringIO(buffer.getvalue())))
        assert rows[0] == list(schema.headers)
        assert rows[1] == result.record.to_row()
        assert len(rows[1]) == schema.field_count

        label_index = schema.position("ATTRIBUTE_LABEL 1")
        assert rows[1][label_index] == "Width"
        assert rows[1][label_index + 1] == "45"
        assert rows[1][label_index + 2] == "mm"

    def test_unused_slots_stay_blank_through_export(self, tmp_path):
        schema, _, result = self._run(tmp_path)
        row = result.record.to_row()
        for index in range(4, 7):
            for part in ("LABEL", "VALUE", "UOM"):
                assert row[schema.position(f"ATTRIBUTE_{part} {index}")] == ""

    def test_provenance_survives_the_whole_journey(self, tmp_path):
        """Every written cell can still name the page it came from."""
        _, _, result = self._run(tmp_path)
        for entry in result.provenance():
            assert entry["artifact_sha256"]
            assert entry["page"] >= 1
            assert entry["verifier_version"]
            assert entry["authority"] == "DEMO"

    def test_the_mapping_is_reported_as_non_authoritative(self, tmp_path):
        """Nothing in this chain may be described as Unilog-compliant."""
        _, _, result = self._run(tmp_path)
        assert result.authoritative_mapping is False
