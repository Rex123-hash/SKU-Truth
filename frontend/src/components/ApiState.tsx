"use client";

import { PlugZap, RefreshCw } from "lucide-react";

import type { SkuTruthApiError } from "@/lib/api";
import { API_BASE_URL } from "@/lib/api";
import { Button } from "./primitives";

/**
 * What the page shows when the API cannot answer. It says so plainly and offers a retry.
 * It never renders placeholder values that could be mistaken for a result.
 */
export function ApiUnavailable({
  error,
  onRetry,
  compact = false,
}: {
  error: SkuTruthApiError;
  onRetry: () => void;
  compact?: boolean;
}) {
  const unreachable = error.code === "UNREACHABLE";

  return (
    <div
      role="alert"
      className={
        "card-surface flex flex-col items-start gap-4 border-amber-soft bg-amber-wash " +
        (compact ? "p-5" : "p-7")
      }
    >
      <span className="inline-flex items-center gap-2 text-[13px] font-semibold uppercase tracking-[0.1em] text-[#8a6410]">
        <PlugZap className="h-4 w-4" aria-hidden="true" />
        Demo API unavailable
      </span>

      <div>
        <p className="text-[15px] leading-relaxed text-ink">
          {unreachable
            ? "The frontend could not reach the SKUTruth demo API, so there is nothing verified to show. No values are being substituted."
            : error.message}
        </p>
        {unreachable ? (
          <p className="mt-2 font-mono text-[12.5px] text-muted">{API_BASE_URL}</p>
        ) : (
          <p className="mt-2 font-mono text-[12.5px] text-muted">
            {error.code}
            {error.stage ? " · " + error.stage : ""}
          </p>
        )}
      </div>

      <Button variant="secondary" onClick={onRetry}>
        <RefreshCw className="h-4 w-4" aria-hidden="true" />
        Retry
      </Button>
    </div>
  );
}

/** A calm placeholder block while a request is in flight. */
export function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={"animate-pulse rounded-[10px] bg-line-soft/70 " + className}
    />
  );
}

export function SkeletonCard({ lines = 3 }: { lines?: number }) {
  return (
    <div className="card-surface p-5">
      <Skeleton className="h-5 w-24" />
      <Skeleton className="mt-4 h-8 w-40" />
      <div className="mt-5 space-y-2.5">
        {Array.from({ length: lines }).map((_, index) => (
          <Skeleton key={index} className="h-3.5 w-full" />
        ))}
      </div>
    </div>
  );
}
