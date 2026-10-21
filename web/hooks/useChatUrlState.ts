"use client";

import { parseAsString, useQueryStates } from "nuqs";
import { useCallback, useEffect, useMemo, useRef } from "react";
import { useUiStore } from "@/stores/uiStore";

const LAST_SESSION_KEY = "spark_chat_last_session";

export function useChatUrlState() {
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const setSelectedMachineId = useUiStore((s) => s.setSelectedMachineId);
  const [raw, setRaw] = useQueryStates(
    {
      session: parseAsString.withDefault(""),
      machine: parseAsString.withDefault(""),
      machineId: parseAsString.withDefault(""),
      prompt: parseAsString.withDefault(""),
      view: parseAsString.withDefault(""),
      doc: parseAsString.withDefault(""),
    },
    { history: "replace", shallow: true }
  );

  const machineInitRef = useRef(false);
  const restoredSessionKeyRef = useRef<string | null>(null);
  const factoryTransitionRef = useRef(false);

  const rawSession = raw.session ?? "";
  const lastSessionKey = useMemo(
    () => `${LAST_SESSION_KEY}:${selectedFactoryId ?? "none"}`,
    [selectedFactoryId]
  );

  useEffect(() => {
    factoryTransitionRef.current = true;
    restoredSessionKeyRef.current = null;
  }, [selectedFactoryId]);

  useEffect(() => {
    if (restoredSessionKeyRef.current === lastSessionKey) return;
    restoredSessionKeyRef.current = lastSessionKey;
    try {
      const saved = localStorage.getItem(lastSessionKey);
      setRaw({ session: saved || null });
    } catch {
      setRaw({ session: null });
    }
    factoryTransitionRef.current = false;
  }, [lastSessionKey, setRaw]);

  useEffect(() => {
    if (factoryTransitionRef.current || !rawSession) return;
    try {
      localStorage.setItem(lastSessionKey, rawSession);
    } catch {}
  }, [lastSessionKey, rawSession]);

  const sessionId = rawSession;
  const machineId = (raw.machine || raw.machineId || "").trim();
  const draftPrompt = (raw.prompt ?? "").trim();
  const sidebarView: "chats" | "documents" | "feedback" =
    raw.view === "documents"
      ? "documents"
      : raw.view === "feedback"
        ? "feedback"
        : "chats";
  const deepLinkDocId = (raw.doc ?? "").trim() || null;

  useEffect(() => {
    if (machineInitRef.current) return;
    machineInitRef.current = true;

    if (machineId) {
      setSelectedMachineId(machineId);
      if (raw.machineId && !raw.machine) {
        setRaw({ machine: machineId, machineId: null });
      }
      return;
    }

    const fromStore = useUiStore.getState().selectedMachineId;
    if (fromStore) {
      setRaw({ machine: fromStore, machineId: null });
      setSelectedMachineId(fromStore);
    }
  }, [machineId, raw.machine, raw.machineId, setRaw, setSelectedMachineId]);

  useEffect(() => {
    if (machineId) {
      setSelectedMachineId(machineId);
    }
  }, [machineId, setSelectedMachineId]);

  const setSessionId = useCallback(
    (id: string) => setRaw({ session: id || null }),
    [setRaw]
  );

  const setMachineId = useCallback(
    (id: string | null) => setRaw({ machine: id || null, machineId: null }),
    [setRaw]
  );

  const clearDraftPrompt = useCallback(() => setRaw({ prompt: null }), [setRaw]);

  const setSidebarView = useCallback(
    (v: "chats" | "documents" | "feedback") =>
      setRaw({ view: v === "chats" ? null : v }),
    [setRaw]
  );

  const clearDeepLinkDoc = useCallback(() => setRaw({ doc: null }), [setRaw]);

  const setDocumentsMachine = useCallback(
    (id: string | null) => {
      if (id) setRaw({ view: "documents", machine: id, machineId: null });
      else setRaw({ machine: null, machineId: null });
    },
    [setRaw]
  );

  return useMemo(
    () => ({
      sessionId,
      machineId,
      draftPrompt,
      sidebarView,
      deepLinkDocId,
      setSessionId,
      setMachineId,
      setSidebarView,
      setDocumentsMachine,
      clearDraftPrompt,
      clearDeepLinkDoc,
    }),
    [
      sessionId,
      machineId,
      draftPrompt,
      sidebarView,
      deepLinkDocId,
      setSessionId,
      setMachineId,
      setSidebarView,
      setDocumentsMachine,
      clearDraftPrompt,
      clearDeepLinkDoc,
    ]
  );
}
