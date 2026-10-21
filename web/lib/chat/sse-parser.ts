import { parseChatSources } from "@/lib/chat/source-parse";
import type {
  ChatConfidenceTier,
  ChatSseCitationBlockPayload,
  ChatSseDonePayload,
  ChatSseEvent,
  ChatSseMetaPayload,
  ChatSseSourcesPayload,
  ChatStreamEventHandlers,
} from "@/lib/chat/sse-types";

function asRecord(value: unknown): Record<string, unknown> | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function parseStringArray(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const items = value.filter((t): t is string => typeof t === "string");
  return items.length > 0 ? items : undefined;
}

function parseMeta(raw: Record<string, unknown>): ChatSseMetaPayload {
  const pipeline = raw.pipeline;
  return {
    intent: typeof raw.intent === "string" ? raw.intent : undefined,
    route: typeof raw.route === "string" ? raw.route : undefined,
    routing_reason:
      typeof raw.routing_reason === "string" ? raw.routing_reason : undefined,
    pipeline:
      pipeline === "machinery" || pipeline === "enterprise"
        ? pipeline
        : undefined,
    agentic_tools_called: parseStringArray(raw.agentic_tools_called),
    cache_id: typeof raw.cache_id === "string" ? raw.cache_id : undefined,
    stream_phase:
      raw.stream_phase === "searching" ||
      raw.stream_phase === "reading" ||
      raw.stream_phase === "generating"
        ? raw.stream_phase
        : undefined,
  };
}

function parseSources(raw: Record<string, unknown>): ChatSseSourcesPayload {
  const used = asRecord(raw.used_filters);
  const reportRaw = asRecord(raw.retrieval_report);
  const retrieval_report = reportRaw
    ? {
        degraded: Boolean(reportRaw.degraded),
        degraded_reasons: parseStringArray(reportRaw.degraded_reasons),
        failed_collections: parseStringArray(reportRaw.failed_collections),
        vector_count:
          typeof reportRaw.vector_count === "number" ? reportRaw.vector_count : undefined,
        lexical_count:
          typeof reportRaw.lexical_count === "number" ? reportRaw.lexical_count : undefined,
        fusion_method:
          typeof reportRaw.fusion_method === "string" ? reportRaw.fusion_method : undefined,
        intent: typeof reportRaw.intent === "string" ? reportRaw.intent : undefined,
      }
    : undefined;
  return {
    sources: parseChatSources(raw.sources),
    fallback_level:
      typeof raw.fallback_level === "number" ? raw.fallback_level : undefined,
    used_filters: used ?? undefined,
    retrieval_report: retrieval_report ?? null,
  };
}

function parseDone(raw: Record<string, unknown>): ChatSseDonePayload {
  const tier = raw.confidence_tier;
  const validTier =
    tier === "high" || tier === "medium" || tier === "low" ? tier : undefined;
  return {
    assistant_message_id:
      typeof raw.assistant_message_id === "string"
        ? raw.assistant_message_id
        : undefined,
    cache_hit: typeof raw.cache_hit === "boolean" ? raw.cache_hit : undefined,
    intent: typeof raw.intent === "string" ? raw.intent : undefined,
    route: typeof raw.route === "string" ? raw.route : undefined,
    top_doc_score:
      typeof raw.top_doc_score === "number" ? raw.top_doc_score : undefined,
    confidence_tier: validTier as ChatConfidenceTier | undefined,
  };
}

function parseEvent(eventName: string | null, raw: Record<string, unknown>): ChatSseEvent | null {
  switch (eventName) {
    case "connected":
      return { type: "connected", data: {} };
    case "token":
    case "token_provisional": {
      const delta = raw.delta;
      if (typeof delta !== "string" || delta.length === 0) return null;
      return { type: "token", data: { delta } };
    }
    case "citation_block": {
      const text = typeof raw.text === "string" ? raw.text : "";
      return {
        type: "citation_block",
        data: {
          text,
          citations_verified: raw.citations_verified === true,
        },
      };
    }
    case "meta":
      return { type: "meta", data: parseMeta(raw) };
    case "sources":
      return { type: "sources", data: parseSources(raw) };
    case "done":
      return { type: "done", data: parseDone(raw) };
    case "error":
      return {
        type: "error",
        data: {
          code: String(raw.code ?? "error"),
          message: String(raw.message ?? "stream error"),
        },
      };
    default:
      return null;
  }
}

export function dispatchChatSseEvent(
  event: ChatSseEvent,
  handlers: ChatStreamEventHandlers
): void {
  switch (event.type) {
    case "connected":
      handlers.onConnected?.();
      break;
    case "token":
    case "token_provisional":
      handlers.onToken?.(event.data.delta);
      break;
    case "citation_block":
      handlers.onCitationBlock?.(event.data.text, event.data.citations_verified);
      break;
    case "meta":
      handlers.onMeta?.(event.data);
      break;
    case "sources":
      handlers.onSources?.(event.data);
      break;
    case "done":
      handlers.onDone?.(event.data);
      break;
    case "error":
      handlers.onError?.(event.data.code, event.data.message);
      break;
  }
}

/** Parse SSE buffer; returns unconsumed remainder. */
export function parseSseChunk(
  buffer: string,
  handlers: ChatStreamEventHandlers
): string {
  let remainder = buffer;
  let boundary = remainder.indexOf("\n\n");
  while (boundary >= 0) {
    const rawEvent = remainder.slice(0, boundary);
    remainder = remainder.slice(boundary + 2);
    boundary = remainder.indexOf("\n\n");

    if (!rawEvent.trim() || rawEvent.startsWith(":")) continue;

    let eventName: string | null = null;
    const dataLines: string[] = [];
    for (const line of rawEvent.split("\n")) {
      if (line.startsWith("event:")) {
        eventName = line.slice(6).trim();
      } else if (line.startsWith("data:")) {
        dataLines.push(line.slice(5).trimStart());
      }
    }
    if (dataLines.length === 0) continue;

    let payload: Record<string, unknown> = {};
    try {
      payload = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
    } catch {
      continue;
    }

    const event = parseEvent(eventName, payload);
    if (event) dispatchChatSseEvent(event, handlers);
  }
  return remainder;
}
