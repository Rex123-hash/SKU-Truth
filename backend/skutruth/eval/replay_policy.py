"""Which cassette store an evaluation split is allowed to read.

The replay milestone noted that cassette lookup is single-store, and asked whether
evaluation needs a layered fixtures-then-runtime store. It does not, and building one
would be actively harmful for the locked test.

A `LOCKED_TEST` evaluation must read **curated fixtures only**. If it could fall back
to the runtime directory, a missing fixture would be silently satisfied by whatever
recording happened to be lying around from the last development run — and the locked
numbers would quietly stop describing the locked set. A missing curated cassette has
to fail closed, exactly as a replay miss does.

`DEV` may read the runtime store, because that is where iteration happens.

So the composition needed is one function, not a new class.
"""

from __future__ import annotations

from skutruth.replay import CassetteStore, fixture_store, runtime_store

from .models import Split


def cassette_store_for(split: Split) -> CassetteStore:
    """The only store this split may read.

    `LOCKED_TEST` gets the read-only fixture store, so it can neither fall back to
    runtime recordings nor write new ones. `DEV` gets the runtime store.
    """
    if split is Split.LOCKED_TEST:
        return fixture_store()
    return runtime_store()


def is_locked_evaluation(split: Split) -> bool:
    return split is Split.LOCKED_TEST
