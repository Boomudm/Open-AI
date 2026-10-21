"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, type IngestPreflightResponse } from "@/lib/api";
import { parseApiError } from "@/lib/errors";

export type IngestPreflightParams = {
  file: File;
  factoryId: string;
  machineId?: string;
  documentType?: string;
};

export function useIngestPreflight(debounceMs = 350) {
  const [result, setResult] = useState<IngestPreflightResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const seqRef = useRef(0);

  const reset = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current);
    seqRef.current += 1;
    setResult(null);
    setLoading(false);
    setError(null);
  }, []);

  const run = useCallback(
    (params: IngestPreflightParams) => {
      if (timerRef.current) clearTimeout(timerRef.current);
      const seq = ++seqRef.current;
      setLoading(true);
      setError(null);

      timerRef.current = setTimeout(() => {
        void (async () => {
          try {
            const form = new FormData();
            form.append("file", params.file);
            form.append("factory_id", params.factoryId);
            if (params.documentType) form.append("document_type", params.documentType);
            if (params.machineId) form.append("machine_id", params.machineId);

            const response = await api.ingestPreflight(form);
            if (seq !== seqRef.current) return;
            setResult(response);
            setError(null);
          } catch (err) {
            if (seq !== seqRef.current) return;
            setResult(null);
            setError(parseApiError(err));
          } finally {
            if (seq === seqRef.current) setLoading(false);
          }
        })();
      }, debounceMs);
    },
    [debounceMs]
  );

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  return { result, loading, error, run, reset };
}
