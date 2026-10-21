"use client";

import { ChatThinkingStatus } from "@/components/chat/gemini/ChatThinkingStatus";
import { GeminiLoadingIndicator } from "@/components/chat/gemini/ChatLoadingIndicator";
import {
  selectChatMessages,
  selectChatSending,
  selectChatStreamStartedAt,
  selectChatStreamStatus,
  useChatStore,
} from "@/stores/chatStore";
import { memo } from "react";

function streamPhaseLabel(
  phase: ReturnType<typeof selectChatStreamStatus>["phase"]
): string {
  switch (phase) {
    case "routing":
      return "กำลังวิเคราะห์คำถาม…";
    case "searching":
      return "กำลังค้นหาเอกสารที่เกี่ยวข้อง…";
    case "reading":
      return "กำลังอ่านข้อมูลที่พบ…";
    case "citations":
      return "กำลังจัดอ้างอิง…";
    case "generating":
      return "";
    default:
      return "กำลังค้นหาและสรุปคำตอบจากเอกสาร…";
  }
}

function StreamingBubbleInner() {
  const sending = useChatStore(selectChatSending);
  const streamStatus = useChatStore(selectChatStreamStatus);
  const streamStartedAt = useChatStore(selectChatStreamStartedAt);
  const messages = useChatStore(selectChatMessages);
  const pendingSources = useChatStore((s) => s.pendingStreamSources);
  const sourceCount = pendingSources.length;
  const hasStreamingAssistant = messages.some((m) =>
    m.id.startsWith("asst-stream-")
  );

  if (!sending) return null;

  if (hasStreamingAssistant) return null;

  if (
    streamStatus.phase === "routing" ||
    streamStatus.phase === "searching" ||
    streamStatus.phase === "reading" ||
    streamStatus.phase === "generating" ||
    streamStatus.phase === "citations"
  ) {
    return (
      <div className="w-full max-w-[min(100%,42rem)] pt-0.5">
        <ChatThinkingStatus
          status={streamStatus}
          sourceCount={sourceCount}
          sources={pendingSources}
          startedAt={streamStartedAt}
          mode="live"
        />
      </div>
    );
  }

  const label = streamPhaseLabel(streamStatus.phase);
  if (!label) return null;

  return <GeminiLoadingIndicator label={label} />;
}

export const StreamingBubble = memo(StreamingBubbleInner);
