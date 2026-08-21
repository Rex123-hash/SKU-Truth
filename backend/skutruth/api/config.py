"""Server configuration. Secrets stay server-side and never appear in a response.

The mode is read once, at startup, from `SKUTRUTH_API_MODE`. It is not a request
parameter: a client that could ask for LIVE could spend the project's Agent Search and
Vertex budget from a browser, and a judge watching a demo would have no way to tell which
mode produced what they are looking at.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .models import ExecutionMode

ENV_MODE = "SKUTRUTH_API_MODE"
ENV_ORIGINS = "SKUTRUTH_API_ALLOWED_ORIGINS"

#: Local frontend dev servers. Production origins are supplied explicitly; there is no
#: wildcard default, because a wildcard is the one setting nobody revisits later.
DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:3000",
    "http://localhost:5173",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
)

#: Bumped when a change here could alter what a client sees.
API_VERSION = "skutruth-api@v1"

_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True, slots=True)
class ApiSettings:
    """Everything the app needs, resolved once."""

    mode: ExecutionMode = ExecutionMode.DEMO_REPLAY
    allowed_origins: tuple[str, ...] = DEFAULT_ALLOWED_ORIGINS
    root: Path = _ROOT

    @property
    def demo_cases_path(self) -> Path:
        return self.root / "data" / "demo" / "cases.json"

    @property
    def registry_path(self) -> Path:
        return self.root / "data" / "discovery" / "manufacturer_domains.demo.toml"

    @classmethod
    def from_env(cls) -> ApiSettings:
        """Refuse an unrecognised mode rather than defaulting quietly.

        A typo in a deployment variable must not silently produce a replay server that
        someone believes is live, or the reverse.
        """
        raw = os.environ.get(ENV_MODE, "").strip().upper()
        if raw and raw not in tuple(ExecutionMode):
            raise ValueError(
                f"{ENV_MODE} must be one of {', '.join(ExecutionMode)}; got {raw!r}"
            )
        origins = tuple(
            item.strip()
            for item in os.environ.get(ENV_ORIGINS, "").split(",")
            if item.strip()
        )
        return cls(
            mode=ExecutionMode(raw) if raw else ExecutionMode.DEMO_REPLAY,
            allowed_origins=origins or DEFAULT_ALLOWED_ORIGINS,
        )


__all__ = [
    "API_VERSION",
    "DEFAULT_ALLOWED_ORIGINS",
    "ENV_MODE",
    "ENV_ORIGINS",
    "ApiSettings",
]
