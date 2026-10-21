"use client";

import { GeminiChatInterface } from "@/components/chat/gemini/ChatInterface";
import { ChatSessionProvider } from "@/contexts/ChatSessionContext";
import { useIsDesktopNav } from "@/hooks/useMediaQuery";
import type { ChatSessionContextValue } from "@/contexts/ChatSessionContext";

export type GeminiChatLayoutProps = {
  chatSession: ChatSessionContextValue;
};

export function GeminiChatLayout({ chatSession }: GeminiChatLayoutProps) {
  const desktop = useIsDesktopNav();

  const sessionValue: ChatSessionContextValue = {
    ...chatSession,
    desktop,
    onOpenSidebar: () => {
      window.dispatchEvent(new CustomEvent("spark:open-workspace-sidebar"));
    },
  };

  return (
    <ChatSessionProvider value={sessionValue}>
      <div className="flex flex-col flex-1 min-h-0 h-full overflow-hidden bg-gemini-bg dark:bg-gemini-dark-bg gemini-theme-transition">
        <GeminiChatInterface />
      </div>
    </ChatSessionProvider>
  );
}
