# The submission API

A thin, typed HTTP view over the pipeline, for the demo frontend and for judges. It
renders what the trust layers already decided. It does not decide anything itself, and
nothing in it can turn a model proposal into a fact.

## Running it

```
python -m uvicorn skutruth.api.asgi:app --app-dir backend --reload --port 8000
```

Interactive docs at `http://localhost:8000/docs`, and a health check at
`http://localhost:8000/api/health`.

No cloud credentials, no environment variables, and no organizer data pack are needed to
run the default mode.

## Execution modes

| | what it does | external calls |
|---|---|---|
| `DEMO_REPLAY` *(default)* | deterministic stages plus the committed demo record | **none** |
| `LIVE` | live providers under the existing budgets | yes |

Set with `SKUTRUTH_API_MODE`. An unrecognised value is refused at startup rather than
defaulting quietly — a typo in a deployment variable must not produce a replay server
somebody believes is live.

The mode is a **server** setting, never a request parameter. A client that could ask for
LIVE could spend this project's Agent Search and Vertex budget from a browser.

**LIVE never falls back to replay.** A live failure stays a typed failure. Live analysis
of an arbitrary client-supplied row is not exposed at all: the reviewed-domain gate, the
call budget, and the acquisition policy are operator-driven, and `scripts/discover_sources.py
--live` remains the way to run them.

## Why the demo record is committed

The evidence the pipeline produced — the stored Kichler HTML artifact, the Agent Search
and Vertex recordings, the organizer input pack — is gitignored on purpose: it is
third-party material with no established redistribution grant. A clean clone has none of
it, and neither does a deployment built from one.

So `data/demo/cases.json` holds the **derived** result: typed outcomes, values, and short
evidence pointers, regenerated from the real evidence by `scripts/build_demo_cases.py`.
No source document, page HTML, or cassette body is reproduced in it.

This is a real recording of what happened, not live data, and the API says so on every
stage. `tests/test_api.py` re-derives the whole record whenever the evidence is present
and fails if the committed file has drifted.

## Routes

| route | what it answers |
|---|---|
| `GET /api/health` | is the server up, in which mode, does it call anything external |
| `GET /api/demo/products` | the three real cases, with countable metrics |
| `GET /api/demo/products/{mpn}` | one case in full — the whole timeline and evidence |
| `POST /api/analyze` | analyse an organizer-style row |
| `GET /api/schema` | delivery contract shape and the enums the UI renders |

`{mpn}` is a path parameter that accepts slashes, because a real organizer MPN contains
them (`SHOP/4X2/840/V1`) and refusing to route it would hide one of the three cases.

`POST /api/analyze` replays a known demo row in full. Any other row gets the stages that
are computable from committed code and committed data — manufacturer normalisation and
product classification — and honest `NOT_RUN` for everything downstream. Discovery,
acquisition, identity and verification need evidence about *that* product, and the
endpoint will not manufacture it.

## Trust states

Every stage carries three separate things, and the UI should show all three:

* **`status`** — `SUCCESS`, `REVIEW`, `WITHHELD`, `BLOCKED`, `NOT_RUN`. What a reader
  sees at a glance.
* **`reason`** — the internal typed reason, verbatim: `EXACT_PRODUCT_MPN`,
  `SOURCE_PROPERTY_NOT_AUTHORIZED`, `SOURCE_RATE_LIMITED`. Never softened into prose.
* **`evidence`** — where the outcome came from: `DETERMINISTIC`, `STORED_CASSETTE`,
  `STORED_ARTIFACT`, or `RECORDED_OBSERVATION`.

`RECORDED_OBSERVATION` is the honest one. It means a person watched it happen in a live
run and wrote it down — an HTTP 429 cannot be replayed — and the UI should present it
differently from a stage the server just re-derived.

Attributes are split into three lists that never merge: `proposed` (what the model said),
`verified` (what the stored source independently supports), and `withheld` (what survived
binding and still did not become a fact). A verified value is a **manufacturer fact**
under a local demo profile; `unilog_mapping_status` stays `UNAUTHORIZED` because no
official Unilog attribute vocabulary authorises it as delivery content.

## What the API never returns

Absolute paths, credentials, GCP resource ids, cassette internals, raw page HTML, and
Python tracebacks. Evidence excerpts are capped at 200 characters: they are pointers into
a source, not a copy of it. Failures are a single typed shape — `code`, `stage`,
`message`, `retryable`, `details` — and `tests/test_api.py` asserts each of these
absences directly.

CORS is an explicit allow-list (`SKUTRUTH_API_ALLOWED_ORIGINS`, comma-separated), which
defaults to the local frontend dev ports. There is no wildcard default, because a
wildcard is the setting nobody revisits later.
