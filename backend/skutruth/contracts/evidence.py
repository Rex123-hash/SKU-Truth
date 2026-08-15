"""Artifacts, evidence, locators, and conflicts.

FROZEN CONTRACT — see contracts/README.md before changing anything here.

The load-bearing idea: an accepted value must trace to a *span we located ourselves*
in an artifact we ingested and hashed. Search grounding and URL Context are discovery
signals — they tell us where to look. They do not establish page-level provenance,
so `DiscoveryMethod` and `EvidenceVerification` are separate fields and only the
latter can license acceptance.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .conditions import ConditionSet
from .enums import (
    ConflictCause,
    DiscoveryMethod,
    EvidenceModality,
    EvidenceVerification,
    IdentityScope,
    ResolvedBy,
    RunMode,
    SourceType,
)
from .value import AttributeValue


def _same_raw_text(a: str, b: str) -> bool:
    """Whitespace-insensitive comparison of two source fragments.

    Case is significant: `mA` and `MA` are different units, and a comparison that
    folded them would defeat the point of anchoring a derivation to source text.
    """
    return "".join(a.split()) == "".join(b.split())


class SourceArtifact(BaseModel):
    """A document we ingested, hashed, and can re-open at a given page.

    `final_url` is the artifact's own URL after redirects, which is frequently not
    the URL a search citation pointed at. Both are kept: `discovery_url` records how
    we got here, `final_url` records what we actually read.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    artifact_id: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    final_url: str
    discovery_url: str | None = None
    discovery_method: DiscoveryMethod
    publisher: str | None = None
    source_type: SourceType
    media_type: str = Field(default="application/pdf")
    page_count: int | None = Field(default=None, ge=1)
    retrieved_at: datetime
    document_version: str | None = Field(
        default=None, description="Publisher's own revision/date marking, when stated"
    )
    identity_scope: IdentityScope = Field(
        description="Whether this artifact covers one exact reference, a family, or a range"
    )
    covers_mpn: str | None = Field(
        default=None,
        description="The commercial reference this artifact is about, when it names one. "
        "Distinct exact-SKU artifacts are how invariance across a family is proven.",
    )


