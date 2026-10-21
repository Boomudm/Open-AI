"use client";

import { useFactoryIdParam } from "@/hooks/useFactoryIdParam";
import { api } from "@/lib/api";
import { getDocumentMeta, saveDocumentMeta } from "@/lib/offline/meta-cache";
import { isBrowserOnline } from "@/lib/offline/network";
import { STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import { useQuery } from "@tanstack/react-query";

export function useIndexedDocuments(machineId?: string | null, options?: { enabled?: boolean }) {
  const factoryId = useFactoryIdParam();
  const enabled = options?.enabled ?? true;

  return useQuery({
    queryKey: queryKeys.documents({
      indexed: true,
      factory_id: factoryId,
      machine_id: machineId ?? undefined,
    }),
    enabled: enabled && Boolean(factoryId),
    queryFn: async () => {
      if (!factoryId) return [];
      try {
        const docs = await api.fetchAllDocuments(
          {
            factory_id: factoryId,
            machine_id: machineId || undefined,
          },
          { pageSize: 100, maxItems: 500 }
        );
        void saveDocumentMeta(factoryId, docs);
        return docs;
      } catch (e) {
        if (!isBrowserOnline() && factoryId) {
          const cached = await getDocumentMeta(factoryId);
          if (cached?.documents.length) {
            if (machineId) {
              return cached.documents.filter((d) => d.machine_id === machineId);
            }
            return cached.documents;
          }
        }
        throw e;
      }
    },
    staleTime: STALE_STATIC,
  });
}
