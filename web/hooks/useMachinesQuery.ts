"use client";

import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { api, type MachinesQuery } from "@/lib/api";
import { getMachineMeta, saveMachineMeta } from "@/lib/offline/meta-cache";
import { isBrowserOnline } from "@/lib/offline/network";
import { DEBOUNCE_MS, STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useUiStore } from "@/stores/uiStore";

export function useMachinesQuery(params?: MachinesQuery) {
  return useQuery({
    queryKey: queryKeys.machines(params as Record<string, unknown>),
    queryFn: async () => {
      const factoryId = params?.factory_id;
      try {
        const result = await api.machines(params);
        if (factoryId) void saveMachineMeta(factoryId, result.items);
        return result;
      } catch (e) {
        if (!isBrowserOnline() && factoryId) {
          const cached = await getMachineMeta(factoryId);
          if (cached?.machines.length) {
            return {
              items: cached.machines,
              total: cached.machines.length,
              page: 1,
              page_size: cached.machines.length,
            };
          }
        }
        throw e;
      }
    },
    staleTime: STALE_STATIC,
  });
}

export function useMachinesInfinite(
  search = "",
  options?: { enabled?: boolean; factoryId?: string | null }
) {
  const storeFactoryId = useUiStore((s) => s.selectedFactoryId);
  const factoryId = options?.factoryId ?? storeFactoryId;
  const debouncedSearch = useDebouncedValue(search, DEBOUNCE_MS);
  const enabled = options?.enabled ?? true;

  const query = useInfiniteQuery({
    queryKey: queryKeys.machines({
      infinite: true,
      factory_id: factoryId,
      q: debouncedSearch,
    }),
    enabled: enabled && Boolean(factoryId),
    queryFn: async ({ pageParam = 1 }) => {
      try {
        const result = await api.machines({
          page: pageParam,
          page_size: 50,
          factory_id: factoryId ?? undefined,
          q: debouncedSearch || undefined,
        });
        if (factoryId && pageParam === 1 && !debouncedSearch) {
          void saveMachineMeta(factoryId, result.items);
        }
        return result;
      } catch (e) {
        if (!isBrowserOnline() && factoryId) {
          const cached = await getMachineMeta(factoryId);
          if (cached?.machines.length) {
            const q = debouncedSearch.trim().toLowerCase();
            const filtered = q
              ? cached.machines.filter(
                  (m) =>
                    m.machine_id.toLowerCase().includes(q) ||
                    m.machine_name.toLowerCase().includes(q)
                )
              : cached.machines;
            return {
              items: filtered,
              total: filtered.length,
              page: 1,
              page_size: filtered.length,
            };
          }
        }
        throw e;
      }
    },
    initialPageParam: 1,
    getNextPageParam: (last) => {
      const loaded = last.page * last.page_size;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    staleTime: STALE_STATIC,
  });

  const machines = useMemo(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data]
  );

  const factories = useMemo(() => {
    const ids = new Set(machines.map((m) => m.factory_id));
    return Array.from(ids).sort();
  }, [machines]);

  return {
    ...query,
    machines,
    factories,
    hasMore: query.hasNextPage ?? false,
    loadMore: () => query.fetchNextPage(),
  };
}

export function useFactoriesFromMachines() {
  const { data } = useMachinesQuery({ page_size: 200 });
  return useMemo(() => {
    const ids = new Set((data?.items ?? []).map((m) => m.factory_id));
    return Array.from(ids).sort();
  }, [data]);
}
