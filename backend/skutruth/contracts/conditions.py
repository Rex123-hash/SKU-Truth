"""Structured operating-point qualifiers.

FROZEN CONTRACT — see contracts/README.md before changing anything here.

Conditions are first-class data, not text inside a feature label. This is what
lets the system see that a contactor rated `18 A` and `32 A` is not contradicting
itself: those are its AC-3 and AC-1 ratings. Comparing values across different
condition keys is a category error, and the type system makes that visible.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .enums import ConditionCompleteness, ConditionKind


class Condition(BaseModel):
    """One bound qualifier, e.g. utilization category = AC-3."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: ConditionKind
    value: str = Field(min_length=1, description="Normalized qualifier, e.g. 'AC-3', '400 V'")
    raw: str | None = Field(default=None, description="Qualifier text as the source wrote it")

    def key(self) -> tuple[str, str]:
        return (self.kind.value, self.value.casefold())

    def display(self) -> str:
        return f"{self.value}"


class ConditionSet(BaseModel):
    """The full operating point a value is stated under.

    `completeness` records whether every qualifier the ETIM feature requires has
    actually been bound. A value whose conditions are only PARTIAL can still be
    accepted, but it cannot reach the top support grade — we do not know exactly
    what it is a measurement of.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    conditions: tuple[Condition, ...] = ()
    completeness: ConditionCompleteness = ConditionCompleteness.UNKNOWN
    missing_kinds: tuple[ConditionKind, ...] = Field(
        default=(),
        description="Qualifiers the feature requires that no source bound. Drives PARTIAL.",
    )

    def get(self, kind: ConditionKind) -> Condition | None:
        for c in self.conditions:
            if c.kind is kind:
                return c
        return None

    def key(self) -> tuple[tuple[str, str], ...]:
        """Order-independent identity of this operating point.

        Two observations may only be compared for factual agreement when their keys
        are equal. Anything else is a QUALIFIER difference, not a conflict.
        """
        return tuple(sorted(c.key() for c in self.conditions))

    def describes_same_operating_point_as(self, other: ConditionSet) -> bool:
        return self.key() == other.key()

    # -- compatibility for corroboration ---------------------------------------
    #
    # Equality of `key()` is the right test for "is this the same operating point".
    # It is the wrong test for "may these two observations corroborate each other",
    # because real sources omit qualifiers they consider obvious: a datasheet row
    # headed `AC-3 400 V` and a distributor table that says only `AC-3` are describing
    # the same rating, and refusing to group them would be pedantry, not rigour.
    #
    # The smallest defensible rule is therefore *clash detection*, not equality:
    #
    #     compatible(a, b)  <=>  for every ConditionKind present in BOTH,
    #                            a and b agree on its value
    #
    # A qualifier present in one and absent from the other is tolerated. A qualifier
    # present in both with different values is a hard incompatibility. That rejects
    # the case this rule exists for -- AC-3 and AC-1 cannot corroborate each other --
    # while tolerating the far more common case of an under-specified source.
    #
    # Tolerating an omission is safe here because it cannot manufacture support: an
    # under-specified evidence set leaves `completeness` short of COMPLETE, which
    # caps the support grade below A on its own.

    def conflicting_kinds(self, other: ConditionSet) -> tuple[ConditionKind, ...]:
        """Kinds bound by both sets to different values. Empty means compatible."""
        mine = {c.kind: c.value.casefold() for c in self.conditions}
        theirs = {c.kind: c.value.casefold() for c in other.conditions}
        return tuple(
            sorted(
                (kind for kind in mine.keys() & theirs.keys() if mine[kind] != theirs[kind]),
                key=lambda k: k.value,
            )
        )

    def is_compatible_with(self, other: ConditionSet) -> bool:
        """True when no qualifier bound by both sets disagrees."""
        return not self.conflicting_kinds(other)

    def supports(self, claimed: ConditionSet) -> bool:
        """True when every qualifier `claimed` asserts is bound identically here.

        Stricter than `is_compatible_with`, and used where an attribute claims an
        operating point: the claim must be *stated* by evidence, not merely
        un-contradicted by it.
        """
        mine = {c.kind: c.value.casefold() for c in self.conditions}
        return all(mine.get(c.kind) == c.value.casefold() for c in claimed.conditions)

    @property
    def is_complete(self) -> bool:
        return self.completeness is ConditionCompleteness.COMPLETE

    def display(self) -> str:
        if not self.conditions:
            return "no conditions recorded"
        return " · ".join(c.display() for c in self.conditions)

    def __bool__(self) -> bool:
        return bool(self.conditions)