class SpanLocator(BaseModel):
    """Where inside an artifact the fragment lives.

    Designed for tables, not only prose. A datasheet specification is usually a cell
    in a row, and forcing it through a prose-quote shape loses the row context that
    makes it meaningful. Character offsets are recorded when text extraction is
    reliable; a bounding box is recorded when it is not.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int | None = Field(default=None, ge=1, description="1-indexed page")
    section: str | None = Field(default=None, description="Heading or table caption")

    table_index: int | None = Field(default=None, ge=0)
    row_index: int | None = Field(default=None, ge=0)
    row_header: str | None = Field(default=None, description="e.g. 'Rated operational current Ie'")
    column_index: int | None = Field(default=None, ge=0)
    column_header: str | None = Field(default=None, description="e.g. 'AC-3 400 V'")

    char_start: int | None = Field(default=None, ge=0, description="Offset into page text")
    char_end: int | None = Field(default=None, ge=0)
    bbox: tuple[float, float, float, float] | None = Field(
        default=None, description="(x0, y0, x1, y1) in PDF points; used for highlighting"
    )

    @model_validator(mode="after")
    def _offsets_ordered(self) -> SpanLocator:
        if (
            self.char_start is not None
            and self.char_end is not None
            and self.char_end < self.char_start
        ):
            raise ValueError("char_end precedes char_start")
        return self

    @property
    def is_tabular(self) -> bool:
        return self.table_index is not None or self.row_header is not None

    def human(self) -> str:
        bits: list[str] = []
        if self.page is not None:
            bits.append(f"p.{self.page}")
        if self.section:
            bits.append(self.section)
        if self.row_header:
            bits.append(f"row “{self.row_header}”")
        if self.column_header:
            bits.append(f"col “{self.column_header}”")
        return " · ".join(bits) if bits else "location not recorded"


class Evidence(BaseModel):
    """One observation of one value, in one region of one ingested artifact.

    `raw_fragment` is what the source literally contains — a prose sentence, or a
    flattened table row. `normalized_quote` is the whitespace- and typography-
    normalized form that span verification actually matched against; keeping both
    means a reviewer sees the source's own words while the machine check stays exact.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_id: str
    artifact: SourceArtifact
    locator: SpanLocator = Field(default_factory=SpanLocator)

    raw_fragment: str = Field(min_length=1, description="Verbatim source text or table row")
    normalized_quote: str = Field(min_length=1, description="What span verification matched")
    modality: EvidenceModality
    verification: EvidenceVerification
    match_score: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Similarity when FUZZY_OCR_SPAN"
    )

    observed_value: AttributeValue
    conditions: ConditionSet = Field(default_factory=ConditionSet)

    proves_family_scope: bool = Field(
        default=False,
        description="The span itself shows the value holds across the family — a variant "
        "table row spanning every child, or an explicit 'all variants' statement. False "
        "for a family document that merely happens to list one child's value.",
    )

    # Reproducibility trail: enough to re-run this exact extraction.
    extraction_model: str
    prompt_version: str
    schema_version: str
    run_mode: RunMode
    run_id: str

    @model_validator(mode="after")
    def _verified_spans_are_locatable(self) -> Evidence:
        if self.verification is not EvidenceVerification.UNVERIFIED and self.locator.page is None:
            raise ValueError(
                f"{self.verification} claims the span was located, but no page is recorded; "
                "a span we cannot re-open is not verified"
            )
        return self

    @model_validator(mode="after")
    def _fuzzy_spans_report_their_score(self) -> Evidence:
        if self.verification is EvidenceVerification.FUZZY_OCR_SPAN and self.match_score is None:
            raise ValueError("FUZZY_OCR_SPAN must record the match_score it was accepted at")
        return self

    @property
    def may_support_accepted_value(self) -> bool:
        return self.verification.may_support_accepted_value

    @property
    def source_type(self) -> SourceType:
        return self.artifact.source_type

    @property
    def identity_scope(self) -> IdentityScope:
        return self.artifact.identity_scope


