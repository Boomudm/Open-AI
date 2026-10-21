"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useChatAsk } from "@/hooks/chat/useChatAsk";
import { useChatSessionSync } from "@/hooks/chat/useChatSessionSync";
import { useChatUrlState } from "@/hooks/useChatUrlState";
import { useChatSettings } from "@/hooks/useChatSettings";
import { useEnsureFactorySelected } from "@/hooks/useEnsureFactorySelected";
import { useIndexedDocuments } from "@/hooks/useIndexedDocuments";
import { api } from "@/lib/api";
import { getUsername } from "@/lib/auth";
import { findReusableEmptySession } from "@/lib/chat";
import { parseApiError } from "@/lib/errors";
import { useUiStore } from "@/stores/uiStore";
import {
  findLastAssistantId,
  getActiveSources,
  useChatStore,
} from "@/stores/chatStore";

export function useChatPageController() {
  useEnsureFactorySelected();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const activeSessionRef = useRef<string | undefined>(undefined);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const {
    sessionId,
    machineId,
    draftPrompt,
    sidebarView,
    deepLinkDocId,
    setSessionId,
    setMachineId,
    setSidebarView,
    clearDraftPrompt,
    clearDeepLinkDoc,
  } = useChatUrlState();

  // SSE can emit `connected` before an effect has run after session creation.
  // Keep this ref current during render so the first progress event is not lost.
  activeSessionRef.current = sessionId;

  const composerReady = useChatStore((s) => s.composerReady);
  const setComposerReady = useChatStore((s) => s.setComposerReady);
  const messages = useChatStore((s) => s.messages);
  const input = useChatStore((s) => s.input);
  const sending = useChatStore((s) => s.sending);
  const regeneratingId = useChatStore((s) => s.regeneratingId);
  const verifyingId = useChatStore((s) => s.verifyingId);
  const error = useChatStore((s) => s.error);
  const selectedMsgId = useChatStore((s) => s.selectedMsgId);
  const sourcesOpen = useChatStore((s) => s.sourcesOpen);
  const setError = useChatStore((s) => s.setError);
  const setInput = useChatStore((s) => s.setInput);
  const closeSources = useChatStore((s) => s.closeSources);
  const markVerified = useChatStore((s) => s.markVerified);
  const setVerifyingId = useChatStore((s) => s.setVerifyingId);

  const { settings: chatSettings } = useChatSettings();
  const draftPromptAppliedRef = useRef<string | null>(null);

  const [username, setUsername] = useState("Operator");
  const [deletingSessionId, setDeletingSessionId] = useState<string | null>(null);
  const [pendingDeleteSessionId, setPendingDeleteSessionId] = useState<string | null>(null);
  const [rcaOpen, setRcaOpen] = useState(false);

  const sessionSync = useChatSessionSync({
    sessionId,
    factoryId: selectedFactoryId,
    setSessionId,
    composerReady,
    setComposerReady,
    activeSessionRef,
  });

  const { askQuestion, abortAsk, retryLastAsk } = useChatAsk({
    sessionId,
    machineId: machineId || null,
    factoryId: selectedFactoryId,
    chatSettings,
    activeSessionRef,
  });

  const { data: indexedDocuments = [], isLoading: indexedLoading } = useIndexedDocuments(
    machineId || null,
    { enabled: Boolean(machineId) }
  );

  useEffect(() => {
    setUsername(getUsername() || "Operator");
    setComposerReady(true);
  }, [setComposerReady]);

  useEffect(() => {
    if (!draftPrompt || draftPromptAppliedRef.current === draftPrompt) return;
    draftPromptAppliedRef.current = draftPrompt;
    setInput(draftPrompt);
    clearDraftPrompt();
    window.setTimeout(() => inputRef.current?.focus(), 0);
  }, [draftPrompt, clearDraftPrompt, setInput]);

  useEffect(() => {
    return () => abortAsk();
  }, [abortAsk]);

  const lastAssistantId = useMemo(() => findLastAssistantId(messages), [messages]);
  const activeSourceId = selectedMsgId ?? lastAssistantId;
  const activeSources = useMemo(
    () => getActiveSources(messages, selectedMsgId, lastAssistantId),
    [messages, selectedMsgId, lastAssistantId]
  );

  const sessionBlocked =
    !sessionId ||
    (Boolean(sessionId) && sessionSync.messagesLoading) ||
    (sessionSync.createSession.isPending && composerReady);

  const send = useCallback(
    async (attachments?: File[]) => {
      if (sessionBlocked || sending || regeneratingId) return;
      setComposerReady(true);
      const files = attachments ?? [];
      if (!input.trim() && files.length === 0) return;
      const question = input.trim();
      setInput("");
      await askQuestion(question, { files });
    },
    [
      input,
      askQuestion,
      regeneratingId,
      sending,
      sessionBlocked,
      setComposerReady,
      setInput,
    ]
  );

  const handleRegenerate = useCallback(
    async (assistantMessageId: string) => {
      const idx = messages.findIndex((m) => m.id === assistantMessageId);
      if (idx <= 0) return;
      let userIdx = idx - 1;
      while (userIdx >= 0 && messages[userIdx].role !== "user") {
        userIdx -= 1;
      }
      if (userIdx < 0) return;
      await askQuestion(messages[userIdx].content, {
        replaceAssistantId: assistantMessageId,
        appendUserMessage: false,
      });
    },
    [messages, askQuestion]
  );

  const handleVerifyMessage = useCallback(
    async (assistantMessageId: string) => {
      if (!selectedFactoryId) {
        setError("เลือกโรงงานก่อนยืนยันคำตอบ");
        return;
      }
      setVerifyingId(assistantMessageId);
      try {
        await api.verifyChatMessage(assistantMessageId, selectedFactoryId);
        markVerified(assistantMessageId);
      } catch (e) {
        setError(parseApiError(e));
      } finally {
        setVerifyingId(null);
      }
    },
    [selectedFactoryId, setError, setVerifyingId, markVerified]
  );

  const handleRetryError = useCallback(() => {
    retryLastAsk();
    if (!sessionSync.messagesError) return;
    if (sessionId) void sessionSync.refetchMessages();
    setError("");
  }, [retryLastAsk, sessionSync, sessionId, setError]);

  const handleDeleteSession = useCallback((id: string) => {
    setPendingDeleteSessionId(id);
  }, []);

  const confirmDeleteSession = useCallback(async () => {
    const id = pendingDeleteSessionId;
    if (!id) return;
    setError("");
    setDeletingSessionId(id);
    try {
      await sessionSync.deleteSession.mutateAsync(id);
      if (sessionId === id) {
        const remaining = sessionSync.sessions.filter((s) => s.session_id !== id);
        const reusable = findReusableEmptySession(remaining);
        if (reusable) {
          sessionSync.switchToSession(reusable.session_id);
        } else if (remaining.length > 0) {
          sessionSync.switchToSession(remaining[0].session_id);
        } else {
          const s = await sessionSync.createSession.mutateAsync(null);
          sessionSync.switchToSession(s.session_id);
        }
      }
      setPendingDeleteSessionId(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete conversation");
    } finally {
      setDeletingSessionId(null);
    }
  }, [pendingDeleteSessionId, sessionSync, sessionId, setError]);

  const handlePinSession = useCallback(
    async (id: string, pinned: boolean) => {
      try {
        await sessionSync.updateSession.mutateAsync({ sessionId: id, patch: { pinned } });
      } catch (e) {
        setError(e instanceof Error ? e.message : "ไม่สามารถปักหมุดได้");
      }
    },
    [sessionSync.updateSession, setError]
  );

  const handleRenameSession = useCallback(
    async (id: string, title: string) => {
      const trimmed = title.trim();
      if (!trimmed) return;
      try {
        await sessionSync.updateSession.mutateAsync({ sessionId: id, patch: { title: trimmed } });
      } catch (e) {
        setError(e instanceof Error ? e.message : "ไม่สามารถเปลี่ยนชื่อได้");
      }
    },
    [sessionSync.updateSession, setError]
  );

  const sendSuggestion = useCallback(
    async (question: string) => {
      const trimmed = question.trim();
      if (!trimmed || sessionBlocked || sending || regeneratingId) return;
      setComposerReady(true);
      setInput("");
      await askQuestion(trimmed);
    },
    [
      askQuestion,
      regeneratingId,
      sending,
      sessionBlocked,
      setComposerReady,
      setInput,
    ]
  );

  const messagesLoadFailed =
    sessionSync.messagesError && !sessionSync.messagesLoading && Boolean(sessionId);

  return {
    username,
    sessionId,
    machineId,
    sidebarView,
    deepLinkDocId,
    setMachineId,
    setSidebarView,
    clearDeepLinkDoc,
    inputRef,
    selectedFactoryId,
    indexedDocuments,
    indexedLoading,
    rcaOpen,
    setRcaOpen,
    deletingSessionId,
    pendingDeleteSessionId,
    setPendingDeleteSessionId,
    confirmDeleteSession,
    handleDeleteSession,
    handlePinSession,
    handleRenameSession,
    sessionSync,
    messages,
    input,
    sending,
    regeneratingId,
    verifyingId,
    error: error || (messagesLoadFailed ? "โหลดประวัติแชทไม่สำเร็จ" : ""),
    activeSourceId,
    activeSources,
    sourcesOpen,
    closeSources,
    send,
    sendSuggestion,
    handleRegenerate,
    handleVerifyMessage,
    handleRetryError,
    sessionBlocked,
    composerReady,
    chatSettings,
    abortAsk,
  };
}
