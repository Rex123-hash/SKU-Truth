"""Typed failures for the replay layer.

Four things can go wrong, and conflating them would make the layer untrustworthy:

* the infrastructure itself is misused (`ModeNotRequestableError`);
* a cassette we needed is absent (`ReplayMissError`);
* a cassette exists but cannot be trusted (`InvalidCassetteError`);
* the external provider failed, then or now (`RecordedProviderError`).

None of these is ever handled by falling back to a live call. A replay run that
quietly reached the network would invalidate every number measured from it.
"""

from __future__ import annotations


class ReplayError(Exception):
    """Base class for replay-infrastructure failures."""


class ModeNotRequestableError(ReplayError):
    """A run mode was requested that callers are not permitted to ask for.

    `MIXED` is the only such mode. It exists so a run that ended up partly recorded
    and partly live can be described honestly after the fact — never so that one can
    be requested on purpose.
    """

    def __init__(self, mode: str) -> None:
        super().__init__(
            f"run mode {mode!r} cannot be requested; it is a defensive provenance "
            "state, not an operating mode"
        )
        self.mode = mode


class ReplayMissError(ReplayError):
    """No cassette for this request, in REPLAY mode.

    Carries enough context to identify which fixture is missing, and nothing that
    could carry a credential: the key, the provider and model, and where we looked.
    """

    def __init__(
        self,
        key: str,
        *,
        provider: str,
        model: str,
        searched: str,
        prompt_version: str | None = None,
        schema_version: str | None = None,
    ) -> None:
        detail = f"provider={provider} model={model}"
        if prompt_version:
            detail += f" prompt={prompt_version}"
        if schema_version:
            detail += f" schema={schema_version}"
        super().__init__(
            f"no cassette {key} ({detail}) under {searched}. Replay never falls back to a "
            "live call: record this interaction in LIVE mode, or point the runner at the "
            "store that holds it."
        )
        self.key = key
        self.provider = provider
        self.model = model
        self.searched = searched


class InvalidCassetteError(ReplayError):
    """A cassette exists but failed validation.

    Raised for unreadable JSON, an unknown format version, a key that disagrees with
    its filename, or a key that disagrees with the request descriptor stored inside
    it. The last case is how tampering and stale recordings are caught.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(f"cassette at {path} is not usable: {reason}")
        self.path = path
        self.reason = reason


class RecordedProviderError(Exception):
    """Replay of an interaction whose recorded outcome was a provider failure.

    Deliberately not a `ReplayError`: the replay layer worked correctly. What is
    being reproduced is the provider's failure, so callers can exercise their own
    error handling deterministically.
    """

    def __init__(self, key: str, error_type: str, message: str) -> None:
        super().__init__(f"recorded provider failure replayed ({error_type}): {message}")
        self.key = key
        self.error_type = error_type
        self.provider_message = message
