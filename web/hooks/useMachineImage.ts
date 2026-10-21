"use client";

import { api } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

export function useMachineImage(
  machineId: string,
  imageUpdatedAt?: string | null
) {
  const [blobUrl, setBlobUrl] = useState<string | null>(null);

  const query = useQuery({
    queryKey: ["machineImage", machineId, imageUpdatedAt ?? ""],
    queryFn: () => api.getMachineImageBlob(machineId),
    enabled: Boolean(machineId),
    staleTime: 5 * 60 * 1000,
    retry: false,
  });

  useEffect(() => {
    if (!query.data) {
      setBlobUrl(null);
      return;
    }
    const url = URL.createObjectURL(query.data);
    setBlobUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [query.data]);

  return {
    imageUrl: blobUrl,
    loading: query.isLoading,
    hasImage: Boolean(query.data),
    error: query.error,
    refetch: query.refetch,
  };
}
