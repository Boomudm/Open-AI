"use client";

import { ChatMessageBubble } from "@/components/chat/gemini/ChatMessageBubble";
import { GeminiLoadingIndicator } from "@/components/chat/gemini/ChatLoadingIndicator";
import { StreamingBubble } from "@/components/chat/gemini/StreamingBubble";
import { useChatSession } from "@/contexts/ChatSessionContext";
import { MSG_LOADING_HISTORY } from "@/lib/messages.th";
import {
  selectChatMessages,
  selectChatSending,
  selectChatStreamStatus,
  useChatStore,
} from "@/stores/chatStore";
import { useCallback, useEffect, useRef } from "react";

const SCROLL_THRESHOLD = 150;

export function ChatHistory() {
  const { messagesLoading } = useChatSession();
  const messages = useChatStore(selectChatMessages);
  const sending = useChatStore(selectChatSending);
  const streamStatus = useChatStore(selectChatStreamStatus);
  const visitedStageCount = streamStatus.visitedPhases?.length ?? 0;

  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const userScrolledUpRef = useRef(false);
  const isEmpty = messages.length === 0 && !sending && !messagesLoading;

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    userScrolledUpRef.current = distanceFromBottom > SCROLL_THRESHOLD;
  }, []);

  useEffect(() => {
    if (scrollRef.current && !userScrolledUpRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, sending, streamStatus.phase, visitedStageCount]);

  useEffect(() => {
    const content = contentRef.current;
    if (!content || typeof ResizeObserver === "undefined") return;

    const observer = new ResizeObserver(() => {
      const scroller = scrollRef.current;
      if (!scroller || userScrolledUpRef.current) return;
      scroller.scrollTop = scroller.scrollHeight;
    });
    observer.observe(content);
    return () => observer.disconnect();
  }, [messages.length]);

  return (
    <div
      ref={scrollRef}
      onScroll={handleScroll}
      className="chat-system flex-1 min-h-0 overflow-y-auto gemini-scrollbar bg-transparent gemini-theme-transition"
      role="log"
      aria-label="บทสนทนา"
      aria-relevant="additions"
      tabIndex={0}
    >
      {messagesLoading && messages.length === 0 ? (
        <div className="flex items-center justify-center h-full">
          <GeminiLoadingIndicator label={MSG_LOADING_HISTORY} />
        </div>
      ) : isEmpty ? (
        null
      ) : (
        <div
          ref={contentRef}
          className="mx-auto max-w-[48rem] space-y-7 px-4 pb-8 pt-3 sm:space-y-9 sm:px-8 sm:pb-10 sm:pt-4"
        >
          {messages.map((m) => (
            <ChatMessageBubble key={m.id} message={m} />
          ))}
          <StreamingBubble />
        </div>
      )}
    </div>
  );
}
