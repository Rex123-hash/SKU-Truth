"""Vertex configuration, from the environment.

No model id is baked into business logic. The default below is the model the capability
spike actually verified in this project — recorded as a default, not as a constant to
depend on, since `model` also participates in the replay key.

Credentials are never configuration. Authentication is Application Default Credentials;
nothing here reads, stores, or logs a secret.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ENV_PROJECT = "SKUTRUTH_GCP_PROJECT"
ENV_LOCATION = "SKUTRUTH_VERTEX_LOCATION"
ENV_MODEL = "SKUTRUTH_VERTEX_MODEL"

#: Verified working in the capability spike: structured output over an inline PDF,
#: with usage metadata reported.
DEFAULT_MODEL = "gemini-2.5-flash"
DEFAULT_LOCATION = "us-central1"

#: Recorded on the interaction descriptor because Vertex behaviour is regional; a
#: cassette recorded in one location should not be replayed as though it came from
#: another.
PROVIDER_NAME = "vertex-ai"
ENDPOINT = "generateContent"


@dataclass(frozen=True, slots=True)
class VertexConfig:
    """Where to call and which model to use."""

    project: str
    location: str = DEFAULT_LOCATION
    model: str = DEFAULT_MODEL

    @classmethod
    def from_env(cls) -> VertexConfig:
        """Read configuration, refusing rather than guessing a project."""
        project = os.environ.get(ENV_PROJECT, "").strip()
        if not project:
            raise RuntimeError(
                f"{ENV_PROJECT} is not set. Vertex needs an explicit GCP project; "
                f"inferring one from ambient credentials would make runs depend on "
                f"whichever account happened to be active."
            )
        return cls(
            project=project,
            location=os.environ.get(ENV_LOCATION, "").strip() or DEFAULT_LOCATION,
            model=os.environ.get(ENV_MODEL, "").strip() or DEFAULT_MODEL,
        )


__all__ = [
    "DEFAULT_LOCATION",
    "DEFAULT_MODEL",
    "ENDPOINT",
    "ENV_LOCATION",
    "ENV_MODEL",
    "ENV_PROJECT",
    "PROVIDER_NAME",
    "VertexConfig",
]
