"use client";

import { GeminiChatLayout } from "@/components/chat/gemini/Layout";
import { useChatPageController } from "@/hooks/chat/useChatPageController";
import { useChatStore } from "@/stores/chatStore";
import { useRouter } from "next/navigation";
import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
  type ComponentType,
} from "react";

function ChatContent() {
  const c = useChatPageController();
  const router = useRouter();

  useEffect(() => {
    if (c.sidebarView === "documents") {
      const url = c.machineId
        ? `/documents?machine=${encodeURIComponent(c.machineId)}`
        : "/documents";
      router.replace(url);
      return;
    }
    if (c.sidebarView === "feedback") {
      router.replace("/feedback");
    }
  }, [c.sidebarView, c.machineId, router]);

  const [docViewer, setDocViewer] = useState<{
    docId: string;
    page?: number;
    title?: string | null;
    mimeType?: string | null;
    factoryId?: string | null;
    machineId?: string | null;
    highlight?: string;
  } | null>(null);
  const [DocumentViewer, setDocumentViewer] = useState<ComponentType<any> | null>(null);
  const [RCAPanel, setRCAPanel] = useState<ComponentType<any> | null>(null);

  useEffect(() => {
    if (!docViewer || DocumentViewer) return;
    let active = true;
    void import("@/components/documents/DocumentViewer").then((m) => {
      if (active) setDocumentViewer(() => m.DocumentViewer);
    });
    return () => {
      active = false;
    };
  }, [DocumentViewer, docViewer]);

  useEffect(() => {
    if (!c.rcaOpen || RCAPanel) return;
    let active = true;
    void import("@/components/chat/RCAPanel").then((m) => {
      if (active) setRCAPanel(() => m.RCAPanel);
    });
    return () => {
      active = false;
    };
  }, [RCAPanel, c.rcaOpen]);

  const handleOpenDocument = useCallback(
    (docId: string, page?: number, title?: string | null, highlight?: string) => {
      const match = c.indexedDocuments.find((d) => d.doc_id === docId);
      setDocViewer({
        docId,
        page,
        title: title ?? match?.title ?? match?.source_file,
        mimeType: match?.mime_type,
        factoryId: match?.factory_id ?? c.selectedFactoryId,
        machineId: match?.machine_id ?? c.machineId ?? null,
        highlight,
      });
    },
    [c.indexedDocuments, c.selectedFactoryId, c.machineId]
  );

  const setRcaOpen = c.setRcaOpen;

  const chatSession = useMemo(
    () => ({
      username: c.username,
      sessionId: c.sessionId,
      factoryId: c.selectedFactoryId,
      machineId: c.machineId || null,
      inputRef: c.inputRef,
      messagesLoading: c.sessionSync.messagesLoading,
      sessionBlocked: c.sessionBlocked,
      indexedDocuments: c.indexedDocuments,
      indexedLoading: c.indexedLoading,
      machinesEnabled: c.composerReady,
      desktop: false,
      onSend: c.send,
      onSuggestion: c.sendSuggestion,
      onAbort: c.abortAsk,
      onRegenerate: c.handleRegenerate,
      onVerifyMessage: c.handleVerifyMessage,
      onOpenRca: () => setRcaOpen(true),
      onRetryError: c.handleRetryError,
      onClearError: () => useChatStore.getState().setError(""),
      onOpenDocument: handleOpenDocument,
      onMachineChange: c.setMachineId,
      onOpenSidebar: () => {},
    }),
    [
      c.username,
      c.sessionId,
      c.selectedFactoryId,
      c.machineId,
      c.inputRef,
      c.sessionSync.messagesLoading,
      c.sessionBlocked,
      c.indexedDocuments,
      c.indexedLoading,
      c.composerReady,
      c.send,
      c.sendSuggestion,
      c.abortAsk,
      c.handleRegenerate,
      c.handleVerifyMessage,
      c.handleRetryError,
      c.setMachineId,
      setRcaOpen,
      handleOpenDocument,
    ]
  );

  if (c.sidebarView !== "chats") {
    return null;
  }

  return (
    <>
      <GeminiChatLayout chatSession={chatSession} />

      {docViewer && DocumentViewer && (
        <DocumentViewer
          key={docViewer.docId}
          docId={docViewer.docId}
          title={docViewer.title}
          mimeType={docViewer.mimeType}
          initialPage={docViewer.page}
          highlight={docViewer.highlight}
          factoryId={docViewer.factoryId}
          machineId={docViewer.machineId}
          onClose={() => setDocViewer(null)}
        />
      )}

      {c.rcaOpen && RCAPanel && (
        <RCAPanel
          open={c.rcaOpen}
          machineId={c.machineId || null}
          onClose={() => c.setRcaOpen(false)}
        />
      )}
    </>
  );
}

export default function ChatPageInner() {
  return (
    <Suspense
      fallback={
        <div className="flex items-center justify-center h-full text-sm text-gemini-muted dark:text-gemini-dark-muted gemini-theme-transition">
          Loading chat…
        </div>
      }
    >
      <ChatContent />
    </Suspense>
  );
}
