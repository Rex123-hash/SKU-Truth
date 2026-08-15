# Curated replay fixtures

Human-reviewed recordings that are intended for commit. Everything a LIVE run
produces lands in `data/replay/runtime/` (gitignored) instead.

Promotion is deliberate: a person reads the cassette, confirms it carries no
credential and no third-party content we lack the right to redistribute, and copies
it here. That review is the only thing between this repository and an accidentally
published secret or licensed datasheet.

The fixture store is opened read-only in code, so a live run cannot write here.
