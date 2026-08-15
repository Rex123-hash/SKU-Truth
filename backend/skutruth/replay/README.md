# Record / replay

Every external and model interaction goes through `run_interaction`. Nothing in the
pipeline calls a provider directly.

```
LIVE     caller executes -> interaction captured -> versioned cassette stored
REPLAY   cassette loaded -> returned             -> no external call, ever
```

## Why this exists

Three reasons, in order of importance.

**Measurements have to be reproducible.** Evaluation numbers computed against a live
provider are not reproducible by anyone, including us a week later. Numbers computed
from committed cassettes can be re-derived by a reviewer with no API key.

**The demo must not be able to fail.** A judge-facing run that depends on a third-party
fetch succeeding is a run that can break at the worst moment, for reasons entirely
outside our control.

**Development should be cheap.** Iterating on parsing and adjudication should not cost
money or rate limit, and should not require the network at all.

Replay is recorded real interactions, not synthetic data, and the UI says so — see
`RunProvenance.banner()`, which states the capture date.

## LIVE and REPLAY

**LIVE** validates the mode is requestable, derives the cassette key *before* calling,
invokes the injected callable exactly once, measures latency, redacts, writes the
cassette atomically, and returns a structured result.

**REPLAY** derives the same key, loads the cassette, validates it, and returns it. The
`live_callable` is never invoked — not on a miss, not on a malformed cassette, not on
a recorded failure.

**MIXED** is not requestable. It exists only so a run that ended up partly recorded and
partly live can be described honestly afterwards. `run_interaction` refuses it.

Mode semantics are not restated here. `is_mode_requestable` and `is_public_demo_safe`
probe the frozen `RunProvenance` contract, so there is one source of truth and the two
cannot drift apart.

## Why replay never falls back to live

A fallback would mean a run labelled REPLAY had silently reached the network, so any
metric taken from it would be unreproducible and quietly wrong — and nobody would know,
because a fallback looks like success. Given that, a missing cassette must be an
error. `ReplayMissError` names the key, provider, model, and the directory searched, so
the fix is obvious: record the interaction, or point the runner at the store holding it.

## What the cassette key covers

The key answers one question: *would replaying this cassette reproduce the same logical
call?*

**In the key:** key version, provider, model, endpoint, normalized payload, prompt
version, schema version, stage version, enabled tools, tool configuration, and the hash
of every artifact the call reads.

**Not in the key:** timestamps, run and trace ids, latency, retry counts, and
credentials. A timestamp in the key would give every interaction a fresh key and make
replay useless; a credential would break every cassette on rotation.

Tools and artifact hashes are sorted, so listing the same two tools in a different order
yields the same key. Payload key ordering is handled by canonical JSON — sorted keys,
no incidental whitespace, SHA-256 over UTF-8. `repr()` is never used: it is not stable
across versions and varies with insertion order.

`KEY_VERSION` participates in the digest, so bumping it separates old keys from new
ones instead of silently reusing stale recordings under changed semantics.

## Where cassettes live

| Directory | Purpose | Committed? |
|---|---|---|
| `data/replay/runtime/` | Everything LIVE records | No — gitignored |
| `data/replay/fixtures/` | Human-reviewed recordings | Yes, deliberately |

Promotion is a manual copy after a person has looked at the file. The fixture store is
opened **read-only**, so a live run cannot write into it by accident. That review step
is the only thing between us and committing a credential or someone else's licensed
datasheet.

Writes are atomic: a temporary file in the destination directory, flushed and fsynced,
then `os.replace`. An interrupted process leaves a stray temporary file, never a
truncated cassette that would load and validate as though it were whole.

## Redaction guarantees

Redaction runs before persistence *and* before key derivation, so a secret never
reaches a file even transiently, and rotating a credential does not invalidate
cassettes.

It recurses through nested dicts and lists, matches keys case-insensitively after
folding `-`, `_`, and spaces, and replaces the whole value of a sensitive key however
deeply nested. Strings are additionally scrubbed for credential-bearing query
parameters, which also covers provider error messages that echo the request URL.

Matching is in two parts on purpose. Exact matches cover bare `token`, `secret`,
`password`, `cookie` and friends. Substring matching is limited to markers that are
unambiguous alone — `apikey`, `accesstoken`, `clientsecret` — because a naive
"contains token" rule would redact `promptTokenCount` and `input_tokens` and destroy
the usage data the cost model depends on.

## Usage and cost

`Usage` is provider-neutral and entirely optional. Nothing is derived: if a provider
reports input and output tokens but no total, the total stays `None`, because summing
them assumes the provider counts nothing else. Cost is recorded only when the provider
reports it. No pricing table lives here, and a cassette never claims more than the
provider actually returned.

## Failures

A provider failure during LIVE is recorded as an error cassette **and re-raised
unchanged** — recording is observation, and must not swallow what the caller needs to
handle. Replaying that cassette raises `RecordedProviderError`, reproducing the failure
structurally rather than reaching for the network.

Everything raised by the injected callable is treated as a provider failure, since it
is the only thing that ran. Errors in our own code before invocation — a missing
callable, an unusable request — are programmer errors and are not recorded.

| Exception | Meaning |
|---|---|
| `ModeNotRequestableError` | `MIXED` was requested |
| `ReplayMissError` | No cassette for this key |
| `InvalidCassetteError` | Cassette present but untrustworthy |
| `RecordedProviderError` | Replaying a recorded provider failure |

## Cassette validation

A cassette is never `json.load`ed and trusted. Loading checks the format version, that
the key is a well-formed digest, that the key matches the filename, that required
fields and a timezone-aware `captured_at` are present, and — the important one — that
**the stored key is derivable from the stored request descriptor**. A hand-edited or
stale cassette fails that check. There is no fallback to live.

## Using it from a future provider integration

```python
request = InteractionRequest(
    provider="vertex-ai",
    model="gemini-3.1-flash-lite",
    endpoint="generateContent",
    payload=normalized_body,
    prompt_version="extract@v3",
    schema_version=schema.schema_version,
    tools=("google_search",),
    artifact_hashes=(document_sha256,),
)

result = run_interaction(
    mode=mode,
    request=request,
    store=runtime_store(),
    live_callable=lambda: call_the_provider(...),
)
parsed = parse(result.response)
```

The cassette stores the provider's **raw** response, not a parsed result, so parser and
schema changes can be tested against an unchanged recording. Binary bodies are not
supported today; they would be base64-encoded behind a narrow wrapper, and there is no
reason to build that machinery before something needs it.
