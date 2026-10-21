import { useCallback, useEffect, useRef } from "react";
import {
  useChatSessionsInfinite,
  useCreateChatSession,
  useDeleteChatSession,
  useUpdateChatSession,
} from "@/hooks/useChatSessions";
import { api } from "@/lib/api";
import {
  findReusableEmptySession,
  isEmptyDefaultSession,
  mapApiMessages,
} from "@/lib/chat";
import { parseApiError } from "@/lib/errors";
import { STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import { useChatStore } from "@/stores/chatStore";
import { useQuery } from "@tanstack/react-query";

type UseChatSessionSyncParams = {
  sessionId: string | undefined;
  factoryId: string | null;
  setSessionId: (id: string) => void;
  composerReady: boolean;
  setComposerReady: (ready: boolean) => void;
  activeSessionRef: React.MutableRefObject<string | undefined>;
};

export function useChatSessionSync({
  sessionId,
  factoryId,
  setSessionId,
  composerReady,
  setComposerReady,
  activeSessionRef,
}: UseChatSessionSyncParams) {
  const {
    sessions,
    isLoading: sessionsLoading,
    isError: sessionsError,
    refetch: refetchSessions,
    hasMore: sessionsHasMore,
    loadMore: loadMoreSessions,
    isFetchingNextPage: sessionsFetchingMore,
  } = useChatSessionsInfinite(sessionId, {
    enabled: Boolean(factoryId),
    factoryId,
  });

  const createSession = useCreateChatSession(factoryId);
  const updateSession = useUpdateChatSession();
  const deleteSession = useDeleteChatSession();

  const sessionInitRef = useRef(false);
  const creatingInitRef = useRef(false);
  const loadedSessionRef = useRef<string | null>(null);
  const pendingSessionRef = useRef<string | null>(null);

  const setMessages = useChatStore((s) => s.setMessages);
  const resetForSession = useChatStore((s) => s.resetForSession);
  const setError = useChatStore((s) => s.setError);

  useEffect(() => {
    sessionInitRef.current = false;
    creatingInitRef.current = false;
    loadedSessionRef.current = null;
    pendingSessionRef.current = null;
    resetForSession();
  }, [factoryId, resetForSession]);

  const {
    data: apiMessages,
    isLoading: messagesLoading,
    isError: messagesError,
    refetch: refetchMessages,
  } = useQuery({
    queryKey: queryKeys.chatMessages(`${factoryId ?? "none"}:${sessionId ?? ""}`),
    queryFn: () => api.listMessages(sessionId!, factoryId),
    enabled: Boolean(sessionId && factoryId),
    staleTime: STALE_STATIC,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!sessionId || messagesLoading) return;
    if (loadedSessionRef.current === sessionId) return;
    if (!apiMessages) return;
    loadedSessionRef.current = sessionId;
    setMessages(mapApiMessages(apiMessages));
  }, [sessionId, apiMessages, messagesLoading, setMessages]);

  useEffect(() => {
    if (!factoryId || !sessionId || messagesLoading || !messagesError) return;
    if (sessionsLoading) return;
    loadedSessionRef.current = null;
    if (sessions.length > 0) {
      setSessionId(sessions[0].session_id);
      return;
    }
    setSessionId("");
  }, [
    factoryId,
    sessionId,
    messagesLoading,
    messagesError,
    sessionsLoading,
    sessions,
    setSessionId,
  ]);

  useEffect(() => {
    if (!factoryId || sessionsLoading || sessionInitRef.current || !composerReady) return;
    if (sessionId && sessions.some((s) => s.session_id === sessionId)) {
      sessionInitRef.current = true;
      return;
    }
    // sessionId is either unset or left over from a previously selected
    // factory (a chat session is permanently bound to the factory it was
    // first used with, so it won't appear in this factory's session list)
    // — fall through to pick or create a session that actually belongs to
    // `factoryId` instead of letting a stale session reach the ask request.
    if (sessions.length > 0) {
      const reusable = findReusableEmptySession(sessions);
      if (reusable) {
        setSessionId(reusable.session_id);
        sessionInitRef.current = true;
        return;
      }
    }
    if (createSession.isPending || creatingInitRef.current) return;
    creatingInitRef.current = true;
    createSession.mutate(null, {
      onSuccess: (s) => {
        pendingSessionRef.current = s.session_id;
        setSessionId(s.session_id);
        sessionInitRef.current = true;
      },
      onError: (err) => {
        setError(err instanceof Error ? err.message : "สร้างเซสชันแชทไม่สำเร็จ");
      },
      onSettled: () => {
        creatingInitRef.current = false;
      },
    });
  }, [factoryId, sessionsLoading, sessionId, sessions, setSessionId, createSession, composerReady]);

  const switchToSession = useCallback(
    (id: string, clearMessages = true) => {
      pendingSessionRef.current = id;
      loadedSessionRef.current = null;
      activeSessionRef.current = id;
      setSessionId(id);
      if (clearMessages) {
        resetForSession();
      } else {
        useChatStore.getState().setSelectedMsgId(null);
        useChatStore.getState().setSourcesOpen(false);
      }
    },
    [activeSessionRef, setSessionId, resetForSession]
  );

  const handleNewChat = useCallback(async () => {
    if (createSession.isPending) return;
    setError("");
    const current = sessions.find((s) => s.session_id === sessionId);
    if (current && isEmptyDefaultSession(current)) {
      switchToSession(current.session_id);
      return;
    }
    const reusable = findReusableEmptySession(sessions, sessionId);
    if (reusable) {
      switchToSession(reusable.session_id);
      return;
    }
    try {
      const s = await createSession.mutateAsync(null);
      switchToSession(s.session_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create session");
    }
  }, [createSession, sessionId, sessions, switchToSession, setError]);

  const handleSelectSession = useCallback(
    (id: string) => {
      setComposerReady(true);
      loadedSessionRef.current = null;
      activeSessionRef.current = id;
      resetForSession();
      setSessionId(id);
      setError("");
    },
    [activeSessionRef, setSessionId, setComposerReady, setError, resetForSession]
  );

  return {
    sessions,
    sessionsLoading,
    sessionsError,
    refetchSessions,
    sessionsHasMore,
    loadMoreSessions,
    sessionsFetchingMore,
    createSession,
    updateSession,
    deleteSession,
    messagesLoading,
    messagesError,
    refetchMessages,
    switchToSession,
    handleNewChat,
    handleSelectSession,
    pendingSessionRef,
  };
}
