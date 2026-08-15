"""Typed attribute values, one variant per ETIM feature type, plus derivation lineage.

FROZEN CONTRACT — see contracts/README.md before changing anything here.

Every value carries `raw`, the text as it appeared in the source, and a `Derivation`
recording how the normalized form was produced from it. A normalized value does not
need its own quote — `18 A` derived from a source that said `18000 mA` is supported by
the quote for `18000 mA` plus a deterministic, versioned transform. Lineage, not a
second quote, is what makes the normalized value defensible.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import DerivationKind, EtimFeatureType


class Derivation(BaseModel):
    """How a normalized value was produced from raw source text.

    `transform_id` is versioned so that a re-run can prove it applied the same rule.
    No language model participates in any derivation.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: DerivationKind = DerivationKind.VERBATIM
    transform_id: str = Field(
        default="verbatim@v1",
        description="Versioned identifier of the deterministic transform applied",
    )
    detail: str | None = Field(
        default=None, description="Human-readable trace, e.g. '18000 mA -> 18 A (x1e-3)'"
    )

    @model_validator(mode="after")
    def _non_verbatim_explains_itself(self) -> Derivation:
        if self.kind is not DerivationKind.VERBATIM and not self.detail:
            raise ValueError(f"derivation {self.kind} must record a `detail` trace")
        return self

    @property
    def is_verbatim(self) -> bool:
        return self.kind is DerivationKind.VERBATIM


VERBATIM = Derivation()


#: Decimal places used when reducing a float to a comparison key. Product data is
#: quoted to a handful of significant figures, so this only absorbs float-repr noise.
_NUMERIC_PRECISION = 9


class _ValueBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw: str = Field(min_length=1, description="Verbatim value text from the source")
    derivation: Derivation = VERBATIM

    def display(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError

    def semantic_key(self) -> tuple:  # pragma: no cover - overridden
        """The value stripped of presentation, for agreement checks.

        Two observations agree when their semantic keys match. `raw` and `derivation`
        are excluded, so `18 A` and `18.0 A` are one claim however each source wrote
        it. The **unit is part of the key**: `18 A` and `18 mA` do not agree here.
        Reconciling those is normalisation's job, and it happens before grouping —
        an evidence group compares values that are already in ETIM's unit.
        """
        raise NotImplementedError

    def agrees_with(self, other: AttributeValue) -> bool:
        return self.semantic_key() == other.semantic_key()


class NumericValue(_ValueBase):
    kind: Literal["numeric"] = "numeric"
    number: float
    unit: str | None = Field(default=None, description="ETIM UNITDESC, e.g. 'A', 'kW', 'mm'")

    def display(self) -> str:
        n = f"{self.number:g}"
        return f"{n} {self.unit}" if self.unit else n

    def semantic_key(self) -> tuple:
        return ("numeric", round(self.number, _NUMERIC_PRECISION), self.unit)


class RangeValue(_ValueBase):
    kind: Literal["range"] = "range"
    minimum: float
    maximum: float
    unit: str | None = None

    @model_validator(mode="after")
    def _min_le_max(self) -> RangeValue:
        # Definitional, not physical: an ETIM range with min > max is malformed by
        # construction. This is the only class of constraint we assert -- no
        # cross-attribute engineering formulas are used as truth validators.
        if self.minimum > self.maximum:
            raise ValueError(f"range minimum {self.minimum} exceeds maximum {self.maximum}")
        return self

    def display(self) -> str:
        span = f"{self.minimum:g}–{self.maximum:g}"
        return f"{span} {self.unit}" if self.unit else span

    def semantic_key(self) -> tuple:
        return (
            "range",
            round(self.minimum, _NUMERIC_PRECISION),
            round(self.maximum, _NUMERIC_PRECISION),
            self.unit,
        )


class AlphanumericValue(_ValueBase):
    """A picklist selection. `value_id` is the ETIM EVxxxxxxx code when known."""

    kind: Literal["alphanumeric"] = "alphanumeric"
    text: str = Field(min_length=1)
    value_id: str | None = None

    def display(self) -> str:
        return self.text

    def semantic_key(self) -> tuple:
        # The ETIM value id is authoritative when present; the text is a label for it.
        return ("alphanumeric", self.value_id or self.text.casefold())


class LogicalValue(_ValueBase):
    kind: Literal["logical"] = "logical"
    boolean: bool

    def display(self) -> str:
        return "Yes" if self.boolean else "No"

    def semantic_key(self) -> tuple:
        return ("logical", self.boolean)


AttributeValue = Annotated[
    NumericValue | RangeValue | AlphanumericValue | LogicalValue,
    Field(discriminator="kind"),
]

#: Which value variant each ETIM feature type must produce. Enforced by
#: `ProductAttribute`, so a model cannot return a string for a numeric feature.
VALUE_KIND_FOR_FEATURE_TYPE: dict[EtimFeatureType, str] = {
    EtimFeatureType.NUMERIC: "numeric",
    EtimFeatureType.RANGE: "range",
    EtimFeatureType.ALPHANUMERIC: "alphanumeric",
    EtimFeatureType.LOGICAL: "logical",
}
