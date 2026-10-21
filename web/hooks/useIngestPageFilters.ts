"use client";

import { parseAsString, useQueryStates } from "nuqs";
import { useCallback } from "react";

export type JobStatusFilter = "" | "queued" | "running" | "completed" | "partial" | "failed";

export function useIngestPageFilters() {
  const [raw, setRaw] = useQueryStates(
    {
      status: parseAsString.withDefault(""),
    },
    { history: "replace", shallow: true }
  );

  const statusFilter = (raw.status ?? "") as JobStatusFilter;

  const setStatusFilter = useCallback(
    (status: JobStatusFilter) => setRaw({ status: status || null }),
    [setRaw]
  );

  return { statusFilter, setStatusFilter };
}
