import type { Source } from "@/lib/api";
import type { ChatStreamStatus } from "@/lib/chat/sse-types";

export type ChatSessionRow = {
  session_id: string;
  title: string | null;
  pinned?: boolean;
  message_count?: number;
  created_at: string;
  updated_at: string;
  context?: Record<string, unknown> | null;
  factory_id?: string | null;
};

const DEFAULT_TITLES = new Set(["new chat", "new_chat", "แชทใหม่"]);

export function isDefaultTitle(title: string | null | undefined): boolean {
  const t = title?.trim();
  if (!t) return true;
  return DEFAULT_TITLES.has(t.toLowerCase());
}

export function isEmptyDefaultSession(session: ChatSessionRow): boolean {
  return isDefaultTitle(session.title) && (session.message_count ?? 0) === 0;
}

export function findReusableEmptySession(
  sessions: ChatSessionRow[],
  excludeId?: string | null
): ChatSessionRow | undefined {
  return sessions.find(
    (s) =>
      s.session_id !== excludeId &&
      isEmptyDefaultSession(s)
  );
}

export type ChatAttachmentMeta = {
  filename: string;
  mime_type: string;
  url?: string;
  sort_order?: number;
  previewUrl?: string;
};

export type ChatMessageRow = {
  message_id: string;
  role: "user" | "assistant" | string;
  content: string;
  sources?: Source[] | null;
  confidence_tier?: "high" | "medium" | "low" | null;
  cache_hit?: boolean;
  verified_at?: string | null;
  created_at: string;
  attachments?: ChatAttachmentMeta[];
};

export type ChatMsg = {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  cache_hit?: boolean;
  confidence_tier?: "high" | "medium" | "low";
  citations_verified?: boolean;
  verified?: boolean;
  attachments?: ChatAttachmentMeta[];
  retrieval_report?: import("@/lib/api").RetrievalReport | null;
  system_degradation?: boolean;
  /** Safe activity metadata captured from real stream events (never raw model reasoning). */
  workSummary?: {
    durationMs: number;
    status: ChatStreamStatus;
    sourceCount: number;
  };
};

const CHUNK_CITATION_RE = /\s*\[chunk_id:[^\]]+\]\.?/gi;

export function stripChunkCitations(content: string): string {
  return content
    .replace(CHUNK_CITATION_RE, "")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const UUID_RE =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string): boolean {
  return UUID_RE.test(value);
}

export function mapApiMessages(rows: ChatMessageRow[]): ChatMsg[] {
  return rows.map((m) => ({
    id: m.message_id,
    role: m.role === "assistant" ? "assistant" : "user",
    content:
      m.role === "assistant" ? stripChunkCitations(m.content) : m.content,
    sources: (m.sources as Source[] | undefined) ?? undefined,
    confidence_tier: m.confidence_tier ?? undefined,
    cache_hit: m.cache_hit ?? undefined,
    verified: Boolean(m.verified_at),
    attachments: m.attachments?.map((att) => ({
      filename: att.filename,
      mime_type: att.mime_type,
      url: att.url,
      sort_order: att.sort_order,
    })),
  }));
}

export function formatSessionTime(iso: string): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("th-TH", {
      day: "2-digit",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function sessionLabel(session: ChatSessionRow): string {
  const title = session.title?.trim();
  if (title && !isDefaultTitle(title)) return title;
  const mc = session.message_count ?? 0;
  // Legacy rows used title "New chat" once messages existed; null title = draft empty chat.
  if (mc > 0 || title?.toLowerCase() === "new chat") {
    return `แชท · ${formatSessionTime(session.updated_at)}`;
  }
  return "แชทใหม่";
}
