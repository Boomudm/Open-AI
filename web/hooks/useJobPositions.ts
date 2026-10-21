"use client";

import { api, type JobPositionBrief } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { STALE_STATIC } from "@/lib/query-config";
import { useQuery } from "@tanstack/react-query";

export function useJobPositions(enabled = true) {
  return useQuery({
    queryKey: queryKeys.jobPositions(),
    queryFn: () => api.listJobPositions(),
    staleTime: STALE_STATIC,
    enabled,
  });
}

export type { JobPositionBrief };
