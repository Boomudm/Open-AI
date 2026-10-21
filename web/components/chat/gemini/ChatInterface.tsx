"use client";

import { ChatHeader } from "@/components/chat/gemini/ChatHeader";
import { ChatHistory } from "@/components/chat/gemini/ChatHistory";
import { ChatWelcomeState } from "@/components/chat/gemini/ChatWelcomeState";
import { GeminiFogBackground } from "@/components/chat/gemini/GeminiFogBackground";
import { MessageInput } from "@/components/chat/gemini/MessageInput";
import { ErrorState } from "@/components/ui/State";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { MSG_QUERY_FAILED } from "@/lib/messages.th";
import {
  selectChatError,
  selectChatMessages,
  selectChatSending,
  useChatStore,
} from "@/stores/chatStore";
import { useEffect, useState, type ComponentType } from "react";

export function GeminiChatInterface() {
  const {
    desktop,
    machineId,
    messagesLoading,
    onOpenSidebar,
    onOpenRca,
    onRetryError,
    onClearError,
  } =
    useChatSession();
  const error = useChatStore(selectChatError);
  const messages = useChatStore(selectChatMessages);
  const sending = useChatStore(selectChatSending);
  const sourcesOpen = useChatStore((s) => s.sourcesOpen);
  const emptyChat = messages.length === 0 && !sending && !messagesLoading;
  const [CitationDrawer, setCitationDrawer] = useState<ComponentType | null>(null);

  useEffect(() => {
    if (!sourcesOpen || CitationDrawer) return;
    let active = true;
    void import("@/components/chat/gemini/CitationDrawer").then((m) => {
      if (active) setCitationDrawer(() => m.CitationDrawer);
    });
    return () => {
      active = false;
    };
  }, [CitationDrawer, sourcesOpen]);

  return (
    <main
      className="relative flex flex-col flex-1 min-w-0 min-h-0 h-full gemini-main-gradient gemini-theme-transition overflow-hidden"
      aria-label="Neo Chat"
    >
      {emptyChat ? <GeminiFogBackground /> : null}

      <ChatHeader
        desktop={desktop}
        machineId={machineId}
        onOpenSidebar={onOpenSidebar}
        onOpenRca={onOpenRca}
        emptyChat={emptyChat}
      />

      {emptyChat ? (
        <div className="relative z-[1] flex flex-1 min-h-0 flex-col items-center justify-center px-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <div className="flex w-full max-w-[820px] flex-col items-center gap-7 sm:gap-8 -mt-[6vh]">
            <ChatWelcomeState />
            <MessageInput emptyChat />
          </div>
        </div>
      ) : (
        <>
          <ChatHistory />
          {error && !sending && (
            <div className="relative z-[1] shrink-0 px-4 pb-2 max-w-3xl mx-auto w-full">
              <ErrorState
                title={MSG_QUERY_FAILED}
                message={error}
                onRetry={onRetryError ?? onClearError}
                className="py-3"
              />
            </div>
          )}
          <MessageInput emptyChat={false} />
        </>
      )}

      {emptyChat && error && !sending && (
        <div className="relative z-[1] shrink-0 px-4 pb-2 max-w-3xl mx-auto w-full">
          <ErrorState
            title={MSG_QUERY_FAILED}
            message={error}
            onRetry={onRetryError ?? onClearError}
            className="py-3"
          />
        </div>
      )}

      {sourcesOpen && CitationDrawer && <CitationDrawer />}
    </main>
  );
}
