"""Per-class structured extraction schemas.

Generated at runtime for one ETIM class at a time — never a single schema spanning
all 5,640 classes, which would be both enormous and useless as a constraint.

The point is to remove choices from the model rather than to describe them to it. A
picklist feature is emitted as a closed `enum` of the real ETIM values, so an invalid
one cannot be returned. A unit-bearing feature accepts only units sharing the ETIM
unit's dimension, so amperes cannot arrive where volts belong — while still letting a
source report milliamps for `units.normalize_numeric` to convert. Feature ids come
from the loader, so the model cannot invent one, and the class id is a single-member
enum, so it cannot invent that either.

Equally important is what the schema does *not* expose. There is no confidence field,
no condition-completeness field, and no `proves_family_scope` field. Those are
decisions the system makes from evidence; letting a model assert them would hand back
exactly the trust the architecture is built to withhold. A test asserts they never
appear in the serialized output.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from skutruth.contracts import ConditionKind, EtimFeatureType

from . import units
from .demo_classes import DemoClassConfig
from .model import EtimClass

#: Recorded on every generated schema and on the Evidence produced from it, so a
#: stored extraction can be traced to the schema shape that constrained it.
EXTRACTION_SCHEMA_VERSION = "etim-extraction@v1"

#: Fields the model must never be asked for. Enforced by test, not by convention.
FORBIDDEN_SCHEMA_KEYS = (
    "completeness",
    "proves_family_scope",
    "confidence",
    "support_grade",
    "verification",
)


@dataclass(frozen=True, slots=True)
class FeatureSchema:
    """Everything extraction needs to know about one feature."""

    feature_id: str
    name: str
    feature_type: EtimFeatureType
    unit: str | None
    accepted_units: tuple[str, ...]
    allowed_values: tuple[tuple[str, str], ...]  # (value_id, text)
    required_condition_kinds: tuple[ConditionKind, ...]
    expected_conditions: tuple[tuple[ConditionKind, str], ...]
    buyer_critical: bool
    qualifier_rationale: str | None = None

    @property
    def value_kind(self) -> str:
        return {
            EtimFeatureType.NUMERIC: "numeric",
            EtimFeatureType.RANGE: "range",
            EtimFeatureType.ALPHANUMERIC: "alphanumeric",
            EtimFeatureType.LOGICAL: "logical",
        }[self.feature_type]

    def instruction(self) -> str:
        """One line of prompt-facing guidance, assembled from ETIM facts only."""
        bits = [self.name]
        if self.unit:
            bits.append(f"reported in {self.unit}")
        if self.expected_conditions:
            fixed = ", ".join(f"{k.value}={v}" for k, v in self.expected_conditions)
            bits.append(f"defined at {fixed}")
        elif self.required_condition_kinds:
            need = ", ".join(k.value for k in self.required_condition_kinds)
            bits.append(f"record the qualifiers {need}")
        return "; ".join(bits) + "."

    def to_dict(self) -> dict:
        return {
            "etim_feature_id": self.feature_id,
            "name": self.name,
            "etim_feature_type": self.feature_type.value,
            "value_kind": self.value_kind,
            "unit": self.unit,
            "accepted_units": list(self.accepted_units),
            "allowed_values": [
                {"value_id": vid, "text": text} for vid, text in self.allowed_values
            ],
            "required_condition_kinds": [k.value for k in self.required_condition_kinds],
            "expected_conditions": [
                {"kind": k.value, "value": v} for k, v in self.expected_conditions
            ],
            "buyer_critical": self.buyer_critical,
        }


@dataclass(frozen=True)
class ClassExtractionSchema:
    """The extraction contract for one ETIM class."""

    etim_class_id: str
    etim_class_name: str
    etim_release: str
    etim_language: str
    schema_version: str
    features: tuple[FeatureSchema, ...]

    def feature(self, feature_id: str) -> FeatureSchema | None:
        for f in self.features:
            if f.feature_id == feature_id:
                return f
        return None

    @property
    def feature_ids(self) -> tuple[str, ...]:
        return tuple(f.feature_id for f in self.features)

    def to_dict(self) -> dict:
        """The metadata document: what the class is, and what each feature means."""
        return {
            "etim_class_id": self.etim_class_id,
            "etim_class_name": self.etim_class_name,
            "etim_release": self.etim_release,
            "etim_language": self.etim_language,
            "schema_version": self.schema_version,
            "features": [f.to_dict() for f in self.features],
        }

    def json_schema(self) -> dict:
        """The response schema constraining the model's output.

        Targets the OpenAPI 3.0 subset that structured-output APIs accept: object,
        array, string, number, integer, boolean, plus `enum`, `required`, and
        `nullable`. No `oneOf`, `const`, or `$ref`.
        """
        return {
            "type": "object",
            "properties": {
                "etim_class_id": {"type": "string", "enum": [self.etim_class_id]},
                "features": {
                    "type": "object",
                    "description": (
                        "One entry per ETIM feature. Omit a feature, or set it to null, "
                        "when the document does not state it. Never infer a value."
                    ),
                    "properties": {f.feature_id: _feature_schema(f) for f in self.features},
                    "propertyOrdering": list(self.feature_ids),
                },
            },
            "required": ["etim_class_id", "features"],
            "propertyOrdering": ["etim_class_id", "features"],
        }

    def canonical_json(self) -> str:
        """Byte-stable serialization of metadata plus response schema."""
        return json.dumps(
            {"metadata": self.to_dict(), "json_schema": self.json_schema()},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def fingerprint(self) -> str:
        """Content address of this schema.

        Identical ETIM input and configuration produce an identical fingerprint, which
        is what lets it participate in a cache key alongside the document hash and the
        model id.
        """
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()


_CONDITION_SCHEMA = {
    "type": "object",
    "description": (
        "Operating qualifiers the source states for this value, e.g. utilization "
        "category or voltage. Copy only what the document says; never supply a "
        "qualifier the text does not state."
    ),
    "properties": {
        "kind": {"type": "string", "enum": [k.value for k in ConditionKind]},
        "value": {"type": "string", "description": "Normalized qualifier, e.g. 'AC-3'"},
        "raw": {"type": "string", "description": "The qualifier as the source wrote it"},
    },
    "required": ["kind", "value"],
    "propertyOrdering": ["kind", "value", "raw"],
}


def _common_properties(feature: FeatureSchema) -> dict:
    return {
        "raw_text": {
            "type": "string",
            "description": "The supporting text, copied verbatim from the document.",
        },
        "page": {"type": "integer", "description": "1-indexed page the text appears on."},
        "conditions": {"type": "array", "items": dict(_CONDITION_SCHEMA)},
    }


def _feature_schema(feature: FeatureSchema) -> dict:
    props: dict = {}
    required: list[str] = []

    if feature.feature_type is EtimFeatureType.NUMERIC:
        props["number"] = {"type": "number"}
        required.append("number")
    elif feature.feature_type is EtimFeatureType.RANGE:
        props["minimum"] = {"type": "number"}
        props["maximum"] = {"type": "number"}
        required += ["minimum", "maximum"]
    elif feature.feature_type is EtimFeatureType.ALPHANUMERIC:
        text: dict = {"type": "string"}
        if feature.allowed_values:
            text["enum"] = [t for _, t in feature.allowed_values]
        props["text"] = text
        required.append("text")
    else:  # LOGICAL
        props["boolean"] = {"type": "boolean"}
        required.append("boolean")

    if feature.accepted_units:
        props["unit"] = {
            "type": "string",
            "enum": list(feature.accepted_units),
            "description": (
                f"Unit as the source states it. Values are converted to {feature.unit} "
                "deterministically; do not convert them yourself."
            ),
        }
        required.append("unit")

    props.update(_common_properties(feature))
    required += ["raw_text", "page"]

    ordering = [*required, "conditions"]
    return {
        "type": "object",
        "nullable": True,
        "description": feature.instruction(),
        "properties": props,
        "required": required,
        "propertyOrdering": ordering,
    }


def build_extraction_schema(
    etim_class: EtimClass,
    config: DemoClassConfig | None = None,
    *,
    etim_release: str = "10.0",
    etim_language: str = "EN",
    feature_ids: tuple[str, ...] | None = None,
) -> ClassExtractionSchema:
    """Build the extraction schema for one ETIM class.

    `feature_ids` narrows the schema to a subset — useful for targeted re-extraction
    of the features a record is still missing, without re-reading everything. The
    subset is intersected with the class, so an id that is not on the class is
    dropped rather than fabricated into the schema.
    """
    wanted = set(feature_ids) if feature_ids is not None else None
    features: list[FeatureSchema] = []

    for f in etim_class.features:
        if wanted is not None and f.feature_id not in wanted:
            continue
        rule = config.rule_for(f.feature_id) if config is not None else None
        accepted = units.compatible_units(f.unit) if units.is_known(f.unit) else ()
        if f.unit is not None and not accepted:
            # ETIM mandates a unit our registry does not know. Ask for it verbatim
            # rather than silently dropping the unit and inviting a bare number.
            accepted = (f.unit,)
        features.append(
            FeatureSchema(
                feature_id=f.feature_id,
                name=f.name,
                feature_type=f.feature_type,
                unit=f.unit,
                accepted_units=accepted,
                allowed_values=tuple((v.value_id, v.text) for v in f.allowed_values),
                required_condition_kinds=rule.required_kinds if rule else (),
                expected_conditions=rule.expected if rule else (),
                buyer_critical=bool(config and config.is_buyer_critical(f.feature_id)),
                qualifier_rationale=rule.rationale if rule else None,
            )
        )

    return ClassExtractionSchema(
        etim_class_id=etim_class.class_id,
        etim_class_name=etim_class.name,
        etim_release=etim_release,
        etim_language=etim_language,
        schema_version=EXTRACTION_SCHEMA_VERSION,
        features=tuple(features),
    )
