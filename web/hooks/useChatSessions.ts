"use client";

import { api } from "@/lib/api";
import type { ChatSessionRow } from "@/lib/chat";
import { STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import {
  useInfiniteQuery,
  useMutation,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { useMemo, useEffect, useRef } from "react";
import type { Paginated } from "@/lib/api";

type SessionPage = Paginated<{
  session_id: string;
  title: string | null;
  pinned: boolean;
  message_count: number;
  created_at: string;
  updated_at: string;
  context?: Record<string, unknown> | null;
  factory_id?: string | null;
}>;

function patchSessionPages(
  old: InfiniteData<SessionPage> | undefined,
  sessionId: string,
  patch: Partial<ChatSessionRow>
): InfiniteData<SessionPage> | undefined {
  if (!old?.pages.length) return old;
  return {
    ...old,
    pages: old.pages.map((page) => ({
      ...page,
      items: page.items.map((s) =>
        s.session_id === sessionId ? { ...s, ...patch } : s
      ),
    })),
  };
}

export function useChatSessionsInfinite(
  activeSessionId?: string | null,
  opts?: { enabled?: boolean; factoryId?: string | null }
) {
  const activeRef = useRef(activeSessionId);
  activeRef.current = activeSessionId;
  const factoryId = opts?.factoryId ?? null;
  const sessionQueryKey = queryKeys.chatSessions({
    infinite: true,
    factory_id: factoryId ?? null,
  });

  const query = useInfiniteQuery({
    queryKey: sessionQueryKey,
    queryFn: ({ pageParam = 1 }) =>
      api.listSessions({
        page: pageParam,
        page_size: 50,
        for_sidebar: true,
        include_session_id: activeRef.current || undefined,
        factory_id: factoryId,
      }),
    initialPageParam: 1,
    enabled: opts?.enabled ?? true,
    getNextPageParam: (last) => {
      const loaded = last.page * last.page_size;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    staleTime: STALE_STATIC,
  });

  useEffect(() => {
    if (activeSessionId) {
      void query.refetch();
    }
  }, [activeSessionId, query.refetch]);

  const sessions: ChatSessionRow[] = useMemo(
    () => query.data?.pages.flatMap((p) => p.items) ?? [],
    [query.data]
  );

  return {
    ...query,
    sessions,
    hasMore: query.hasNextPage ?? false,
    loadMore: () => query.fetchNextPage(),
  };
}

export function useCreateChatSession(factoryId?: string | null) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (title?: string | null) => api.createSession(title, factoryId ?? null),
    onSuccess: (data) => {
      const now = new Date().toISOString();
      const factoryId =
        typeof data.context?.factory_id === "string"
          ? data.context.factory_id
          : null;
      const sessionQueryKey = queryKeys.chatSessions({
        infinite: true,
        factory_id: factoryId,
      });
      qc.setQueryData<InfiniteData<SessionPage>>(
        sessionQueryKey,
        (old) => {
          if (!old?.pages.length) return old;
          const row = {
            session_id: data.session_id,
            title: data.title ?? null,
            pinned: data.pinned ?? false,
            message_count: 0,
            created_at: now,
            updated_at: now,
            context: data.context ?? null,
            factory_id: factoryId,
          };
          if (old.pages.some((p) => p.items.some((s) => s.session_id === data.session_id))) {
            return old;
          }
          return {
            ...old,
            pages: old.pages.map((page, index) =>
              index === 0
                ? {
                    ...page,
                    items: [row, ...page.items],
                    total: page.total + 1,
                  }
                : page
            ),
          };
        }
      );
      qc.invalidateQueries({ queryKey: queryKeys.chatSessions() });
    },
  });
}

export function useUpdateChatSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      sessionId,
      patch,
    }: {
      sessionId: string;
      patch: { title?: string | null; pinned?: boolean };
    }) => api.updateSession(sessionId, patch),
    onMutate: async ({ sessionId, patch }) => {
      await qc.cancelQueries({ queryKey: queryKeys.chatSessions() });
      const previous = qc.getQueryData<InfiniteData<SessionPage>>(
        queryKeys.chatSessions({ infinite: true })
      );
      if (previous) {
        qc.setQueryData<InfiniteData<SessionPage>>(
          queryKeys.chatSessions({ infinite: true }),
          patchSessionPages(previous, sessionId, patch)
        );
      }
      return { previous };
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(queryKeys.chatSessions({ infinite: true }), ctx.previous);
      }
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: queryKeys.chatSessions() });
    },
  });
}

export function useDeleteChatSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: string) => api.deleteSession(sessionId),
    onMutate: async (sessionId) => {
      await qc.cancelQueries({ queryKey: queryKeys.chatSessions() });
      const previous = qc.getQueryData<InfiniteData<SessionPage>>(
        queryKeys.chatSessions({ infinite: true })
      );
      if (previous) {
        qc.setQueryData<InfiniteData<SessionPage>>(
          queryKeys.chatSessions({ infinite: true }),
          {
            ...previous,
            pages: previous.pages.map((page) => ({
              ...page,
              items: page.items.filter((s) => s.session_id !== sessionId),
              total: Math.max(0, page.total - 1),
            })),
          }
        );
      }
      return { previous };
    },
    onError: (_err, _id, ctx) => {
      if (ctx?.previous) {
        qc.setQueryData(queryKeys.chatSessions({ infinite: true }), ctx.previous);
      }
    },
    onSuccess: (_data, sessionId) => {
      qc.invalidateQueries({ queryKey: queryKeys.chatSessions() });
      qc.removeQueries({ queryKey: ["chatMessages"] });
    },
  });
}
