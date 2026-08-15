"""Deterministic validation of extracted values against an ETIM class.

No language model participates in anything here. Every check is a lookup against the
ETIM release or the reviewed class configuration, which is what makes the results
citable rather than merely plausible.

Two entry points, deliberately separate:

* `build_value` takes the raw payload an extraction model produced, and either
  returns a typed, ETIM-canonical `AttributeValue` or refuses. This is where unit
  conversion and picklist mapping happen, and where malformed input dies.
* `validate_feature_value` takes an already-typed value and asserts it is in
  canonical form. Cheap, and safe to run again before acceptance.

Nothing is silently coerced into validity. Normalisation converts *representations*
— 18000 mA into 18 A, "screw connection" into the ETIM allowed value "Screw
connection" — and every such change records a `Derivation`. Anything that is actually
invalid produces an error and no value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from skutruth.contracts import (
    AlphanumericValue,
    AttributeValue,
    Condition,
    ConditionCompleteness,
    ConditionKind,
    ConditionSet,
    Derivation,
    DerivationKind,
    EtimFeatureType,
    LogicalValue,
    NumericValue,
    RangeValue,
)

from . import units
from .demo_classes import DemoClassConfig
from .model import EtimClass, EtimFeature

ENUM_MAP_TRANSFORM = "etim_enum_map@v1"


class Severity(StrEnum):
    ERROR = "ERROR"  # the value must not be accepted
    WARNING = "WARNING"  # accepted, but a reviewer should see this


class ValidationCode(StrEnum):
    """Closed vocabulary so the UI and the evaluation harness can group failures."""

    UNKNOWN_FEATURE = "UNKNOWN_FEATURE"
    WRONG_VALUE_KIND = "WRONG_VALUE_KIND"
    MISSING_UNIT = "MISSING_UNIT"
    UNEXPECTED_UNIT = "UNEXPECTED_UNIT"
    UNKNOWN_UNIT = "UNKNOWN_UNIT"
    INCOMPATIBLE_UNIT = "INCOMPATIBLE_UNIT"
    UNSUPPORTED_UNIT_CONVERSION = "UNSUPPORTED_UNIT_CONVERSION"
    NON_FINITE_NUMBER = "NON_FINITE_NUMBER"
    RANGE_INVERTED = "RANGE_INVERTED"
    NOT_IN_PICKLIST = "NOT_IN_PICKLIST"
    VALUE_ID_MISMATCH = "VALUE_ID_MISMATCH"
    MALFORMED_PAYLOAD = "MALFORMED_PAYLOAD"
    CONDITIONS_INCOMPLETE = "CONDITIONS_INCOMPLETE"
    CONDITION_VALUE_MISMATCH = "CONDITION_VALUE_MISMATCH"
    NO_QUALIFIER_RULE = "NO_QUALIFIER_RULE"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: ValidationCode
    severity: Severity
    message: str
    feature_id: str | None = None

    def __str__(self) -> str:
        where = f"{self.feature_id}: " if self.feature_id else ""
        return f"[{self.severity}] {where}{self.message}"


@dataclass(frozen=True)
class ValidationResult:
    """Structured outcome, suitable for both the pipeline and the Evidence Drawer."""

    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.severity is Severity.WARNING)

    @property
    def ok(self) -> bool:
        """True when nothing blocks acceptance. Warnings do not block."""
        return not self.errors

    def codes(self) -> tuple[ValidationCode, ...]:
        return tuple(i.code for i in self.issues)

    def has(self, code: ValidationCode) -> bool:
        return any(i.code is code for i in self.issues)

    def merge(self, other: ValidationResult) -> ValidationResult:
        return ValidationResult(self.issues + other.issues)


@dataclass
class _Issues:
    feature_id: str | None
    items: list[ValidationIssue] = field(default_factory=list)

    def error(self, code: ValidationCode, message: str) -> None:
        self.items.append(ValidationIssue(code, Severity.ERROR, message, self.feature_id))

    def warn(self, code: ValidationCode, message: str) -> None:
        self.items.append(ValidationIssue(code, Severity.WARNING, message, self.feature_id))

    def result(self) -> ValidationResult:
        return ValidationResult(tuple(self.items))


# ---------------------------------------------------------------------------------
# Raw extraction payload — the shape `schema_gen` asks a model to produce
# ---------------------------------------------------------------------------------


class RawCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ConditionKind
    value: str = Field(min_length=1)
    raw: str | None = None


class RawFeatureValue(BaseModel):
    """What an extraction model returns for one feature, before validation.

    Untyped on purpose: the model fills whichever fields the generated schema exposes
    for the feature, and this layer decides whether that constitutes a valid value.
    Note what is absent — no confidence, no condition completeness, and no
    `proves_family_scope`. Those are decided by code, not proposed by a model.
    """

    model_config = ConfigDict(extra="forbid")

    number: float | None = None
    minimum: float | None = None
    maximum: float | None = None
    unit: str | None = None
    text: str | None = None
    boolean: bool | None = None
    raw_text: str = Field(min_length=1)
    page: int = Field(
        ge=1,
        description="1-indexed page the supporting text appears on. Required, because a "
        "span whose page is unknown cannot be located again and so cannot be verified.",
    )
    conditions: list[RawCondition] = Field(default_factory=list)


# ---------------------------------------------------------------------------------
# Feature lookup
# ---------------------------------------------------------------------------------


def resolve_feature(
    etim_class: EtimClass, feature_id: str
) -> tuple[EtimFeature | None, ValidationResult]:
    """Look the feature up on the class, or report that it does not belong there."""
    feature = etim_class.feature(feature_id)
    if feature is None:
        issues = _Issues(feature_id)
        issues.error(
            ValidationCode.UNKNOWN_FEATURE,
            f"{feature_id} is not a feature of {etim_class.class_id} "
            f"({etim_class.name})",
        )
        return None, issues.result()
    return feature, ValidationResult()


# ---------------------------------------------------------------------------------
# Typed-value validation
# ---------------------------------------------------------------------------------


def validate_feature_value(
    etim_class: EtimClass, feature_id: str, value: AttributeValue
) -> ValidationResult:
    """Assert a typed value is in ETIM-canonical form for this class-feature."""
    feature, result = resolve_feature(etim_class, feature_id)
    if feature is None:
        return result

    issues = _Issues(feature_id)
    expected_kind = {
        EtimFeatureType.NUMERIC: "numeric",
        EtimFeatureType.RANGE: "range",
        EtimFeatureType.ALPHANUMERIC: "alphanumeric",
        EtimFeatureType.LOGICAL: "logical",
    }[feature.feature_type]
    if value.kind != expected_kind:
        issues.error(
            ValidationCode.WRONG_VALUE_KIND,
            f"ETIM type {feature.feature_type} requires a {expected_kind} value, "
            f"got {value.kind}",
        )
        return issues.result()

    if value.kind in {"numeric", "range"}:
        _check_unit(issues, feature, value.unit)
    if value.kind == "numeric":
        _check_finite(issues, value.number)
    if value.kind == "range":
        _check_finite(issues, value.minimum)
        _check_finite(issues, value.maximum)
        if value.minimum > value.maximum:  # unreachable via the contract; belt and braces
            issues.error(
                ValidationCode.RANGE_INVERTED,
                f"range minimum {value.minimum:g} exceeds maximum {value.maximum:g}",
            )
    if value.kind == "alphanumeric":
        _check_picklist(issues, feature, value.text, value.value_id)

    return issues.result()


def _check_finite(issues: _Issues, number: float) -> None:
    if not math.isfinite(number):
        issues.error(ValidationCode.NON_FINITE_NUMBER, f"{number} is not a finite number")


def _check_unit(issues: _Issues, feature: EtimFeature, unit: str | None) -> None:
    if feature.unit is None:
        if unit is not None:
            issues.error(
                ValidationCode.UNEXPECTED_UNIT,
                f"ETIM defines no unit for this feature, value carries {unit!r}",
            )
        return
    if unit is None:
        issues.error(
            ValidationCode.MISSING_UNIT, f"ETIM mandates unit {feature.unit!r}, value carries none"
        )
        return
    if unit != feature.unit:
        issues.error(
            ValidationCode.UNEXPECTED_UNIT,
            f"ETIM mandates unit {feature.unit!r}, value carries {unit!r}; "
            "normalize before accepting",
        )


def _check_picklist(
    issues: _Issues, feature: EtimFeature, text: str, value_id: str | None
) -> None:
    if not feature.allowed_values:
        return
    allowed = feature.find_allowed(text)
    if allowed is None:
        issues.error(
            ValidationCode.NOT_IN_PICKLIST,
            f"{text!r} is not an allowed value; ETIM permits "
            f"{', '.join(repr(t) for t in feature.allowed_texts())}",
        )
        return
    if text != allowed.text:
        issues.warn(
            ValidationCode.NOT_IN_PICKLIST,
            f"{text!r} differs from the ETIM spelling {allowed.text!r}",
        )
    if value_id is not None and value_id != allowed.value_id:
        issues.error(
            ValidationCode.VALUE_ID_MISMATCH,
            f"value_id {value_id!r} does not match {allowed.text!r} ({allowed.value_id})",
        )


# ---------------------------------------------------------------------------------
# Raw payload -> typed, canonical value
# ---------------------------------------------------------------------------------


def build_value(
    etim_class: EtimClass, feature_id: str, raw: RawFeatureValue
) -> tuple[AttributeValue | None, ValidationResult]:
    """Turn an extraction payload into a canonical value, or refuse with reasons.

    Returns `(None, result)` on any error. A caller that receives `None` must
    withhold the attribute; there is no partially-valid outcome.
    """
    feature, result = resolve_feature(etim_class, feature_id)
    if feature is None:
        return None, result

    issues = _Issues(feature_id)
    builder = {
        EtimFeatureType.NUMERIC: _build_numeric,
        EtimFeatureType.RANGE: _build_range,
        EtimFeatureType.ALPHANUMERIC: _build_alphanumeric,
        EtimFeatureType.LOGICAL: _build_logical,
    }[feature.feature_type]
    value = builder(issues, feature, raw)
    outcome = issues.result()
    if not outcome.ok:
        return None, outcome
    return value, outcome


def _converted_unit(
    issues: _Issues, feature: EtimFeature, raw_unit: str | None
) -> str | None:
    """Validate the source unit against the ETIM unit. Returns the target unit."""
    if feature.unit is None:
        if raw_unit is not None:
            issues.error(
                ValidationCode.UNEXPECTED_UNIT,
                f"ETIM defines no unit for this feature, extraction reported {raw_unit!r}",
            )
        return None
    if raw_unit is None:
        issues.error(
            ValidationCode.MISSING_UNIT,
            f"ETIM mandates unit {feature.unit!r}; the source unit must be read from the "
            "document, never assumed",
        )
        return None
    if not units.is_known(raw_unit):
        issues.error(
            ValidationCode.UNKNOWN_UNIT,
            f"{raw_unit!r} is not in the reviewed unit registry",
        )
        return None
    try:
        if units.dimension_of(raw_unit) != units.dimension_of(feature.unit):
            issues.error(
                ValidationCode.INCOMPATIBLE_UNIT,
                f"{raw_unit!r} ({units.dimension_of(raw_unit)}) cannot be converted to "
                f"{feature.unit!r} ({units.dimension_of(feature.unit)})",
            )
            return None
    except units.UnknownUnit as exc:  # ETIM unit outside the registry
        issues.error(ValidationCode.UNKNOWN_UNIT, str(exc))
        return None
    return feature.unit


def _build_numeric(
    issues: _Issues, feature: EtimFeature, raw: RawFeatureValue
) -> NumericValue | None:
    if raw.number is None:
        issues.error(ValidationCode.MALFORMED_PAYLOAD, "numeric feature requires `number`")
        return None
    _check_finite(issues, raw.number)
    target = _converted_unit(issues, feature, raw.unit)
    if not issues.result().ok:
        return None

    value = NumericValue(raw=raw.raw_text, number=raw.number, unit=raw.unit)
    if target is None:
        return value
    try:
        return units.normalize_numeric(value, target)
    except units.UnsupportedConversion as exc:
        issues.error(ValidationCode.UNSUPPORTED_UNIT_CONVERSION, str(exc))
    except units.UnitError as exc:  # pragma: no cover - guarded above
        issues.error(ValidationCode.INCOMPATIBLE_UNIT, str(exc))
    return None


def _build_range(issues: _Issues, feature: EtimFeature, raw: RawFeatureValue) -> RangeValue | None:
    if raw.minimum is None or raw.maximum is None:
        issues.error(
            ValidationCode.MALFORMED_PAYLOAD, "range feature requires `minimum` and `maximum`"
        )
        return None
    _check_finite(issues, raw.minimum)
    _check_finite(issues, raw.maximum)
    if raw.minimum > raw.maximum:
        issues.error(
            ValidationCode.RANGE_INVERTED,
            f"range minimum {raw.minimum:g} exceeds maximum {raw.maximum:g}",
        )
    target = _converted_unit(issues, feature, raw.unit)
    if not issues.result().ok:
        return None

    value = RangeValue(
        raw=raw.raw_text, minimum=raw.minimum, maximum=raw.maximum, unit=raw.unit
    )
    if target is None:
        return value
    try:
        return units.normalize_range(value, target)
    except units.UnsupportedConversion as exc:
        issues.error(ValidationCode.UNSUPPORTED_UNIT_CONVERSION, str(exc))
    except units.UnitError as exc:  # pragma: no cover - guarded above
        issues.error(ValidationCode.INCOMPATIBLE_UNIT, str(exc))
    return None


def _build_alphanumeric(
    issues: _Issues, feature: EtimFeature, raw: RawFeatureValue
) -> AlphanumericValue | None:
    if raw.text is None or not raw.text.strip():
        issues.error(ValidationCode.MALFORMED_PAYLOAD, "alphanumeric feature requires `text`")
        return None
    if raw.unit is not None:
        issues.error(
            ValidationCode.UNEXPECTED_UNIT, f"alphanumeric feature carries unit {raw.unit!r}"
        )
        return None
    if not feature.allowed_values:
        return AlphanumericValue(raw=raw.raw_text, text=raw.text.strip())

    allowed = feature.find_allowed(raw.text)
    if allowed is None:
        issues.error(
            ValidationCode.NOT_IN_PICKLIST,
            f"{raw.text!r} is not an allowed value; ETIM permits "
            f"{', '.join(repr(t) for t in feature.allowed_texts())}",
        )
        return None
    derivation = Derivation()
    if raw.text != allowed.text:
        # Case and spacing folded onto ETIM's own spelling. A representation change,
        # recorded as one, not a silent rewrite of what the source said.
        derivation = Derivation(
            kind=DerivationKind.ENUM_MAP,
            transform_id=ENUM_MAP_TRANSFORM,
            detail=f"{raw.text!r} -> ETIM value {allowed.text!r} ({allowed.value_id})",
        )
    return AlphanumericValue(
        raw=raw.raw_text,
        text=allowed.text,
        value_id=allowed.value_id,
        derivation=derivation,
    )


def _build_logical(
    issues: _Issues, feature: EtimFeature, raw: RawFeatureValue
) -> LogicalValue | None:
    if raw.boolean is None:
        issues.error(ValidationCode.MALFORMED_PAYLOAD, "logical feature requires `boolean`")
        return None
    if raw.unit is not None:
        issues.error(
            ValidationCode.UNEXPECTED_UNIT, f"logical feature carries unit {raw.unit!r}"
        )
        return None
    return LogicalValue(raw=raw.raw_text, boolean=raw.boolean)


# ---------------------------------------------------------------------------------
# Condition completeness
# ---------------------------------------------------------------------------------


def resolve_conditions(
    config: DemoClassConfig | None, feature_id: str, conditions: ConditionSet
) -> ConditionSet:
    """Derive `completeness` and `missing_kinds` from the reviewed qualifier rule.

    **Whatever completeness the caller supplied is overwritten.** A model may propose
    conditions; it may not rule on whether its own conditions are complete, because
    that is the judgement the support grade turns on.

    * COMPLETE — a rule exists and every required kind is bound. `ConditionSet`
      already guarantees each kind is bound at most once, so "present" is "present
      exactly once" by construction.
    * PARTIAL — a rule exists and one or more required kinds are absent, listed
      deterministically in `missing_kinds`.
    * UNKNOWN — no reviewed rule for this feature, so no defensible claim either way.
    """
    rule = config.rule_for(feature_id) if config is not None else None
    if rule is None:
        return conditions.model_copy(
            update={"completeness": ConditionCompleteness.UNKNOWN, "missing_kinds": ()}
        )
    present = {c.kind for c in conditions.conditions}
    missing = tuple(k for k in rule.required_kinds if k not in present)
    return conditions.model_copy(
        update={
            "completeness": (
                ConditionCompleteness.PARTIAL if missing else ConditionCompleteness.COMPLETE
            ),
            "missing_kinds": missing,
        }
    )


def validate_conditions(
    config: DemoClassConfig | None, feature_id: str, conditions: ConditionSet
) -> ValidationResult:
    """Report missing required qualifiers and values bound to the wrong operating point.

    Run against a set already passed through `resolve_conditions`; this reports, it
    does not derive.
    """
    issues = _Issues(feature_id)
    rule = config.rule_for(feature_id) if config is not None else None
    if rule is None:
        issues.warn(
            ValidationCode.NO_QUALIFIER_RULE,
            "no reviewed qualifier rule for this feature; condition completeness is UNKNOWN",
        )
        return issues.result()

    for kind in rule.required_kinds:
        if conditions.get(kind) is None:
            issues.error(
                ValidationCode.CONDITIONS_INCOMPLETE,
                f"required qualifier {kind.value} is not bound",
            )

    for kind, expected in rule.expected:
        bound = conditions.get(kind)
        if bound is None:
            continue  # already reported as incomplete
        if bound.value.casefold() != expected.casefold():
            issues.error(
                ValidationCode.CONDITION_VALUE_MISMATCH,
                f"{kind.value} is {bound.value!r}, but this ETIM feature is defined at "
                f"{expected!r}; the value belongs to a different feature",
            )
    return issues.result()


def expected_condition_set(
    config: DemoClassConfig | None, feature_id: str
) -> ConditionSet | None:
    """The operating point the ETIM feature itself fixes, when one is reviewed.

    Useful to pre-fill the qualifiers extraction should be looking for, without
    letting the model decide what they are.
    """
    rule = config.rule_for(feature_id) if config is not None else None
    if rule is None or not rule.expected:
        return None
    return ConditionSet(
        conditions=tuple(Condition(kind=k, value=v) for k, v in rule.expected),
        completeness=ConditionCompleteness.UNKNOWN,
    )
