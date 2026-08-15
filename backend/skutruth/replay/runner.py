"""The wrapper every external and model call goes through.

    LIVE    caller executes -> interaction captured -> versioned cassette stored
    REPLAY  cassette loaded -> returned            -> no external call, ever

The provider is injected as a callable, so this layer knows nothing about Vertex,
Gemini, HTTP, or anything else. A later integration supplies the closure and gets
recording, replay, redaction, timing, and usage capture without changing anything
here.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from skutruth.contracts import RunMode, RunProvenance

from .errors import ModeNotRequestableError, RecordedProviderError, ReplayMissError
from .models import (
    CASSETTE_VERSION,
    Cassette,
    InteractionRequest,
    RecordedError,
    Usage,
)
from .redaction import redact, redact_text
from .store import CassetteStore


@dataclass(frozen=True, slots=True)
class LiveResponse:
    """What a live callable may return when it has usage or metadata to report.

    Returning a bare JSON value is also fine, and is what most test callables do;
    it is treated as a response with no usage.
    """

    response: Any
    usage: Usage | None = None
    metadata: dict | None = None
    status_code: int | None = None


@dataclass(frozen=True)
class InteractionResult:
    """The outcome of one interaction, with everything provenance needs."""

    mode: RunMode
    replayed: bool
    cassette: Cassette

    @property
    def key(self) -> str:
        return self.cassette.key

    @property
    def response(self) -> Any:
        return self.cassette.response

    @property
    def provider(self) -> str:
        return self.cassette.provider

    @property
    def model(self) -> str:
        return self.cassette.model

    @property
    def captured_at(self) -> datetime:
        return self.cassette.captured_at

    @property
    def latency_seconds(self) -> float:
        return self.cassette.latency_seconds

    @property
    def usage(self) -> Usage | None:
        return self.cassette.usage

    def to_run_provenance(
        self, *, provider_surface: str | None = None, sdk_version: str | None = None
    ) -> RunProvenance:
        """Adapt to the frozen contract type the rest of the system already uses.

        A replayed result carries the *original* capture time, not now — that is what
        lets the UI say how old the recording is instead of implying freshness.
        """
        return RunProvenance(
            mode=self.mode,
            captured_at=self.cassette.captured_at if self.mode is not RunMode.LIVE else None,
            cassette_id=self.cassette.key,
            extraction_model=self.cassette.model,
            provider_surface=provider_surface,
            sdk_version=sdk_version,
        )


# -- frozen-contract probes ---------------------------------------------------
#
# The rules for which modes may be requested and which are safe to serve publicly
# already live on RunProvenance. Rather than restate them — and risk the two drifting
# apart — these helpers construct a throwaway provenance and ask it.


def _probe(mode: RunMode) -> RunProvenance:
    captured = datetime.now(UTC) if mode is not RunMode.LIVE else None
    return RunProvenance(mode=mode, captured_at=captured)


def is_mode_requestable(mode: RunMode) -> bool:
    return _probe(mode).is_requestable


def is_public_demo_safe(mode: RunMode) -> bool:
    """Whether a public, ungated route may serve a run in this mode.

    The single check a future public API route needs: `REPLAY` only.
    """
    return _probe(mode).is_public_demo_safe


def require_requestable(mode: RunMode) -> None:
    if not is_mode_requestable(mode):
        raise ModeNotRequestableError(mode.value)


def require_public_demo_safe(mode: RunMode) -> None:
    if not is_public_demo_safe(mode):
        raise ModeNotRequestableError(mode.value)


# -- the runner ---------------------------------------------------------------


def run_interaction(
    *,
    mode: RunMode,
    request: InteractionRequest,
    store: CassetteStore,
    live_callable: Callable[[], Any] | None = None,
    notes: str | None = None,
) -> InteractionResult:
    """Execute or replay one external interaction.

    In `REPLAY` the `live_callable` is never touched — not on a miss, not on a
    malformed cassette, not on a recorded failure. A replay run that reached the
    network would invalidate every measurement taken from it, so the only outcomes
    are a cassette or an exception.
    """
    require_requestable(mode)
    if mode is RunMode.REPLAY:
        return _replay(request=request, store=store)
    return _record(request=request, store=store, live_callable=live_callable, notes=notes)


def _replay(*, request: InteractionRequest, store: CassetteStore) -> InteractionResult:
    cassette = store.load_for(request)  # raises ReplayMissError / InvalidCassetteError
    if cassette.is_error:
        assert cassette.error is not None
        raise RecordedProviderError(
            cassette.key, cassette.error.error_type, cassette.error.message
        )
    return InteractionResult(mode=RunMode.REPLAY, replayed=True, cassette=cassette)


def _record(
    *,
    request: InteractionRequest,
    store: CassetteStore,
    live_callable: Callable[[], Any] | None,
    notes: str | None,
) -> InteractionResult:
    if live_callable is None:
        # A programmer error, before any provider was involved. Nothing to record.
        raise ValueError("LIVE mode requires a live_callable")

    key = request.cassette_key()
    safe_request = request.redacted()
    captured_at = datetime.now(UTC)
    started = time.perf_counter()

    try:
        outcome = live_callable()
    except Exception as exc:
        # Everything raised by the injected callable is treated as a provider
        # failure: it is the only thing that ran. The failure is recorded so it can
        # be replayed deterministically, and then re-raised unchanged — recording is
        # observation, and must not swallow what the caller needs to handle.
        elapsed = time.perf_counter() - started
        failure = Cassette(
            cassette_version=CASSETTE_VERSION,
            key=key,
            request=safe_request,
            provider=request.provider,
            model=request.model,
            outcome="error",
            error=RecordedError(
                error_type=type(exc).__name__,
                message=redact_text(str(exc)),
            ),
            captured_at=captured_at,
            latency_seconds=max(elapsed, 0.0),
            notes=notes,
        )
        store.save(failure)
        raise

    elapsed = time.perf_counter() - started
    if isinstance(outcome, LiveResponse):
        response, usage, metadata = outcome.response, outcome.usage, outcome.metadata or {}
    else:
        response, usage, metadata = outcome, None, {}

    cassette = Cassette(
        cassette_version=CASSETTE_VERSION,
        key=key,
        request=safe_request,
        provider=request.provider,
        model=request.model,
        outcome="success",
        response=redact(response),
        captured_at=captured_at,
        latency_seconds=max(elapsed, 0.0),
        usage=usage,
        response_metadata=redact(metadata),
        notes=notes,
    )
    store.save(cassette)
    return InteractionResult(mode=RunMode.LIVE, replayed=False, cassette=cassette)


__all__ = [
    "InteractionResult",
    "LiveResponse",
    "ReplayMissError",
    "is_mode_requestable",
    "is_public_demo_safe",
    "require_public_demo_safe",
    "require_requestable",
    "run_interaction",
]
