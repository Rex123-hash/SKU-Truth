/**
 * Typed server vocabularies rendered as English.
 *
 * The server's own code -- `EXACT_PRODUCT_MPN`, `SOURCE_PROPERTY_NOT_AUTHORIZED` -- is
 * always shown beside the sentence, never replaced by it. A judge should be able to read
 * the plain meaning and still see the exact term the pipeline actually emitted.
 */

import type { EvidenceBasis, Stage, StageStatus } from "./types";

export const STAGE_LABEL: Record<Stage, string> = {
  NORMALIZATION: "Normalize",
  CLASSIFICATION: "Classify",
  DISCOVERY: "Discover",
  ACQUISITION: "Acquire",
  IDENTITY: "Identify",
  AI_PROPOSAL: "AI propose",
  VERIFICATION: "Verify",
  DELIVERY_MAPPING: "Deliver",
};

export const STAGE_BLURB: Record<Stage, string> = {
  NORMALIZATION: "Resolve the manufacturer string to a reviewed identity.",
  CLASSIFICATION: "Decide the product family from lexical cues.",
  DISCOVERY: "Find an official manufacturer page for this exact reference.",
  ACQUISITION: "Fetch and hash the document under a safe policy.",
  IDENTITY: "Prove the document covers this exact SKU.",
  AI_PROPOSAL: "The model proposes attributes and binds each to a location.",
  VERIFICATION: "Re-derive each proposal from the stored source, mechanically.",
  DELIVERY_MAPPING: "Decide what is authorised for the delivery format.",
};

export const STATUS_LABEL: Record<StageStatus, string> = {
  SUCCESS: "Passed",
  REVIEW: "Needs review",
  WITHHELD: "Withheld",
  BLOCKED: "Blocked",
  NOT_RUN: "Not run",
};

/**
 * Where a reported outcome came from. `RECORDED_OBSERVATION` is the one that has to read
 * differently from the rest: an HTTP 429 is not something a replay can reproduce, so the
 * UI must not let it look like a stage the server just re-derived.
 */
export const EVIDENCE_LABEL: Record<EvidenceBasis, string> = {
  DETERMINISTIC: "Deterministic computation",
  STORED_CASSETTE: "Replayed recording",
  STORED_ARTIFACT: "Stored artifact",
  RECORDED_OBSERVATION: "Recorded observation",
};

export const EVIDENCE_TOOLTIP: Record<EvidenceBasis, string> = {
  DETERMINISTIC: "Recomputed now from committed code and committed data.",
  STORED_CASSETTE: "Re-derived now from a recorded provider interaction.",
  STORED_ARTIFACT: "Re-derived now from a stored, hashed manufacturer document.",
  RECORDED_OBSERVATION:
    "Observed during a live run and written down by the operator. This one is not replayable, so the server did not re-derive it.",
};

/** Reason codes the demo actually emits, in the words a person can act on. */
export const REASON_SENTENCE: Record<string, string> = {
  EXACT_CANONICAL: "The supplied name matched a reviewed manufacturer exactly.",
  EXACT_ALIAS: "The supplied name matched a reviewed alias of this manufacturer.",
  PLACEHOLDER: "The column held a placeholder, not a brand.",
  SINGLE_BRAND_SOURCE: "Only one column asserted this brand, so it goes to review.",
  STRONG_LEXICAL_CUE: "The description carried a decisive cue for this family.",
  EXACT: "The locator names this exact reference.",
  ABSENT: "No returned locator named this exact reference.",
  ARTIFACT_STORED: "The document was fetched, hashed and stored.",
  EXACT_PRODUCT_MPN: "The stored document proves it covers this exact SKU.",
  SOURCE_BOUND: "Every proposal was bound to a location in the stored document.",
  FACT_VERIFIED: "The source states this value under a reviewed property name.",
  SOURCE_RATE_LIMITED: "The manufacturer site answered the fetch with HTTP 429.",
  NO_EXACT_SOURCE: "No locator established the exact reference, so nothing was fetched.",
  NO_ARTIFACT: "There is no stored document, so this stage had no input.",
  NO_VERIFIED_FACT: "Nothing was verified, so nothing could be mapped.",
  UNAUTHORIZED: "No official delivery vocabulary authorises these values.",
  SOURCE_PROPERTY_NOT_AUTHORIZED:
    "The value exists, but the source property does not prove which attribute it belongs to.",
  EXPECTED_LABEL_MISSING:
    "The fragment does not begin with a reviewed label, so it names no attribute.",
};

export const reasonSentence = (reason: string): string | null =>
  REASON_SENTENCE[reason] ?? null;

/** Evidence locator kinds, spelled for a reader rather than for the parser. */
export const LOCATOR_KIND_LABEL: Record<string, string> = {
  HTML_JSONLD: "Structured data (JSON-LD)",
  HTML_TEXT: "Page text",
  PDF_TEXT: "PDF text",
};

export const OUTCOME_LABEL: Record<string, string> = {
  VERIFIED_MANUFACTURER_FACTS: "Complete",
  BLOCKED_AT_ACQUISITION: "Rate limited",
  NO_EXACT_REFERENCE: "Representation gap",
};

/**
 * The one sentence that stops a judge reading "replay" as "fake". Replay is recorded
 * real evidence, played back so the demo is deterministic -- not invented data.
 */
export const REPLAY_EXPLANATION =
  "Replay mode uses previously captured real manufacturer evidence and verified pipeline outcomes, so the demo stays deterministic even when external websites or AI providers are unavailable. Nothing here is mock data.";
