"""Deterministic redaction, applied before anything is persisted or keyed.

Two properties matter. Redaction runs on the way *in*, so a secret never reaches a
cassette file even transiently; and it runs before key derivation, so a rotated
credential does not invalidate every recording.

## On matching

The obvious implementation — redact any key containing "token" — is wrong here, and
in a way that would quietly corrupt our data. Provider responses report usage as
`promptTokenCount`, `input_tokens`, `totalTokenCount`; a substring rule would redact
all of them and we would lose the token counts the whole cost model depends on.

So matching is deliberately in two parts:

* **exact match** on a normalised key name, which covers the bare `token`, `secret`,
  `password`, `cookie` and friends; and
* **substring match** only on markers that are unambiguous in isolation —
  `apikey`, `accesstoken`, `clientsecret` and similar — which catches real-world
  names like `openai_api_key` without touching `prompt_token_count`.

Normalisation folds case and drops `-`, `_` and spaces, so `X-API-Key`, `x_api_key`
and `apiKey` all resolve to `apikey`.

Erring toward leaking is not an option; erring toward over-redaction loses evidence
fidelity. The split above is the narrowest rule that avoids both.
"""

from __future__ import annotations

import re
from typing import Any

#: Bumped when the rules below change, and recorded on every cassette so an old
#: recording can be identified as having been redacted under older rules.
REDACTION_VERSION = "redaction@v1"

PLACEHOLDER = "[REDACTED]"

#: Redacted when the normalised key matches exactly.
SENSITIVE_KEYS: frozenset[str] = frozenset(
    {
        "authorization",
        "proxyauthorization",
        "apikey",
        "xapikey",
        "xgoogapikey",
        "accesstoken",
        "refreshtoken",
        "idtoken",
        "bearertoken",
        "token",
        "secret",
        "clientsecret",
        "password",
        "passwd",
        "cookie",
        "setcookie",
        "sessionid",
        "privatekey",
        "credentials",
        "signature",
    }
)

#: Redacted when the normalised key *contains* one of these. Each is unambiguous on
#: its own; bare "token" is deliberately absent (see the module docstring).
SENSITIVE_MARKERS: tuple[str, ...] = (
    "apikey",
    "accesstoken",
    "refreshtoken",
    "bearertoken",
    "clientsecret",
    "privatekey",
    "authorization",
    "password",
    "passphrase",
    "setcookie",
)

_NORMALISE = re.compile(r"[-_\s.]+")

#: Query parameters scrubbed from URLs and from free text such as error messages.
_QUERY_PARAM = re.compile(
    r"(?i)\b(api[-_]?key|access[-_]?token|refresh[-_]?token|id[-_]?token|auth|"
    r"authorization|token|key|password|secret|signature)=([^&\s\"']+)"
)


def normalise_key(key: str) -> str:
    return _NORMALISE.sub("", key).casefold()


def is_sensitive_key(key: str) -> bool:
    """Whether a mapping key names something that must never be persisted."""
    normalised = normalise_key(key)
    if normalised in SENSITIVE_KEYS:
        return True
    return any(marker in normalised for marker in SENSITIVE_MARKERS)


def redact_text(text: str) -> str:
    """Scrub credential-bearing query parameters out of a URL or free text.

    Used on URLs and on provider error messages, which routinely echo the request
    URL back verbatim.
    """
    return _QUERY_PARAM.sub(lambda m: f"{m.group(1)}={PLACEHOLDER}", text)


def redact(value: Any) -> Any:
    """Return a redacted deep copy. The input is never mutated.

    Recurses through dicts and lists. A sensitive key has its entire value replaced,
    however deeply nested that value is, so a credential cannot survive by hiding
    inside an object. String values are additionally passed through `redact_text` to
    catch credentials embedded in URLs.
    """
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if isinstance(key, str) and is_sensitive_key(key):
                out[key] = PLACEHOLDER
            else:
                out[key] = redact(item)
        return out
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value
