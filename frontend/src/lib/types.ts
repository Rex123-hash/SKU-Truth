/**
 * The frontend mirror of `backend/skutruth/api/models.py`.
 *
 * These types are deliberately as strict as the server's: a proposal, a verified fact
 * and a withheld proposal are three different shapes, so a component cannot render one
 * as another by accident. That separation is the product, not a style preference.
 */

export type ExecutionMode = "DEMO_REPLAY" | "LIVE";

export type Stage =
  | "NORMALIZATION"
  | "CLASSIFICATION"
  | "DISCOVERY"
  | "ACQUISITION"
  | "IDENTITY"
  | "AI_PROPOSAL"
  | "VERIFICATION"
  | "DELIVERY_MAPPING";

export type StageStatus = "SUCCESS" | "REVIEW" | "WITHHELD" | "BLOCKED" | "NOT_RUN";

export type EvidenceBasis =
  | "DETERMINISTIC"
  | "STORED_CASSETTE"
  | "STORED_ARTIFACT"
  | "RECORDED_OBSERVATION";

export interface TimelineEntry {
  stage: Stage;
  status: StageStatus;
  reason: string;
  detail: string;
  evidence: EvidenceBasis;
}

export interface ProductSummary {
  row_number: number | null;
  mpn: string;
  raw_description: string;
  raw_manufacturer: string;
  raw_brand_signals: string[];
}

export interface NormalizationView {
  manufacturer: string | null;
  manufacturer_decision: string;
  manufacturer_reason: string;
  manufacturer_authority: string | null;
  brand: string | null;
  brand_decision: string;
  brand_reason: string;
}

export interface ClassificationView {
  family: string | null;
  decision: string;
  reason: string;
  cues: string[];
  delivery_classpath: string | null;
  delivery_decision: string | null;
}

export interface SourceView {
  discovery_status: StageStatus;
  results_returned: number;
  exact_candidates: number;
  authority: string | null;
  relevance: string | null;
  source_kind: string | null;
  discovery_url: string | null;
  final_url: string | null;
  artifact_kind: string | null;
  artifact_sha256: string | null;
  blocker: string | null;
  blocker_detail: string;
}

export interface IdentityView {
  decision: string;
  identity_scope: string | null;
  covers_mpn: string | null;
  reason: string;
}

export interface AiView {
  ran: boolean;
  model: string | null;
  profile_id: string | null;
  proposal_count: number;
  source_bound_count: number;
  rejected_count: number;
  replayed: boolean;
  not_run_reason: string;
}

export interface EvidenceLocatorView {
  kind: string;
  jsonld_block_index: number | null;
  json_pointer: string | null;
  element_index: number | null;
  start_offset: number | null;
  end_offset: number | null;
  excerpt: string;
}

/** A model proposal bound to a locator. Not a fact. */
export interface ProposedAttribute {
  source_key: string;
  label: string;
  proposed_value: string;
  proposed_uom: string;
  value_kind: string | null;
  locator: EvidenceLocatorView | null;
}

/** A manufacturer fact, mechanically re-derived from the stored source. */
export interface VerifiedAttribute {
  source_key: string;
  label: string;
  value: string;
  uom: string | null;
  source_label: string;
  source_value: string;
  source_uom: string;
  locator: EvidenceLocatorView;
  status: string;
  reason: string;
  authority: string;
  decision: string;
  unilog_mapping_status: string;
  delivery_eligible: boolean;
}

/** A proposal that survived binding and still did not become a fact. */
export interface WithheldAttribute {
  source_key: string;
  label: string;
  proposed_value: string;
  proposed_uom: string;
  source_label: string;
  source_value: string;
  locator: EvidenceLocatorView | null;
  status: string;
  reason: string;
  detail: string;
}

export interface AttributesView {
  proposed: ProposedAttribute[];
  verified: VerifiedAttribute[];
  withheld: WithheldAttribute[];
}

export interface DeliveryView {
  mapped_count: number;
  mapping_status: string;
  unauthorized_reason: string;
}

export interface ProductDetail {
  case_id: string;
  mode: ExecutionMode;
  headline: string;
  product: ProductSummary;
  normalization: NormalizationView;
  classification: ClassificationView;
  source: SourceView;
  identity: IdentityView;
  ai: AiView;
  attributes: AttributesView;
  delivery: DeliveryView;
  timeline: TimelineEntry[];
}

export interface ProductCard {
  case_id: string;
  mpn: string;
  manufacturer: string;
  headline: string;
  outcome: string;
  verified_count: number;
  withheld_count: number;
}

export interface DemoIndex {
  mode: ExecutionMode;
  products: ProductCard[];
  metrics: Record<string, number>;
}

export interface HealthResponse {
  status: string;
  mode: ExecutionMode;
  version: string;
  demo_cases: number;
  external_calls: boolean;
}

export interface SchemaResponse {
  delivery_columns: number;
  attribute_triplets: number;
  organizer_rows: number;
  organizer_examples_populated: number;
  stages: string[];
  stage_statuses: string[];
  evidence_bases: string[];
  trust_note: string;
}

export interface AnalyzeRequest {
  mpn: string;
  description?: string;
  manufacturer?: string;
  e1_brand?: string;
  unilog_brand?: string;
  dib_brand?: string;
}

export type ApiErrorCode =
  | "DEMO_CASE_NOT_FOUND"
  | "INVALID_REQUEST"
  | "REPLAY_NOT_AVAILABLE"
  | "SOURCE_RATE_LIMITED"
  | "NO_EXACT_SOURCE"
  | "SOURCE_ACQUISITION_FAILED"
  | "IDENTITY_WITHHELD"
  | "LIVE_MODE_UNAVAILABLE"
  | "LIVE_PROVIDER_FAILED"
  /** Not from the server: the browser could not reach it at all. */
  | "UNREACHABLE";

export interface ApiErrorBody {
  code: ApiErrorCode;
  stage: Stage | null;
  message: string;
  retryable: boolean;
  details: Record<string, string>;
}
