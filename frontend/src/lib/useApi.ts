"use client";

import { useCallback, useEffect, useState } from "react";

import { SkuTruthApiError } from "./api";

export interface ApiState<T> {
  data: T | null;
  error: SkuTruthApiError | null;
  loading: boolean;
  reload: () => void;
}

/**
 * Runs one API call and exposes its three honest outcomes: loading, a typed error, or
 * data. There is deliberately no fourth branch that substitutes a local fixture when the
 * call fails — a demo that silently invents a backend is the failure mode this entire
 * product exists to argue against.
 */
export function useApi<T>(fetcher: () => Promise<T>): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<SkuTruthApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);

  useEffect(() => {
    let cancelled = false;

    fetcher()
      .then((value) => {
        if (!cancelled) setData(value);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setData(null);
        setError(
          cause instanceof SkuTruthApiError
            ? cause
            : new SkuTruthApiError(
                {
                  code: "UNREACHABLE",
                  stage: null,
                  message: "the SKUTruth demo API could not be reached",
                  retryable: true,
                  details: {},
                },
                0,
              ),
        );
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fetcher, nonce]);

  const reload = useCallback(() => {
    setLoading(true);
    setError(null);
    setNonce((value) => value + 1);
  }, []);

  return { data, error, loading, reload };
}