class EvidenceGroup(BaseModel):
    """Observations that corroborate one another: same value, compatible conditions.

    Both halves of that sentence are enforced. A group whose members disagree on the
    value is not corroboration, and a group that straddles two operating points is
    worse than useless — it would let an AC-3 rating and an AC-1 rating sit behind a
    single representative value, which is precisely the confusion that first-class
    conditions exist to prevent.

    P0 semantics remain deliberately shallow on *independence*: this groups agreeing
    observations so the drawer can show them together, and does **not** claim the
    members are independent sources. `origin_note` says only what we can defend, e.g.
    "3 URLs, likely the same manufacturer origin". Conservative evidence-root
    deduplication is P1, and until it exists, extra members never raise the grade.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    group_id: str = Field(min_length=1)
    representative_value: AttributeValue
    conditions: ConditionSet = Field(default_factory=ConditionSet)
    members: list[Evidence] = Field(min_length=1)
    origin_note: str | None = Field(
        default=None, description="e.g. 'likely same origin as the manufacturer datasheet'"
    )

    @model_validator(mode="after")
    def _members_agree_on_the_value(self) -> EvidenceGroup:
        key = self.representative_value.semantic_key()
        for member in self.members:
            if member.observed_value.semantic_key() != key:
                raise ValueError(
                    f"evidence {member.evidence_id} observed "
                    f"{member.observed_value.display()!r}, which does not corroborate the "
                    f"group's {self.representative_value.display()!r}; put disagreeing "
                    "observations in separate groups"
                )
        return self

    @model_validator(mode="after")
    def _members_share_a_compatible_operating_point(self) -> EvidenceGroup:
        """No qualifier may be bound to different values within one group.

        Checked pairwise as well as against the group's own conditions: clash-freedom
        is not transitive, so a member with no conditions could otherwise bridge an
        AC-3 member and an AC-1 member into a single group.
        """
        for member in self.members:
            clash = member.conditions.conflicting_kinds(self.conditions)
            if clash:
                raise ValueError(
                    f"evidence {member.evidence_id} disagrees with the group's operating "
                    f"point on {', '.join(k.value for k in clash)}"
                )
        for i, a in enumerate(self.members):
            for b in self.members[i + 1 :]:
                clash = a.conditions.conflicting_kinds(b.conditions)
                if clash:
                    raise ValueError(
                        f"evidence {a.evidence_id} and {b.evidence_id} describe different "
                        f"operating points ({', '.join(k.value for k in clash)}) and cannot "
                        "corroborate one another"
                    )
        return self

    def supports_value(self, value: AttributeValue) -> bool:
        """Whether this group speaks for `value`, directly or through a derivation.

        Two routes, and only two:

        * **Verbatim.** The group observed the same claim, compared semantically, so
          `18 A` and `18.0 A` match while `18 mA` does not.
        * **Deterministic derivation.** The accepted value was produced from this
          group's observation by a versioned transform. The link is that the accepted
          value carries the *source's own raw text* — `18 A` derived from a span that
          read `18000 mA` keeps `raw="18000 mA"`. A `Derivation` object on its own
          proves nothing; it has to be anchored to text a span actually contained.

        What this does not do is check the arithmetic of a conversion. Verifying that
        18000 mA really is 18 A needs a unit engine, which lives in the ETIM
        validators, not in the contract. What the contract can guarantee is that a
        derived value is traceable to a real observation rather than floating free.
        """
        if self.representative_value.agrees_with(value):
            return True
        if value.derivation.is_verbatim:
            return False
        return _same_raw_text(self.representative_value.raw, value.raw)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def best_member(self) -> Evidence:
        """The member a reviewer should see first: verified, exact-scope, most structured."""
        ver_rank = {
            EvidenceVerification.EXACT_SPAN: 0,
            EvidenceVerification.FUZZY_OCR_SPAN: 1,
            EvidenceVerification.UNVERIFIED: 2,
        }
        scope_rank = {
            IdentityScope.EXACT_SKU: 0,
            IdentityScope.FAMILY: 1,
            IdentityScope.RANGE: 2,
        }
        mod_rank = {
            EvidenceModality.STRUCTURED_API: 0,
            EvidenceModality.SPEC_TABLE: 1,
            EvidenceModality.SPEC_LINE: 2,
            EvidenceModality.PROSE: 3,
            EvidenceModality.IMAGE_OCR: 4,
            EvidenceModality.MARKETING: 5,
        }
        return min(
            self.members,
            key=lambda e: (
                ver_rank[e.verification],
                scope_rank[e.identity_scope],
                mod_rank[e.modality],
                not e.source_type.is_manufacturer,
            ),
        )

    @property
    def verified_members(self) -> list[Evidence]:
        return [e for e in self.members if e.may_support_accepted_value]


class Conflict(BaseModel):
    """A recorded disagreement between groups, classified by cause.

    Only `FACTUAL` is a genuine source disagreement. Everything above it in
    `ConflictCause` is resolvable deterministically and is retained for the audit
    trail rather than shown as "sources disagree". A model is never permitted to
    resolve a FACTUAL conflict into a committed value.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    cause: ConflictCause
    group_ids: list[str] = Field(min_length=2)
    explanation: str = Field(min_length=1)
    resolution: str | None = None
    resolved_by: ResolvedBy = ResolvedBy.UNRESOLVED

    @model_validator(mode="after")
    def _factual_conflicts_are_not_model_resolved(self) -> Conflict:
        if self.cause is ConflictCause.FACTUAL and self.resolved_by is ResolvedBy.ESCALATED_MODEL:
            raise ValueError(
                "a FACTUAL conflict may not be resolved by a model; it stays conflicted "
                "or goes to a person"
            )
        return self
