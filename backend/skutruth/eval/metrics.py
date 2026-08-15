"""Metric primitives.

One rule governs this module: **a ratio never travels without its counts.**

"98% precision" is unfalsifiable. It could be 49/50 or 490/500, and it could be 1/1
dressed up to look like a result. Every ratio here carries its numerator and
denominator all the way into the serialized report, and rounding is left to whatever
finally prints it.

The second rule follows from the first: an empty denominator produces `rate = None`,
never 0% and never 100%. A system that measured nothing has not scored zero, and a
system that abstained from everything has not scored perfectly.
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Ratio(BaseModel):
    """A measured proportion that always shows its working."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    numerator: int = Field(ge=0)
    denominator: int = Field(ge=0)

    @model_validator(mode="after")
    def _numerator_fits(self) -> Ratio:
        if self.numerator > self.denominator:
            raise ValueError(
                f"numerator {self.numerator} exceeds denominator {self.denominator}; "
                "a ratio that counted more successes than attempts is a scoring bug"
            )
        return self

    @property
    def rate(self) -> float | None:
        """The proportion, or `None` when nothing was measured."""
        if self.denominator == 0:
            return None
        return self.numerator / self.denominator

    @property
    def is_measured(self) -> bool:
        return self.denominator > 0

    def complement(self) -> Ratio:
        """The same measurement counted the other way round."""
        return Ratio(numerator=self.denominator - self.numerator, denominator=self.denominator)

    def display(self) -> str:
        if self.denominator == 0:
            return "n/a (0 evaluated)"
        return f"{self.numerator}/{self.denominator} = {self.rate:.1%}"

    def __str__(self) -> str:  # pragma: no cover - convenience
        return self.display()


@dataclass
class Tally:
    """Mutable counter that becomes a `Ratio`. Scorers accumulate into these."""

    numerator: int = 0
    denominator: int = 0

    def add(self, *, correct: bool) -> None:
        self.denominator += 1
        if correct:
            self.numerator += 1

    def add_denominator_only(self) -> None:
        """Count an attempt that could not succeed — a crash, a miss, an abstention.

        The anti-cherry-pick primitive: a case that failed still occupies the
        denominator wherever it logically attempted something.
        """
        self.denominator += 1

    def to_ratio(self) -> Ratio:
        return Ratio(numerator=self.numerator, denominator=self.denominator)


class LatencySummary(BaseModel):
    """Latency over a sample, with percentiles suppressed when the sample is too small.

    `p50` and `p95` are `None` below `MIN_SAMPLE_FOR_PERCENTILES`. A p95 over four
    observations is the maximum wearing a statistical costume, and reporting it would
    invite exactly the over-reading this framework exists to prevent.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    MIN_SAMPLE_FOR_PERCENTILES: int = 5

    count: int = Field(ge=0)
    total_seconds: float = Field(ge=0.0)
    mean_seconds: float | None = None
    p50_seconds: float | None = None
    p95_seconds: float | None = None

    @classmethod
    def from_samples(cls, samples: list[float]) -> LatencySummary:
        ordered = sorted(s for s in samples if s is not None)
        n = len(ordered)
        if n == 0:
            return cls(count=0, total_seconds=0.0)
        total = sum(ordered)
        p50 = p95 = None
        if n >= cls.model_fields["MIN_SAMPLE_FOR_PERCENTILES"].default:
            p50 = _percentile(ordered, 0.50)
            p95 = _percentile(ordered, 0.95)
        return cls(
            count=n,
            total_seconds=total,
            mean_seconds=total / n,
            p50_seconds=p50,
            p95_seconds=p95,
        )


def _percentile(ordered: list[float], q: float) -> float:
    """Nearest-rank percentile. Deterministic, and no interpolation to argue about."""
    if not ordered:  # pragma: no cover - guarded by caller
        raise ValueError("percentile of an empty sample")
    import math

    rank = max(1, math.ceil(q * len(ordered)))
    return ordered[rank - 1]
