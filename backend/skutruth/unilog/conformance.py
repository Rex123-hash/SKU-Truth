"""Schema conformance, reported issue by issue.

Deliberately not a single "invalid schema" boolean. When an export is rejected the
operator needs to know *which* column is missing, *which* triplet is broken, and whether
the order drifted — those have different causes and different fixes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from .schema import DeliverySchema


class ConformanceCode(StrEnum):
    """What went wrong. One code per distinguishable cause."""

    FIELD_COUNT_MISMATCH = "FIELD_COUNT_MISMATCH"
    MISSING_HEADER = "MISSING_HEADER"
    UNEXPECTED_HEADER = "UNEXPECTED_HEADER"
    DUPLICATE_HEADER = "DUPLICATE_HEADER"
    ORDER_MISMATCH = "ORDER_MISMATCH"
    FINGERPRINT_MISMATCH = "FINGERPRINT_MISMATCH"
    ROW_WIDTH_MISMATCH = "ROW_WIDTH_MISMATCH"


@dataclass(frozen=True, slots=True)
class ConformanceIssue:
    code: ConformanceCode
    detail: str


@dataclass(frozen=True, slots=True)
class ConformanceReport:
    """The outcome of comparing an actual schema or row set against the contract."""

    expected_field_count: int
    actual_field_count: int
    issues: tuple[ConformanceIssue, ...] = field(default_factory=tuple)

    @property
    def ok(self) -> bool:
        return not self.issues

    def codes(self) -> tuple[ConformanceCode, ...]:
        return tuple(i.code for i in self.issues)

    def summary(self) -> str:
        if self.ok:
            return f"conforms: {self.actual_field_count} fields"
        return f"{len(self.issues)} issue(s): " + ", ".join(
            sorted({i.code.value for i in self.issues})
        )


def check_schema(actual: DeliverySchema, expected: DeliverySchema) -> ConformanceReport:
    """Compare a loaded schema against the contract it is supposed to satisfy."""
    issues: list[ConformanceIssue] = []

    if actual.field_count != expected.field_count:
        issues.append(
            ConformanceIssue(
                ConformanceCode.FIELD_COUNT_MISMATCH,
                f"expected {expected.field_count} columns, found {actual.field_count}",
            )
        )

    expected_set, actual_set = set(expected.headers), set(actual.headers)
    for missing in sorted(expected_set - actual_set):
        issues.append(
            ConformanceIssue(ConformanceCode.MISSING_HEADER, f"missing column {missing!r}")
        )
    for extra in sorted(actual_set - expected_set):
        issues.append(
            ConformanceIssue(ConformanceCode.UNEXPECTED_HEADER, f"unexpected column {extra!r}")
        )

    # Same names, different sequence: the contract says do not reorder.
    if expected_set == actual_set and actual.headers != expected.headers:
        first = next(
            i
            for i, (a, b) in enumerate(zip(actual.headers, expected.headers, strict=False))
            if a != b
        )
        issues.append(
            ConformanceIssue(
                ConformanceCode.ORDER_MISMATCH,
                f"column order diverges at position {first}: expected "
                f"{expected.headers[first]!r}, found {actual.headers[first]!r}",
            )
        )

    if not actual.matches(expected):
        issues.append(
            ConformanceIssue(
                ConformanceCode.FINGERPRINT_MISMATCH,
                f"schema fingerprint {actual.fingerprint()[:12]}… does not match the "
                f"expected {expected.fingerprint()[:12]}…",
            )
        )

    return ConformanceReport(
        expected_field_count=expected.field_count,
        actual_field_count=actual.field_count,
        issues=tuple(issues),
    )


def check_rows(rows: list[list[str]], schema: DeliverySchema) -> ConformanceReport:
    """Every exported row must be exactly as wide as the contract."""
    issues = [
        ConformanceIssue(
            ConformanceCode.ROW_WIDTH_MISMATCH,
            f"row {n} has {len(row)} fields, expected {schema.field_count}",
        )
        for n, row in enumerate(rows, start=1)
        if len(row) != schema.field_count
    ]
    return ConformanceReport(
        expected_field_count=schema.field_count,
        actual_field_count=schema.field_count,
        issues=tuple(issues),
    )


__all__ = [
    "ConformanceCode",
    "ConformanceIssue",
    "ConformanceReport",
    "check_rows",
    "check_schema",
]
