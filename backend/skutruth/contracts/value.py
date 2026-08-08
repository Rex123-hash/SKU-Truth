"""Typed attribute values, one variant per ETIM feature type.

FROZEN CONTRACT — see contracts/README.md before changing anything here.

Every value carries `raw`, the text as it appeared in the source, alongside the
normalised form. Normalisation is deterministic and reversible-by-inspection:
a reviewer can always see what the document said and what we turned it into.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import EtimFeatureType


class _ValueBase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    raw: str = Field(min_length=1, description="Verbatim value text from the source")

    def display(self) -> str:  # pragma: no cover - overridden
        raise NotImplementedError


class NumericValue(_ValueBase):
    kind: Literal["numeric"] = "numeric"
    number: float
    unit: str | None = Field(default=None, description="ETIM UNITDESC, e.g. 'A', 'kW', 'mm'")

    def display(self) -> str:
        n = f"{self.number:g}"
        return f"{n} {self.unit}" if self.unit else n


class RangeValue(_ValueBase):
    kind: Literal["range"] = "range"
    minimum: float
    maximum: float
    unit: str | None = None

    @model_validator(mode="after")
    def _min_le_max(self) -> RangeValue:
        # Definitional, not physical: an ETIM range with min > max is malformed by construction.
        if self.minimum > self.maximum:
            raise ValueError(f"range minimum {self.minimum} exceeds maximum {self.maximum}")
        return self

    def display(self) -> str:
        span = f"{self.minimum:g}–{self.maximum:g}"
        return f"{span} {self.unit}" if self.unit else span


class AlphanumericValue(_ValueBase):
    """A picklist selection. `value_id` is the ETIM EVxxxxxxx code when known."""

    kind: Literal["alphanumeric"] = "alphanumeric"
    text: str = Field(min_length=1)
    value_id: str | None = None

    def display(self) -> str:
        return self.text


class LogicalValue(_ValueBase):
    kind: Literal["logical"] = "logical"
    boolean: bool

    def display(self) -> str:
        return "Yes" if self.boolean else "No"


AttributeValue = Annotated[
    NumericValue | RangeValue | AlphanumericValue | LogicalValue,
    Field(discriminator="kind"),
]

#: Which value variant each ETIM feature type must produce. Enforced by the
#: deterministic validator, so a model cannot return a string for a numeric feature.
VALUE_KIND_FOR_FEATURE_TYPE: dict[EtimFeatureType, str] = {
    EtimFeatureType.NUMERIC: "numeric",
    EtimFeatureType.RANGE: "range",
    EtimFeatureType.ALPHANUMERIC: "alphanumeric",
    EtimFeatureType.LOGICAL: "logical",
}
