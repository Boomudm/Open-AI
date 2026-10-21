import { authHeaders, handleUnauthorized } from "@/lib/auth";
import { mintStreamTicket } from "@/lib/api/streams";
import { parseApiError } from "@/lib/errors";
import type { ChatStreamEventHandlers } from "@/lib/chat/sse-types";
import { parseSseChunk } from "@/lib/chat/sse-parser";

export type ChatStreamRequest = {
  question: string;
  filter?: Record<string, unknown>;
  top_k?: number;
};

/** Consume a typed SSE chat stream from POST /api/v1/chat/{sessionId}/ask. */
export async function consumeChatStream(
  sessionId: string,
  body: ChatStreamRequest,
  handlers: ChatStreamEventHandlers,
  options?: { signal?: AbortSignal }
): Promise<void> {
  const ticket = await mintStreamTicket("chat_ask", sessionId);
  const askUrl = ticket
    ? `/api/v1/chat/${sessionId}/ask?ticket=${encodeURIComponent(ticket)}`
    : `/api/v1/chat/${sessionId}/ask`;
  const res = await fetch(askUrl, {
    method: "POST",
    headers: {
      ...authHeaders(),
      "Content-Type": "application/json",
    },
    credentials: "same-origin",
    body: JSON.stringify({ ...body, stream: true }),
    signal: options?.signal,
  });
  if (res.status === 401 && typeof window !== "undefined") {
    handleUnauthorized();
    throw new Error("401 unauthorized");
  }
  if (!res.ok) {
    const text = await res.text();
    throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
  }
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error("streaming not supported");
  }
  // The `done` event is the protocol's terminal frame — the answer is final
  // once it arrives. Anything after it (server-side post-answer housekeeping
  // errors, tunnel/proxy teardown mid-close) must not surface as a failure of
  // an already-delivered answer.
  let finished = false;
  const wrapped: ChatStreamEventHandlers = {
    ...handlers,
    onDone: (payload) => {
      finished = true;
      handlers.onDone?.(payload);
    },
    onError: (code, message) => {
      if (finished) return;
      handlers.onError?.(code, message);
    },
  };
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = parseSseChunk(buffer, wrapped);
      if (finished || options?.signal?.aborted) {
        await reader.cancel();
        break;
      }
    }
  } catch (err) {
    if (!finished) throw err;
    return;
  }
  if (!finished && buffer.trim()) {
    parseSseChunk(`${buffer}\n\n`, wrapped);
  }
}
