"use client";

import { useFactoryIdParam } from "@/hooks/useFactoryIdParam";
import { api } from "@/lib/api";
import { getDocumentMeta, saveDocumentMeta } from "@/lib/offline/meta-cache";
import { isBrowserOnline } from "@/lib/offline/network";
import { STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo } from "react";

const LIBRARY_PAGE_SIZE = 50;

/** Factory-scoped document list for the learning hub (paginated, all machines). */
export function useDocumentsLibrary(options?: { enabled?: boolean }) {
  const factoryId = useFactoryIdParam();
  const enabled = options?.enabled ?? true;

  const query = useInfiniteQuery({
    queryKey: queryKeys.documents({
      library: true,
      factory_id: factoryId,
    }),
    enabled: enabled && Boolean(factoryId),
    initialPageParam: 1,
    queryFn: async ({ pageParam }) => {
      if (!factoryId) {
        return { items: [], total: 0, page: 1, page_size: LIBRARY_PAGE_SIZE };
      }
      try {
        const res = await api.listDocuments({
          factory_id: factoryId,
          page: pageParam,
          page_size: LIBRARY_PAGE_SIZE,
        });
        if (pageParam === 1) {
          void saveDocumentMeta(factoryId, res.items);
        }
        return res;
      } catch (e) {
        if (!isBrowserOnline()) {
          const cached = await getDocumentMeta(factoryId);
          if (cached?.documents.length) {
            return {
              items: cached.documents,
              total: cached.documents.length,
              page: 1,
              page_size: cached.documents.length,
            };
          }
        }
        throw e;
      }
    },
    getNextPageParam: (last) => {
      const loaded = last.page * last.page_size;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    staleTime: STALE_STATIC,
  });

  const documents = useMemo(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data]
  );
  const total = query.data?.pages[0]?.total ?? documents.length;

  return {
    data: documents,
    total,
    isLoading: query.isLoading,
    isFetching: query.isFetching,
    isError: query.isError,
    error: query.error,
    refetch: query.refetch,
    hasMore: query.hasNextPage ?? false,
    loadMore: () => void query.fetchNextPage(),
    isFetchingMore: query.isFetchingNextPage,
  };
}
