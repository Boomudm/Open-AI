"use client";

import { api } from "@/lib/api";
import { STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import { useQuery } from "@tanstack/react-query";

export function useFactoriesQuery() {
  return useQuery({
    queryKey: queryKeys.factories(),
    queryFn: () => api.listFactories(),
    staleTime: STALE_STATIC,
  });
}
