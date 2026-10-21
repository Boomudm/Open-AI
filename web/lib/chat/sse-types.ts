import type { Source } from "@/lib/api";

export type ChatStreamRoute = "rag" | "sql" | "agentic" | "cache" | string;

export type ChatConfidenceTier = "high" | "medium" | "low";

export type ChatPipeline = "machinery" | "enterprise";

/** Routing / intent metadata emitted before tokens. */
export type ChatSseMetaPayload = {
  intent?: string;
  route?: ChatStreamRoute;
  routing_reason?: string;
  pipeline?: ChatPipeline;
  /** Agentic tool invocations (when route is agentic). */
  agentic_tools_called?: string[];
  cache_id?: string;
  /** RAG progress: searching → reading → generating */
  stream_phase?: "searching" | "reading" | "generating";
};

/** Citation payload emitted after generation completes. */
export type ChatSseSourcesPayload = {
  sources: Source[];
  fallback_level?: number;
  used_filters?: Record<string, unknown>;
  retrieval_report?: import("@/lib/api").RetrievalReport | null;
};

/** Final persistence metadata. */
export type ChatSseDonePayload = {
  assistant_message_id?: string;
  cache_hit?: boolean;
  intent?: string;
  route?: ChatStreamRoute;
  top_doc_score?: number;
  confidence_tier?: ChatConfidenceTier;
  citations_verified?: boolean;
};

export type ChatSseTokenPayload = {
  delta: string;
};

export type ChatSseErrorPayload = {
  code: string;
  message: string;
};

export type ChatSseConnectedPayload = Record<string, never>;

export type ChatSseCitationBlockPayload = {
  text: string;
  citations_verified: boolean;
};

export type ChatSseEventName =
  | "connected"
  | "token"
  | "token_provisional"
  | "citation_block"
  | "meta"
  | "sources"
  | "done"
  | "error";

export type ChatSseEvent =
  | { type: "connected"; data: ChatSseConnectedPayload }
  | { type: "token"; data: ChatSseTokenPayload }
  | { type: "token_provisional"; data: ChatSseTokenPayload }
  | { type: "citation_block"; data: ChatSseCitationBlockPayload }
  | { type: "meta"; data: ChatSseMetaPayload }
  | { type: "sources"; data: ChatSseSourcesPayload }
  | { type: "done"; data: ChatSseDonePayload }
  | { type: "error"; data: ChatSseErrorPayload };

export type ChatStreamEventHandlers = {
  onConnected?: () => void;
  onToken?: (delta: string) => void;
  onCitationBlock?: (text: string, citationsVerified: boolean) => void;
  onMeta?: (meta: ChatSseMetaPayload) => void;
  onSources?: (payload: ChatSseSourcesPayload) => void;
  onDone?: (payload: ChatSseDonePayload) => void;
  onError?: (code: string, message: string) => void;
};

/** Live stream state surfaced in the composer / message list. */
export type ChatStreamPhase =
  | "idle"
  | "routing"
  | "searching"
  | "reading"
  | "generating"
  | "citations"
  | "done"
  | "error";

/** High-level, user-safe activity stages reached by the chat pipeline. */
export type ChatStreamStage = Extract<
  ChatStreamPhase,
  "routing" | "searching" | "reading" | "generating" | "citations"
>;

export type ChatStreamStatus = {
  phase: ChatStreamPhase;
  route?: ChatStreamRoute;
  intent?: string;
  toolsCalled?: string[];
  pipeline?: ChatPipeline;
  /** Monotonic stage history used for the live and completed activity summary. */
  visitedPhases?: ChatStreamStage[];
};
