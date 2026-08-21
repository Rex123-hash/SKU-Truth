"""The committed demo case record, and how the API reads it.

## Why a committed file rather than a live re-derivation

The evidence the pipeline produced -- the stored Kichler HTML artifact, the Agent Search
recordings, the Vertex recording -- lives under `data/artifacts/runtime/` and
`data/replay/runtime/`, and both are **gitignored on purpose**: they hold third-party
manufacturer documents and provider material this project has no redistribution grant
for. So does the organizer input pack.

A clean clone therefore has none of it, which means an API that re-derived the demo from
local evidence would work on the machine that recorded it and nowhere else -- including
wherever this gets deployed for judging. This file is the derived, publishable result:
typed outcomes and short evidence pointers, regenerated from the real evidence by
`scripts/build_demo_cases.py`, with no source document redistributed.

`tests/test_api.py` reconciles it against a live re-derivation whenever the evidence *is*
present, so it cannot quietly drift away from what the pipeline actually does.

## Every stage says where it came from

Each timeline entry carries an `EvidenceBasis`. `RECORDED_OBSERVATION` means the operator
watched it in a live run and wrote it down -- an HTTP 429 is not a thing a replay can
reproduce -- and the UI is expected to show that differently from a re-derived stage.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, ConfigDict, ValidationError

from .errors import ApiErrorCode, ApiException
from .models import (
    AiView,
    AttributesView,
    ClassificationView,
    DeliveryView,
    DemoIndex,
    ExecutionMode,
    IdentityView,
    NormalizationView,
    ProductCard,
    ProductDetail,
    ProductSummary,
    SourceView,
    TimelineEntry,
)


class DemoCase(BaseModel):
    """One case, exactly as committed. `mode` is stamped on at request time."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: str
    headline: str
    outcome: str
    product: ProductSummary
    normalization: NormalizationView
    classification: ClassificationView
    source: SourceView
    identity: IdentityView
    ai: AiView
    attributes: AttributesView
    delivery: DeliveryView
    timeline: tuple[TimelineEntry, ...]

    def detail(self, mode: ExecutionMode) -> ProductDetail:
        return ProductDetail(
            case_id=self.case_id,
            mode=mode,
            headline=self.headline,
            product=self.product,
            normalization=self.normalization,
            classification=self.classification,
            source=self.source,
            identity=self.identity,
            ai=self.ai,
            attributes=self.attributes,
            delivery=self.delivery,
            timeline=self.timeline,
        )

    def card(self) -> ProductCard:
        return ProductCard(
            case_id=self.case_id,
            mpn=self.product.mpn,
            manufacturer=self.normalization.manufacturer or self.product.raw_manufacturer,
            headline=self.headline,
            outcome=self.outcome,
            verified_count=len(self.attributes.verified),
            withheld_count=len(self.attributes.withheld),
        )


class DemoCaseFile(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    version: str
    generated_at: str
    note: str
    metrics: dict[str, int]
    cases: tuple[DemoCase, ...]


class DemoCaseLibrary:
    """Read-only access to the committed cases, keyed by case id and by MPN."""

    def __init__(self, file: DemoCaseFile) -> None:
        self._file = file
        self._by_key: dict[str, DemoCase] = {}
        for case in file.cases:
            self._by_key[case.case_id.casefold()] = case
            self._by_key[case.product.mpn.casefold()] = case

    @property
    def metrics(self) -> dict[str, int]:
        return dict(self._file.metrics)

    @property
    def cases(self) -> tuple[DemoCase, ...]:
        return self._file.cases

    def get(self, key: str) -> DemoCase | None:
        return self._by_key.get(key.strip().casefold())

    def require(self, key: str) -> DemoCase:
        case = self.get(key)
        if case is None:
            raise ApiException(
                ApiErrorCode.DEMO_CASE_NOT_FOUND,
                "no demo case exists for that product",
                status_code=404,
                details={"requested": key.strip()[:120]},
            )
        return case

    def index(self, mode: ExecutionMode) -> DemoIndex:
        return DemoIndex(
            mode=mode,
            products=tuple(case.card() for case in self._file.cases),
            metrics=self.metrics,
        )


def load_demo_cases(path: Path) -> DemoCaseLibrary:
    """Load and validate the committed case file.

    A malformed or missing file is a startup-time failure, not a per-request surprise:
    the whole point of the replay mode is that it cannot fail in front of a judge.
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(
            "the demo case file is missing; regenerate it with "
            "scripts/build_demo_cases.py"
        ) from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("the demo case file is not valid JSON") from exc
    try:
        return DemoCaseLibrary(DemoCaseFile.model_validate(payload))
    except ValidationError as exc:
        raise RuntimeError(
            "the demo case file does not satisfy the API contract: "
            + str(exc).replace("\n", " ")[:400]
        ) from exc


@lru_cache(maxsize=4)
def cached_demo_cases(path: Path) -> DemoCaseLibrary:
    """One parse per process. The file is immutable while the server runs."""
    return load_demo_cases(path)


__all__ = [
    "DemoCase",
    "DemoCaseFile",
    "DemoCaseLibrary",
    "cached_demo_cases",
    "load_demo_cases",
]
