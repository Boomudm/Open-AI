import { authHeaders, handleUnauthorized } from "@/lib/auth";
import { parseApiError } from "@/lib/errors";
import { parseSseChunk, type ChatStreamEventHandlers } from "@/lib/chatStream";
import type { AskResponse, ChatAttachment, ChatCapabilities, ConfidenceTier, Paginated, PaginatedResponse, Source } from "./types";
import { http } from "./http";
import { mintStreamTicket } from "./streams";

export const chatApi = {
  createSession: (title?: string | null, factoryId?: string | null) =>
    http<{
      session_id: string;
      title?: string | null;
      pinned?: boolean;
      context?: Record<string, unknown> | null;
    }>(
      "/api/v1/chat/sessions",
      {
        method: "POST",
        body: JSON.stringify({
          title: title ?? null,
          factory_id: factoryId || null,
        }),
      }
    ),

  updateSession: (
    sessionId: string,
    patch: { title?: string | null; pinned?: boolean }
  ) =>
    http<{
      session_id: string;
      title?: string | null;
      pinned?: boolean;
      context?: Record<string, unknown> | null;
    }>(
      `/api/v1/chat/sessions/${sessionId}`,
      {
        method: "PATCH",
        body: JSON.stringify(patch),
      }
    ),

  listSessions: (params?: {
    page?: number;
    page_size?: number;
    for_sidebar?: boolean;
    include_session_id?: string;
    factory_id?: string | null;
  }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    if (params?.for_sidebar) qs.set("for_sidebar", "true");
    if (params?.include_session_id) qs.set("include_session_id", params.include_session_id);
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    const query = qs.toString();
    return http<
      Paginated<{
        session_id: string;
        title: string | null;
        pinned: boolean;
        message_count: number;
        created_at: string;
        updated_at: string;
        context?: Record<string, unknown> | null;
        factory_id?: string | null;
      }>
    >(`/api/v1/chat/sessions${query ? `?${query}` : ""}`);
  },

  deleteSession: (sessionId: string) =>
    http<void>(`/api/v1/chat/sessions/${sessionId}`, { method: "DELETE" }),

  listMessages: async (sessionId: string, factoryId?: string | null) => {
    type ChatMessageRow = {
      message_id: string;
      role: string;
      content: string;
      sources: Source[] | null;
      confidence_tier?: ConfidenceTier | null;
      cache_hit?: boolean;
      created_at: string;
      attachments?: ChatAttachment[];
    };
    const pageSize = 50;
    const maxMessages = 500;
    const all: ChatMessageRow[] = [];
    let page = 1;
    let total = 0;
    do {
      const qs = new URLSearchParams({
        page: String(page),
        page_size: String(pageSize),
      });
      if (factoryId) qs.set("factory_id", factoryId);
      const res = await http<PaginatedResponse<ChatMessageRow>>(
        `/api/v1/chat/${sessionId}/messages?${qs.toString()}`
      );
      total = res.total;
      all.push(...res.items);
      if (all.length >= maxMessages || all.length >= total) break;
      page += 1;
    } while ((page - 1) * pageSize < total);
    return all.slice(0, maxMessages);
  },

  getChatCapabilities: () =>
    http<ChatCapabilities>("/api/v1/chat/capabilities"),

  ask: (sessionId: string, body: {
    question: string;
    filter?: Record<string, unknown>;
    top_k?: number;
    stream?: boolean;
  }, options?: { signal?: AbortSignal }) =>
    http<AskResponse>(`/api/v1/chat/${sessionId}/ask`, {
      method: "POST",
      body: JSON.stringify(body),
      signal: options?.signal,
    }),

  askStream: async (
    sessionId: string,
    body: {
      question: string;
      filter?: Record<string, unknown>;
      top_k?: number;
    },
    handlers: ChatStreamEventHandlers,
    options?: { signal?: AbortSignal }
  ): Promise<void> => {
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
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      buffer = parseSseChunk(buffer, handlers);
      if (options?.signal?.aborted) {
        await reader.cancel();
        break;
      }
    }
    if (buffer.trim()) {
      parseSseChunk(`${buffer}\n\n`, handlers);
    }
  },

  askWithAttachments: async (
    sessionId: string,
    body: {
      question: string;
      filter?: Record<string, unknown>;
      top_k?: number;
      files: File[];
    },
    options?: { signal?: AbortSignal }
  ): Promise<AskResponse> => {
    const form = new FormData();
    form.append("question", body.question);
    if (body.filter && Object.keys(body.filter).length > 0) {
      form.append("filter_json", JSON.stringify(body.filter));
    }
    form.append("top_k", String(body.top_k ?? 6));
    for (const file of body.files) {
      form.append("files", file);
    }
    const ticket = await mintStreamTicket("chat_ask", sessionId);
    const askUrl = ticket
      ? `/api/v1/chat/${sessionId}/ask?ticket=${encodeURIComponent(ticket)}`
      : `/api/v1/chat/${sessionId}/ask`;
    const res = await fetch(askUrl, {
      method: "POST",
      headers: authHeaders(),
      credentials: "same-origin",
      body: form,
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
    return res.json() as Promise<AskResponse>;
  },

  transcribeAudio: async (blob: Blob, filename = "speech.webm") => {
    const form = new FormData();
    form.append("file", blob, filename);
    const res = await fetch("/api/v1/chat/transcribe", {
      method: "POST",
      credentials: "same-origin",
      headers: authHeaders(),
      body: form,
    });
    if (!res.ok) {
      const text = await res.text();
      throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
    }
    return res.json() as Promise<{ text: string }>;
  },

  verifyChatMessage: (messageId: string, factoryId: string) =>
    http<{ cache_id: string; verified: boolean }>(
      `/api/v1/chat/messages/${messageId}/verify?factory_id=${encodeURIComponent(factoryId)}`,
      { method: "POST" }
    )
};
