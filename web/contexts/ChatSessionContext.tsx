"use client";

import type { IndexedDocument } from "@/lib/api";
import {
  createContext,
  useContext,
  type ReactNode,
  type RefObject,
} from "react";

export type ChatSessionContextValue = {
  username: string;
  sessionId?: string;
  factoryId?: string | null;
  machineId: string | null;
  inputRef: RefObject<HTMLTextAreaElement>;
  messagesLoading?: boolean;
  sessionBlocked?: boolean;
  indexedDocuments: IndexedDocument[];
  indexedLoading?: boolean;
  machinesEnabled?: boolean;
  desktop: boolean;
  onSend: (attachments?: File[]) => void;
  onSuggestion?: (question: string) => void;
  onAbort?: () => void;
  onRegenerate?: (assistantMessageId: string) => void;
  onVerifyMessage?: (assistantMessageId: string) => void;
  onOpenRca?: () => void;
  onRetryError?: () => void;
  onClearError?: () => void;
  onOpenDocument?: (docId: string, page?: number, title?: string | null, highlight?: string) => void;
  onMachineChange: (id: string | null) => void;
  onOpenSidebar: () => void;
};

const ChatSessionContext = createContext<ChatSessionContextValue | null>(null);

export function ChatSessionProvider({
  value,
  children,
}: {
  value: ChatSessionContextValue;
  children: ReactNode;
}) {
  return (
    <ChatSessionContext.Provider value={value}>{children}</ChatSessionContext.Provider>
  );
}

export function useChatSession(): ChatSessionContextValue {
  const ctx = useContext(ChatSessionContext);
  if (!ctx) {
    throw new Error("useChatSession must be used within ChatSessionProvider");
  }
  return ctx;
}
