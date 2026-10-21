"use client";

import { mintStreamTicket } from "@/lib/api/streams";
import { useEffect, useState } from "react";

export type IngestProgressEvent = {
  job_id: string;
  percent: number;
  rows_ok: number;
  rows_total: number;
  stage: string;
  status?: string;
};

/** Subscribe to ingest job SSE when job is active (replaces 3s polling for one job). */
export function useIngestJobStream(jobId: string | null, enabled: boolean) {
  const [progress, setProgress] = useState<IngestProgressEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled || !jobId) {
      setProgress(null);
      setError(null);
      setConnected(false);
      return;
    }

    let es: EventSource | null = null;
    let cancelled = false;

    mintStreamTicket("ingest_job", jobId).then((ticket) => {
      if (cancelled) return;
      const base = `/api/v1/ingest/jobs/${jobId}/stream`;
      const url = ticket ? `${base}?ticket=${encodeURIComponent(ticket)}` : base;
      es = new EventSource(url);
      es.onopen = () => {
        setConnected(true);
        setError(null);
      };
      es.onmessage = (ev) => {
        try {
          setProgress(JSON.parse(ev.data) as IngestProgressEvent);
        } catch {
          /* ignore keepalive */
        }
      };
      es.onerror = () => {
        setError("stream disconnected");
        setConnected(false);
        es?.close();
      };
    });

    return () => {
      cancelled = true;
      setConnected(false);
      es?.close();
    };
  }, [jobId, enabled]);

  return { progress, error, connected };
}
