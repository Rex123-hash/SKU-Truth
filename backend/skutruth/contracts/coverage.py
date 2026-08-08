"""Coverage reporting.

FROZEN CONTRACT — see contracts/README.md before changing anything here.

ETIM feature coverage is not business completeness. ETIM features characterize a
class; they are not a mandatory field list for a commerce channel, and a feature that
does not apply to a product is not a gap. Reporting `accepted / all ETIM features`
would penalise inapplicable fields and reward filling them.

So there are four separate numbers, and the buyer-facing one counts only fields that
are applicable, buyer-critical, and accepted with verified support.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CoverageReport(BaseModel):
    """Coverage counted four ways, with raw numerators and denominators kept."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    etim_class_id: str | None = None

    etim_features_total: int = Field(ge=0, description="Features ETIM maps to the class")
    applicable_total: int = Field(ge=0, description="Of those, judged APPLICABLE")
    not_applicable_total: int = Field(ge=0)
    applicability_unknown_total: int = Field(ge=0)

    accepted_total: int = Field(ge=0, description="Applicable features with an accepted value")

    buyer_critical_total: int = Field(
        ge=0, description="Hand-reviewed buyer-critical subset size for this class"
    )
    buyer_critical_applicable: int = Field(ge=0)
    buyer_critical_accepted: int = Field(ge=0)

    @model_validator(mode="after")
    def _counts_are_consistent(self) -> CoverageReport:
        parts = self.applicable_total + self.not_applicable_total + self.applicability_unknown_total
        if parts != self.etim_features_total:
            raise ValueError(
                f"applicability split ({parts}) does not sum to etim_features_total "
                f"({self.etim_features_total})"
            )
        if self.accepted_total > self.applicable_total:
            raise ValueError("accepted_total exceeds applicable_total")
        if self.buyer_critical_applicable > self.buyer_critical_total:
            raise ValueError("buyer_critical_applicable exceeds buyer_critical_total")
        if self.buyer_critical_accepted > self.buyer_critical_applicable:
            raise ValueError("buyer_critical_accepted exceeds buyer_critical_applicable")
        return self

    @property
    def etim_feature_coverage(self) -> float | None:
        """Diagnostic only. Never present this as business completeness."""
        if self.applicable_total == 0:
            return None
        return self.accepted_total / self.applicable_total

    @property
    def buyer_critical_coverage(self) -> float | None:
        """The buyer-facing number: accepted, applicable, buyer-critical fields."""
        if self.buyer_critical_applicable == 0:
            return None
        return self.buyer_critical_accepted / self.buyer_critical_applicable

    def summary(self) -> str:
        bc = self.buyer_critical_coverage
        bc_txt = (
            "n/a"
            if bc is None
            else f"{self.buyer_critical_accepted}/{self.buyer_critical_applicable}"
        )
        return (
            f"buyer-critical {bc_txt} · "
            f"ETIM applicable {self.accepted_total}/{self.applicable_total} · "
            f"not applicable {self.not_applicable_total}"
        )
