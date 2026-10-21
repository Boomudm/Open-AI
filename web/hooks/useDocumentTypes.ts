"use client";

import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useQuery } from "@tanstack/react-query";

export function useDocumentTypes() {
  const query = useQuery({
    queryKey: queryKeys.documentTypes(),
    queryFn: () => api.documentTypes(),
    staleTime: 5 * 60 * 1000,
  });

  return {
    documentTypes: query.data ?? [],
    isLoading: query.isLoading,
    error: query.error ? String(query.error) : null,
  };
}
