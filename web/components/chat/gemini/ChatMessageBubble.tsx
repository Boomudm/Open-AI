"use client";

import { DegradedRetrievalBanner } from "@/components/chat/gemini/DegradedRetrievalBanner";
import { OperatorTrustGate } from "@/components/trust/OperatorTrustGate";
import { AiMessageActions } from "@/components/chat/gemini/AiMessageActions";
import { ChatAttachmentChips } from "@/components/chat/gemini/ChatAttachmentChips";
import { ChatThinkingStatus } from "@/components/chat/gemini/ChatThinkingStatus";
import { SparkMessageContent } from "@/components/chat/gemini/SparkMessageContent";
import { FeedbackReportButton } from "@/components/feedback/FeedbackReportButton";
import { useChatSession } from "@/contexts/ChatSessionContext";
import type { ChatMsg } from "@/lib/chat";
import { isUuid } from "@/lib/chat";
import { cn } from "@/lib/cn";
import { markCitationUserInitiated } from "@/lib/citationPresentation";
import { isAdminUser } from "@/lib/auth";
import { FileText } from "lucide-react";
import {
  selectChatSending,
  selectChatStreamStartedAt,
  selectChatStreamStatus,
  useChatStore,
} from "@/stores/chatStore";
import { memo, useCallback } from "react";

export type ChatMessageBubbleProps = {
  message: ChatMsg;
};

function ChatMessageBubbleInner({ message }: ChatMessageBubbleProps) {
  const { factoryId, sessionId, machineId, onRegenerate, onVerifyMessage } =
    useChatSession();
  const isSelected = useChatStore((s) => s.selectedMsgId === message.id);
  const regenerating = useChatStore((s) => s.regeneratingId === message.id);
  const verifying = useChatStore((s) => s.verifyingId === message.id);
  const selectAssistant = useChatStore((s) => s.selectAssistant);
  const sending = useChatStore(selectChatSending);
  const streamStatus = useChatStore(selectChatStreamStatus);
  const streamStartedAt = useChatStore(selectChatStreamStartedAt);
  const pendingSources = useChatStore((s) => s.pendingStreamSources);
  const sourceCount = pendingSources.length;

  const isUser = message.role === "user";
  const selected = !isUser && isSelected;
  const hasSources = Boolean(message.sources?.length);
  const canReport =
    !isUser && factoryId && sessionId && isUuid(message.id);
  const isStreamingAssistant =
    !isUser &&
    sending &&
    !message.workSummary &&
    message.id.startsWith("asst-stream-");
  const answerStarted = isStreamingAssistant && message.content.trim().length > 0;

  const handleSelect = useCallback(() => {
    if (!hasSources) return;
    markCitationUserInitiated();
    selectAssistant(message.id);
  }, [hasSources, message.id, selectAssistant]);

  const handleRegenerate = useCallback(() => {
    onRegenerate?.(message.id);
  }, [message.id, onRegenerate]);

  const handleVerify = useCallback(() => {
    onVerifyMessage?.(message.id);
  }, [message.id, onVerifyMessage]);

  if (isUser) {
    return (
      <article className="flex justify-end w-full" aria-label="ข้อความจากคุณ">
        <div className="max-w-[min(85%,40rem)]">
          {message.attachments && message.attachments.length > 0 && (
            <div className="flex justify-end mb-2">
              <ChatAttachmentChips attachments={message.attachments} compact />
            </div>
          )}
          <div className="chat-user-bubble inline-block rounded-[1.25rem] px-4 py-2.5 gemini-theme-transition">
            <p className="chat-system-body whitespace-pre-wrap text-left">
              {message.content}
            </p>
          </div>
        </div>
      </article>
    );
  }

  return (
    <article
      className="w-full max-w-[min(100%,42rem)]"
      aria-label="คำตอบจาก Neo"
    >
      {message.retrieval_report?.degraded ? (
        <DegradedRetrievalBanner report={message.retrieval_report} />
      ) : null}

      {isStreamingAssistant ? (
        <ChatThinkingStatus
          status={streamStatus}
          sourceCount={sourceCount}
          sources={pendingSources}
          startedAt={streamStartedAt}
          mode="live"
          compact={answerStarted}
          className={answerStarted ? "mb-2" : "mb-4"}
        />
      ) : message.workSummary ? (
        <ChatThinkingStatus
          status={message.workSummary.status}
          sourceCount={message.workSummary.sourceCount}
          sources={message.sources}
          durationMs={message.workSummary.durationMs}
          mode="completed"
          className="mb-3"
        />
      ) : null}

      <div className="chat-answer-surface">
        <SparkMessageContent content={message.content} />
      </div>

      {!isStreamingAssistant && message.content.trim() ? (
        <div className="mt-3 flex items-center gap-x-2 gap-y-1 flex-wrap chat-system-meta">
          <AiMessageActions
            content={message.content}
            onRegenerate={onRegenerate ? handleRegenerate : undefined}
            regenerating={regenerating}
            onVerify={onVerifyMessage ? handleVerify : undefined}
            verifying={verifying}
            showVerify={isAdminUser()}
            verified={Boolean(message.verified)}
          />

          {hasSources && (
            <button
              type="button"
              onClick={handleSelect}
              className={cn(
                "inline-flex items-center gap-1.5 min-h-[44px] px-3 py-2 rounded-full text-xs font-medium",
                "gemini-theme-transition gemini-focus-ring border",
                selected
                  ? "border-gemini-blue/50 dark:border-gemini-dark-blue/50 bg-gemini-blue/10 dark:bg-gemini-dark-blue/10 text-gemini-blue dark:text-gemini-dark-blue"
                  : "border-gemini-border/70 dark:border-gemini-dark-border/70 text-gemini-muted dark:text-gemini-dark-muted hover:border-gemini-blue/40 hover:text-gemini-blue dark:hover:text-gemini-dark-blue"
              )}
              aria-label={`แหล่งอ้างอิง ${message.sources!.length} รายการ`}
            >
              <FileText className="h-4 w-4 shrink-0" aria-hidden />
              แหล่งอ้างอิง {message.sources!.length}
            </button>
          )}

          {canReport && (
            <FeedbackReportButton
              compact
              payload={{
                factoryId: factoryId!,
                sourceType: "rag_answer",
                sessionId,
                messageId: message.id,
                machineId,
                contextLabel: message.content.slice(0, 200),
                contextSnapshot: {
                  answer_excerpt: message.content.slice(0, 500),
                  cited_sources: message.sources?.map((s) => ({
                    doc_id: s.doc_id,
                    page: s.page,
                    chunk_id: s.chunk_id,
                    title: s.title ?? s.source_file,
                  })),
                },
              }}
            />
          )}
        </div>
      ) : null}
    </article>
  );
}

export const ChatMessageBubble = memo(
  ChatMessageBubbleInner,
  (prev, next) =>
    prev.message.id === next.message.id &&
    prev.message.content === next.message.content &&
    prev.message.verified === next.message.verified &&
    prev.message.sources?.length === next.message.sources?.length &&
    prev.message.attachments?.length === next.message.attachments?.length &&
    prev.message.workSummary === next.message.workSummary &&
    Boolean(prev.message.retrieval_report?.degraded) ===
      Boolean(next.message.retrieval_report?.degraded)
);
