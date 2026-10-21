export type { ChatSseDonePayload } from "@/lib/chat/sse-types";

export type StreamCompletionStatus = "complete" | "aborted" | "error";

export type StreamCompletionContract = {
  status: StreamCompletionStatus;
  messageId?: string;
  cacheHit?: boolean;
};
