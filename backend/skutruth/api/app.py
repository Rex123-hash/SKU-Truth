"""The judge-facing HTTP surface.

Five routes, deliberately. Every one of them answers a question somebody watching the
demo actually asks, and none of them exposes a lever that could spend budget, fetch an
arbitrary URL, or bypass the manufacturer review that licenses evidence in the first
place.

The API is a **view** over the pipeline. It computes deterministic stages, reads the
committed demo record, and renders typed states. It does not re-implement a single trust
decision, and it cannot promote anything: nothing here can turn a proposal into a fact.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .analyze import analyze_row
from .cases import DemoCaseLibrary, cached_demo_cases
from .config import API_VERSION, ApiSettings
from .errors import ApiError, ApiErrorCode, ApiException
from .models import (
    AnalyzeRequest,
    DemoIndex,
    ExecutionMode,
    HealthResponse,
    ProductDetail,
    SchemaResponse,
    Stage,
    StageStatus,
)
from .models import EvidenceBasis as _EvidenceBasis

TRUST_NOTE = (
    "AI proposes, SKUTruth verifies, and Unilog's rules decide the delivery format. A "
    "verified value is a manufacturer fact re-derived from a stored source; it is not "
    "authorised Unilog delivery content until an official Unilog attribute vocabulary "
    "says so."
)


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build the app. The mode is fixed here, at startup, and never per request."""
    config = settings or ApiSettings.from_env()
    library: DemoCaseLibrary = cached_demo_cases(config.demo_cases_path)

    app = FastAPI(
        title="SKUTruth demo API",
        version=API_VERSION,
        description=(
            "Evidence-grounded product intelligence for industrial commerce. "
            "Default mode DEMO_REPLAY makes zero external network calls."
        ),
    )
    app.state.settings = config
    app.state.library = library

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )

    @app.exception_handler(ApiException)
    async def _typed_error(_: Request, exc: ApiException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content=exc.error.model_dump(mode="json"))

    @app.exception_handler(RequestValidationError)
    async def _invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic's own error list can echo submitted values back; only the field names
        # and the failure kinds are useful to a client, and only those are returned.
        fields = {
            ".".join(str(part) for part in item.get("loc", ()) if part != "body"): str(
                item.get("type", "invalid")
            )
            for item in exc.errors()
        }
        error = ApiError(
            code=ApiErrorCode.INVALID_REQUEST,
            message="the request body did not satisfy the input contract",
            details=fields,
        )
        return JSONResponse(status_code=422, content=error.model_dump(mode="json"))

    @app.get("/api/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        """Liveness only. Deliberately touches nothing outside this process."""
        return HealthResponse(
            status="ok",
            mode=config.mode,
            version=API_VERSION,
            demo_cases=len(library.cases),
            external_calls=config.mode is ExecutionMode.LIVE,
        )

    @app.get("/api/demo/products", response_model=DemoIndex)
    async def demo_products() -> DemoIndex:
        """The three real cases, with the counts a judge can check against the detail."""
        return library.index(config.mode)

    @app.get("/api/demo/products/{mpn:path}", response_model=ProductDetail)
    async def demo_product(mpn: str) -> ProductDetail:
        """One case in full.

        `:path` on purpose: a real organizer MPN contains slashes (`SHOP/4X2/840/V1`),
        and refusing to route it would hide the exact case the representation-gap demo
        exists to show.
        """
        return library.require(mpn).detail(config.mode)

    @app.post("/api/analyze", response_model=ProductDetail)
    async def analyze(request: AnalyzeRequest) -> ProductDetail:
        """Analyse an organizer-style row.

        A row that matches a demo case replays that case in full. Any other row gets the
        stages that can be computed deterministically, and honest `NOT_RUN` for the rest
        — discovery, acquisition and verification need evidence about *that* product, and
        this endpoint will not manufacture it.
        """
        known = library.get(request.mpn)
        if known is not None:
            return known.detail(config.mode)
        if config.mode is ExecutionMode.LIVE:
            # LIVE deliberately does not run discovery from an arbitrary client row. The
            # reviewed-domain gate, the call budget and the acquisition policy are
            # operator-driven; exposing them to an unauthenticated request would make a
            # public endpoint able to spend them.
            raise ApiException(
                ApiErrorCode.LIVE_MODE_UNAVAILABLE,
                "live analysis of arbitrary rows is operator-driven and not exposed here",
                status_code=501,
                stage=Stage.DISCOVERY,
                details={"run": "scripts/discover_sources.py --live"},
            )
        return analyze_row(request, registry_path=config.registry_path, mode=config.mode)

    @app.get("/api/schema", response_model=SchemaResponse)
    async def schema() -> SchemaResponse:
        """The delivery contract's shape, and the vocabularies the UI renders."""
        metrics = library.metrics
        return SchemaResponse(
            delivery_columns=metrics.get("delivery_columns", 0),
            attribute_triplets=metrics.get("attribute_triplets", 0),
            organizer_rows=metrics.get("organizer_rows", 0),
            organizer_examples_populated=metrics.get("organizer_examples_populated", 0),
            stages=tuple(Stage),
            stage_statuses=tuple(StageStatus),
            evidence_bases=tuple(_EvidenceBasis),
            trust_note=TRUST_NOTE,
        )

    return app


__all__ = ["TRUST_NOTE", "create_app"]
