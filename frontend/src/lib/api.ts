/**
 * The only place in the frontend that talks to the network.
 *
 * Two rules hold everywhere below. A failed call raises a typed `SkuTruthApiError` and
 * never returns a plausible-looking object: if the API is down the UI says so and offers
 * a retry, because a demo that quietly substitutes local fixtures for a dead backend is
 * exactly the dishonesty this product exists to refuse. And the base URL is the only
 * host the client will contact -- no component composes a URL of its own.
 */

import type {
  AnalyzeRequest,
  ApiErrorBody,
  ApiErrorCode,
  DemoIndex,
  HealthResponse,
  ProductDetail,
  SchemaResponse,
  Stage,
} from "./types";

export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_SKUTRUTH_API_BASE_URL ?? "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export class SkuTruthApiError extends Error {
  readonly code: ApiErrorCode;
  readonly stage: Stage | null;
  readonly retryable: boolean;
  readonly details: Record<string, string>;
  readonly status: number;

  constructor(body: ApiErrorBody, status: number) {
    super(body.message);
    this.name = "SkuTruthApiError";
    this.code = body.code;
    this.stage = body.stage;
    this.retryable = body.retryable;
    this.details = body.details;
    this.status = status;
  }
}

const UNREACHABLE: ApiErrorBody = {
  code: "UNREACHABLE",
  stage: null,
  message: "the SKUTruth demo API could not be reached",
  retryable: true,
  details: {},
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
  } catch {
    // A network-level failure carries no server error body to forward, so it becomes the
    // one client-side code in the union rather than being disguised as a server answer.
    throw new SkuTruthApiError(UNREACHABLE, 0);
  }

  if (!response.ok) {
    let body: ApiErrorBody = { ...UNREACHABLE, message: `request failed (${response.status})` };
    try {
      const parsed = (await response.json()) as Partial<ApiErrorBody>;
      if (parsed && typeof parsed.code === "string") body = parsed as ApiErrorBody;
    } catch {
      /* A non-JSON error body stays the generic shape above. */
    }
    throw new SkuTruthApiError(body, response.status);
  }

  return (await response.json()) as T;
}

export const getHealth = () => request<HealthResponse>("/api/health");

export const getDemoProducts = () => request<DemoIndex>("/api/demo/products");

/**
 * `key` is a case id (`kichler-45297bk`) or an MPN. The server routes the detail path
 * with `:path`, so an MPN carrying slashes -- `SHOP/4X2/840/V1` -- resolves correctly,
 * but the frontend addresses cases by id and never puts a raw MPN in its own URLs.
 */
export const getDemoProduct = (key: string) =>
  request<ProductDetail>(`/api/demo/products/${encodeURI(key)}`);

export const getSchema = () => request<SchemaResponse>("/api/schema");

export const analyzeRow = (row: AnalyzeRequest) =>
  request<ProductDetail>("/api/analyze", { method: "POST", body: JSON.stringify(row) });
