"""Deterministic stages for an arbitrary organizer-style row.

These are the stages that need nothing but committed code and committed data: parse the
manufacturer string, resolve it against the human-reviewed catalogue, and classify the
product family from lexical cues. No provider, no network, no model, no stored evidence.

Everything downstream -- discovery, acquisition, identity, model proposals, verification
-- requires evidence about *that specific product*. For a row nobody has run, that
evidence does not exist, and this module reports `NOT_RUN` with a reason rather than
inventing a plausible-looking result. That refusal is the product, not a limitation of
the demo.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from skutruth.discovery.domains import load_registry
from skutruth.unilog import (
    DeterministicNormalizer,
    DeterministicProductClassifier,
    RawProductRow,
    reviewed_manufacturer_catalog,
)

from .models import (
    AiView,
    AnalyzeRequest,
    AttributesView,
    ClassificationView,
    DeliveryView,
    EvidenceBasis,
    ExecutionMode,
    IdentityView,
    NormalizationView,
    ProductDetail,
    ProductSummary,
    SourceView,
    Stage,
    StageStatus,
    TimelineEntry,
)

#: Said once, so every un-evidenced stage gives the same answer for the same reason.
NO_EVIDENCE = "no stored evidence exists for this product in DEMO_REPLAY"

_DECISION_STATUS = {
    "COMMIT": StageStatus.SUCCESS,
    "REVIEW": StageStatus.REVIEW,
    "WITHHOLD": StageStatus.WITHHELD,
}


def _status_for(decision: object) -> StageStatus:
    return _DECISION_STATUS.get(str(getattr(decision, "value", decision)), StageStatus.REVIEW)


def _matched_cues(classification: object) -> tuple[str, ...]:
    """The lexical cues that actually fired, de-duplicated in first-seen order.

    The UI shows these as the reason a family was chosen, so an empty tuple has to stay
    empty rather than being padded with the description.
    """
    seen: list[str] = []
    for item in classification.evidence:
        for cue in item.matched_cues:
            if cue not in seen:
                seen.append(cue)
    return tuple(seen)


def _delivery_classpath(classification: object) -> str | None:
    """The official taxonomy path, only when the delivery proposal actually grants one."""
    values = dict(classification.delivery.delivery_values)
    return values.get("Classpath") or None


def _row_from(request: AnalyzeRequest) -> RawProductRow:
    """Adapt the API request into the organizer row shape the engines already take."""
    return RawProductRow(
        row_number=0,
        raw={
            "Mfg_Part_Num": request.mpn,
            "Part_Desc": request.description,
            "E1_Brand": request.e1_brand,
            "Unilog_Brand": request.unilog_brand,
            "DIB_Brand": request.dib_brand,
            "Part_Manuf": request.manufacturer,
        },
    )


@lru_cache(maxsize=4)
def _normalizer(registry_path: Path) -> DeterministicNormalizer:
    registry = load_registry(registry_path)
    return DeterministicNormalizer(
        manufacturers=reviewed_manufacturer_catalog(
            registry, source=registry_path.name
        )
    )


def analyze_row(
    request: AnalyzeRequest, *, registry_path: Path, mode: ExecutionMode
) -> ProductDetail:
    """Everything that can be established about a row without evidence about it."""
    row = _row_from(request)
    normalization = _normalizer(registry_path).normalize(row)
    classification = DeterministicProductClassifier().classify(row, normalization=normalization)

    manufacturer = normalization.manufacturer
    brand = normalization.brand

    normalization_view = NormalizationView(
        manufacturer=manufacturer.canonical_proposal,
        manufacturer_decision=manufacturer.decision.value,
        manufacturer_reason=manufacturer.reason.value,
        manufacturer_authority=(
            manufacturer.authority.value if manufacturer.authority is not None else None
        ),
        brand=brand.canonical_proposal,
        brand_decision=brand.decision.value,
        brand_reason=brand.reason.value,
    )
    classification_view = ClassificationView(
        family=(
            classification.internal_family.value
            if classification.internal_family is not None
            else None
        ),
        decision=classification.decision.value,
        reason=classification.reason.value if classification.reason is not None else "",
        cues=_matched_cues(classification),
        delivery_classpath=_delivery_classpath(classification),
        delivery_decision=classification.delivery.decision.value,
    )

    unevaluated = (
        Stage.DISCOVERY,
        Stage.ACQUISITION,
        Stage.IDENTITY,
        Stage.AI_PROPOSAL,
        Stage.VERIFICATION,
        Stage.DELIVERY_MAPPING,
    )
    timeline = (
        TimelineEntry(
            stage=Stage.NORMALIZATION,
            status=_status_for(manufacturer.decision),
            reason=manufacturer.reason.value,
            detail=(
                f"manufacturer resolved to {manufacturer.canonical_proposal}"
                if manufacturer.canonical_proposal
                else "no reviewed manufacturer matched this row"
            ),
            evidence=EvidenceBasis.DETERMINISTIC,
        ),
        TimelineEntry(
            stage=Stage.CLASSIFICATION,
            status=_status_for(classification.decision),
            reason=classification.reason.value if classification.reason is not None else "",
            detail=(
                f"internal family {classification.internal_family.value}"
                if classification.internal_family is not None
                else "no family cue was strong enough"
            ),
            evidence=EvidenceBasis.DETERMINISTIC,
        ),
        *(
            TimelineEntry(
                stage=stage,
                status=StageStatus.NOT_RUN,
                reason="EVIDENCE_NOT_AVAILABLE",
                detail=NO_EVIDENCE,
                evidence=EvidenceBasis.DETERMINISTIC,
            )
            for stage in unevaluated
        ),
    )

    return ProductDetail(
        case_id="ad-hoc",
        mode=mode,
        headline="Deterministic stages only. No source has been discovered for this row.",
        product=ProductSummary(
            row_number=None,
            mpn=row.mfg_part_num or request.mpn,
            raw_description=row.part_desc or "",
            raw_manufacturer=row.part_manuf or "",
            raw_brand_signals=row.brand_signals,
        ),
        normalization=normalization_view,
        classification=classification_view,
        source=SourceView(discovery_status=StageStatus.NOT_RUN, blocker_detail=NO_EVIDENCE),
        identity=IdentityView(decision="NOT_RUN", reason="EVIDENCE_NOT_AVAILABLE"),
        ai=AiView(ran=False, not_run_reason=NO_EVIDENCE),
        attributes=AttributesView(),
        delivery=DeliveryView(
            mapping_status="UNAUTHORIZED",
            unauthorized_reason="no verified manufacturer fact exists for this row",
        ),
        timeline=timeline,
    )


__all__ = ["NO_EVIDENCE", "analyze_row"]
