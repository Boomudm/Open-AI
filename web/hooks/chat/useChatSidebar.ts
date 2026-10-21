"use client";

import { useCallback, useState } from "react";
import {
  useChatSessionsInfinite,
  useCreateChatSession,
  useDeleteChatSession,
  useUpdateChatSession,
} from "@/hooks/useChatSessions";
import { useChatUrlState } from "@/hooks/useChatUrlState";
import { findReusableEmptySession, isEmptyDefaultSession } from "@/lib/chat";
import { useChatStore } from "@/stores/chatStore";
import { useUiStore } from "@/stores/uiStore";

export function useChatSidebar(opts?: { enabled?: boolean }) {
  const enabled = opts?.enabled ?? true;
  const { sessionId, setSessionId } = useChatUrlState();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const resetForSession = useChatStore((s) => s.resetForSession);
  const setError = useChatStore((s) => s.setError);

  const {
    sessions,
    isLoading: sessionsLoading,
    isError: sessionsError,
    refetch: refetchSessions,
    hasMore: sessionsHasMore,
    loadMore: loadMoreSessions,
    isFetchingNextPage: sessionsFetchingMore,
  } = useChatSessionsInfinite(sessionId, {
    enabled: enabled && Boolean(selectedFactoryId),
    factoryId: selectedFactoryId,
  });

  const createSession = useCreateChatSession(selectedFactoryId);
  const updateSession = useUpdateChatSession();
  const deleteSession = useDeleteChatSession();

  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [pendingDeleteSessionId, setPendingDeleteSessionId] = useState<string | null>(null);

  const handleSelectSession = useCallback(
    (id: string) => {
      resetForSession();
      setSessionId(id);
      setError("");
    },
    [resetForSession, setSessionId, setError]
  );

  const handleNewChat = useCallback(async () => {
    if (createSession.isPending) return;
    setError("");
    const current = sessions.find((s) => s.session_id === sessionId);
    if (current && isEmptyDefaultSession(current)) {
      handleSelectSession(current.session_id);
      return;
    }
    const reusable = findReusableEmptySession(sessions, sessionId);
    if (reusable) {
      handleSelectSession(reusable.session_id);
      return;
    }
    try {
      const s = await createSession.mutateAsync(null);
      handleSelectSession(s.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "สร้างเซสชันแชทไม่สำเร็จ");
    }
  }, [createSession, sessionId, sessions, handleSelectSession, setError]);

  const handleDeleteSession = useCallback((id: string) => {
    setPendingDeleteSessionId(id);
  }, []);

  const confirmDeleteSession = useCallback(async () => {
    const id = pendingDeleteSessionId;
    if (!id) return;
    setError("");
    setDeletingSessionId(id);
    try {
      await deleteSession.mutateAsync(id);
      if (sessionId === id) {
        const remaining = sessions.filter((s) => s.session_id !== id);
        const reusable = findReusableEmptySession(remaining);
        if (reusable) {
          handleSelectSession(reusable.session_id);
        } else if (remaining.length > 0) {
          handleSelectSession(remaining[0].session_id);
        } else {
          const s = await createSession.mutateAsync(null);
          handleSelectSession(s.session_id);
        }
      }
      setPendingDeleteSessionId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "ลบการสนทนาไม่สำเร็จ");
    } finally {
      setDeletingSessionId(null);
    }
  }, [
    pendingDeleteSessionId,
    deleteSession,
    sessionId,
    sessions,
    handleSelectSession,
    createSession,
    setError,
  ]);

  const handlePinSession = useCallback(
    async (id: string, pinned: boolean) => {
      try {
        await updateSession.mutateAsync({ sessionId: id, patch: { pinned } });
      } catch (e) {
        setError(e instanceof Error ? e.message : "ไม่สามารถปักหมุดได้");
      }
    },
    [updateSession, setError]
  );

  const handleRenameSession = useCallback(
    async (id: string, title: string) => {
      const trimmed = title.trim();
      if (!trimmed) return;
      try {
        await updateSession.mutateAsync({ sessionId: id, patch: { title: trimmed } });
      } catch (e) {
        setError(e instanceof Error ? e.message : "ไม่สามารถเปลี่ยนชื่อได้");
      }
    },
    [updateSession, setError]
  );

  return {
    sessionId,
    sessions,
    sessionsLoading,
    sessionsError,
    refetchSessions,
    sessionsHasMore,
    loadMoreSessions,
    sessionsFetchingMore,
    creatingSession: createSession.isPending,
    deletingSessionId,
    pendingDeleteSessionId,
    setPendingDeleteSessionId,
    confirmDeleteSession,
    handleNewChat,
    handleSelectSession,
    handleDeleteSession,
    handlePinSession,
    handleRenameSession,
  };
}
