import type { RetrievalReport, Source } from "@/lib/api";
import { stripChunkCitations, type ChatMsg } from "@/lib/chat";
import type {
  ChatSseDonePayload,
  ChatSseMetaPayload,
  ChatStreamPhase,
  ChatStreamStage,
  ChatStreamStatus,
} from "@/lib/chat/sse-types";
import { create } from "zustand";
import { subscribeWithSelector } from "zustand/middleware";

type ChatStoreState = {
  messages: ChatMsg[];
  input: string;
  sending: boolean;
  regeneratingId: string | null;
  verifyingId: string | null;
  error: string;
  selectedMsgId: string | null;
  sourcesOpen: boolean;
  composerReady: boolean;
  streamStatus: ChatStreamStatus;
  streamStartedAt: number | null;
  pendingStreamSources: Source[];

  resetForSession: () => void;
  setMessages: (messages: ChatMsg[]) => void;
  upsertMessage: (message: ChatMsg) => void;
  patchMessage: (id: string, patch: Partial<ChatMsg>) => void;
  removeMessages: (predicate: (msg: ChatMsg) => boolean) => void;
  appendUserMessage: (message: ChatMsg) => void;
  startAssistantStream: (id: string) => void;
  appendStreamDelta: (id: string, delta: string) => void;
  replaceStreamContent: (id: string, content: string) => void;
  setStreamPhase: (phase: ChatStreamStatus["phase"]) => void;
  applyStreamMeta: (meta: ChatSseMetaPayload) => void;
  setPendingStreamSources: (sources: Source[]) => void;
  finalizeStream: (
    tempId: string,
    done: ChatSseDonePayload,
    sources: Source[],
    retrievalReport?: RetrievalReport | null
  ) => string;
  rollbackOptimisticAsk: (
    tempUserId: string | null,
    streamAsstId?: string | null
  ) => void;
  setInput: (value: string) => void;
  setSending: (sending: boolean) => void;
  setRegeneratingId: (id: string | null) => void;
  setVerifyingId: (id: string | null) => void;
  setError: (error: string) => void;
  setSelectedMsgId: (id: string | null) => void;
  setSourcesOpen: (open: boolean) => void;
  setComposerReady: (ready: boolean) => void;
  selectAssistant: (id: string) => void;
  closeSources: () => void;
  markVerified: (messageId: string) => void;
};

const initialStreamStatus = (): ChatStreamStatus => ({
  phase: "idle",
  visitedPhases: [],
});

const STREAM_STAGES: ChatStreamStage[] = [
  "routing",
  "searching",
  "reading",
  "generating",
  "citations",
];

type ChatWorkSummary = NonNullable<ChatMsg["workSummary"]>;

const WORK_SUMMARY_CACHE_KEY = "spark-chat-work-summaries-v1";
const WORK_SUMMARY_CACHE_LIMIT = 120;
const STREAM_PHASES = new Set<ChatStreamPhase>([
  "idle",
  "routing",
  "searching",
  "reading",
  "generating",
  "citations",
  "done",
  "error",
]);

function readWorkSummaryCache(): Record<string, ChatWorkSummary> {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.sessionStorage.getItem(WORK_SUMMARY_CACHE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const safeEntries = Object.entries(parsed)
      .slice(-WORK_SUMMARY_CACHE_LIMIT)
      .flatMap(([id, value]) => {
        if (!value || typeof value !== "object") return [];
        const summary = value as Partial<ChatWorkSummary>;
        const status = summary.status as Partial<ChatStreamStatus> | undefined;
        if (
          typeof summary.durationMs !== "number" ||
          !Number.isFinite(summary.durationMs) ||
          typeof summary.sourceCount !== "number" ||
          !status ||
          !STREAM_PHASES.has(status.phase as ChatStreamPhase)
        ) {
          return [];
        }
        return [
          [
            id,
            {
              durationMs: Math.max(0, summary.durationMs),
              sourceCount: Math.max(0, Math.floor(summary.sourceCount)),
              status: status as ChatStreamStatus,
            },
          ] as const,
        ];
      });
    return Object.fromEntries(safeEntries);
  } catch {
    return {};
  }
}

function cacheWorkSummary(messageId: string, summary: ChatWorkSummary): void {
  if (typeof window === "undefined") return;
  try {
    const cache = readWorkSummaryCache();
    delete cache[messageId];
    cache[messageId] = summary;
    const limited = Object.fromEntries(
      Object.entries(cache).slice(-WORK_SUMMARY_CACHE_LIMIT)
    );
    window.sessionStorage.setItem(
      WORK_SUMMARY_CACHE_KEY,
      JSON.stringify(limited)
    );
  } catch {
    // Storage can be disabled or full; the in-memory summary still works.
  }
}

function isStreamStage(phase: ChatStreamPhase): phase is ChatStreamStage {
  return STREAM_STAGES.includes(phase as ChatStreamStage);
}

function advanceStreamStatus(
  status: ChatStreamStatus,
  phase: ChatStreamPhase
): ChatStreamStatus {
  if (isStreamStage(status.phase) && isStreamStage(phase)) {
    const currentIndex = STREAM_STAGES.indexOf(status.phase);
    const nextIndex = STREAM_STAGES.indexOf(phase);
    if (nextIndex < currentIndex) return status;
  }
  const visited = status.visitedPhases ?? [];
  const visitedPhases =
    isStreamStage(phase) && !visited.includes(phase)
      ? [...visited, phase]
      : visited;
  return { ...status, phase, visitedPhases };
}

function patchMessageById(
  messages: ChatMsg[],
  id: string,
  patcher: (message: ChatMsg) => ChatMsg
): ChatMsg[] {
  if (messages.length === 0) return messages;
  const last = messages[messages.length - 1];
  if (last?.id === id) {
    const patched = patcher(last);
    if (patched === last) return messages;
    return [...messages.slice(0, -1), patched];
  }
  const idx = messages.findIndex((m) => m.id === id);
  if (idx < 0) return messages;
  const patched = patcher(messages[idx]);
  if (patched === messages[idx]) return messages;
  const next = messages.slice();
  next[idx] = patched;
  return next;
}

export const useChatStore = create<ChatStoreState>()(
  subscribeWithSelector((set, get) => ({
    messages: [],
    input: "",
    sending: false,
    regeneratingId: null,
    verifyingId: null,
    error: "",
    selectedMsgId: null,
    sourcesOpen: false,
    composerReady: false,
    streamStatus: initialStreamStatus(),
    streamStartedAt: null,
    pendingStreamSources: [],

    resetForSession: () =>
      set({
        messages: [],
        input: "",
        sending: false,
        regeneratingId: null,
        verifyingId: null,
        selectedMsgId: null,
        sourcesOpen: false,
        error: "",
        streamStatus: initialStreamStatus(),
        streamStartedAt: null,
        pendingStreamSources: [],
      }),

    setMessages: (messages) =>
      set((s) => {
        const cachedSummaries = readWorkSummaryCache();
        const summaries = new Map(
          s.messages
            .filter((message) => message.workSummary)
            .map((message) => [message.id, message.workSummary] as const)
        );
        return {
          messages: messages.map((message) => {
            const workSummary =
              summaries.get(message.id) ?? cachedSummaries[message.id];
            return workSummary ? { ...message, workSummary } : message;
          }),
        };
      }),

    upsertMessage: (message) =>
      set((s) => {
        const nextMessage =
          message.role === "assistant"
            ? { ...message, content: stripChunkCitations(message.content) }
            : message;
        const idx = s.messages.findIndex((m) => m.id === message.id);
        if (idx >= 0) {
          const next = [...s.messages];
          next[idx] = nextMessage;
          return { messages: next };
        }
        return { messages: [...s.messages, nextMessage] };
      }),

    patchMessage: (id, patch) =>
      set((s) => ({
        messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
      })),

    removeMessages: (predicate) =>
      set((s) => ({ messages: s.messages.filter((m) => !predicate(m)) })),

    appendUserMessage: (message) =>
      set((s) => ({ messages: [...s.messages, message] })),

    startAssistantStream: (id) =>
      set((s) => ({
        messages: [...s.messages, { id, role: "assistant", content: "" }],
        streamStatus: { phase: "routing", visitedPhases: ["routing"] },
        streamStartedAt: Date.now(),
        pendingStreamSources: [],
      })),

    appendStreamDelta: (id, delta) =>
      set((s) => ({
        messages: patchMessageById(s.messages, id, (m) =>
          m.content || delta ? { ...m, content: `${m.content}${delta}` } : m
        ),
        streamStatus:
          s.streamStatus.phase === "routing" ||
          s.streamStatus.phase === "searching" ||
          s.streamStatus.phase === "reading"
            ? advanceStreamStatus(s.streamStatus, "generating")
            : s.streamStatus,
      })),

    replaceStreamContent: (id, content) => {
      const nextContent = stripChunkCitations(content);
      set((s) => ({
        messages: patchMessageById(s.messages, id, (m) =>
          m.content === nextContent ? m : { ...m, content: nextContent }
        ),
      }));
    },

    setStreamPhase: (phase) =>
      set((s) => ({
        streamStatus: advanceStreamStatus(s.streamStatus, phase),
      })),

    applyStreamMeta: (meta) =>
      set((s) => {
        const merged: ChatStreamStatus = {
          ...s.streamStatus,
          route: meta.route ?? s.streamStatus.route,
          intent: meta.intent ?? s.streamStatus.intent,
          toolsCalled:
            meta.agentic_tools_called ?? s.streamStatus.toolsCalled,
          pipeline: meta.pipeline ?? s.streamStatus.pipeline,
        };
        return {
          streamStatus: meta.stream_phase
            ? advanceStreamStatus(merged, meta.stream_phase)
            : merged,
        };
      }),

    setPendingStreamSources: (sources) =>
      set((s) => ({
        pendingStreamSources: sources,
        streamStatus: advanceStreamStatus(s.streamStatus, "citations"),
      })),

    finalizeStream: (tempId, done, sources, retrievalReport) => {
      const asstId = done.assistant_message_id ?? tempId;
      let completedSummary: ChatWorkSummary | null = null;
      set((s) => {
        const completedStatus: ChatStreamStatus = {
          ...s.streamStatus,
          phase: "done",
          route: done.route ?? s.streamStatus.route,
          intent: done.intent ?? s.streamStatus.intent,
        };
        const durationMs = s.streamStartedAt
          ? Math.max(0, Date.now() - s.streamStartedAt)
          : 0;
        const summary: ChatWorkSummary = {
          durationMs,
          status: completedStatus,
          sourceCount: sources.length,
        };
        completedSummary = summary;
        return {
          messages: patchMessageById(s.messages, tempId, (m) =>
            m.id === tempId
              ? {
                  ...m,
                  id: asstId,
                  content: stripChunkCitations(m.content),
                  sources,
                  cache_hit: done.cache_hit,
                  confidence_tier: done.confidence_tier,
                  retrieval_report: retrievalReport ?? m.retrieval_report,
                  workSummary: summary,
                }
              : m
          ),
          selectedMsgId: asstId,
          sourcesOpen: false,
          streamStatus: completedStatus,
          streamStartedAt: null,
          pendingStreamSources: [],
        };
      });
      if (completedSummary) cacheWorkSummary(asstId, completedSummary);
      return asstId;
    },

    rollbackOptimisticAsk: (tempUserId, streamAsstId) =>
      set((s) => ({
        messages: s.messages.filter(
          (m) =>
            m.id !== tempUserId &&
            (streamAsstId ? m.id !== streamAsstId : !m.id.startsWith("asst-stream-"))
        ),
        streamStatus: initialStreamStatus(),
        streamStartedAt: null,
        pendingStreamSources: [],
      })),

    setInput: (input) => set({ input }),
    setSending: (sending) =>
      set((s) => ({
        sending,
        streamStatus: sending ? s.streamStatus : initialStreamStatus(),
        streamStartedAt: sending ? s.streamStartedAt : null,
      })),
    setRegeneratingId: (regeneratingId) => set({ regeneratingId }),
    setVerifyingId: (verifyingId) => set({ verifyingId }),
    setError: (error) => set({ error }),
    setSelectedMsgId: (selectedMsgId) => set({ selectedMsgId }),
    setSourcesOpen: (sourcesOpen) => set({ sourcesOpen }),
    setComposerReady: (composerReady) => set({ composerReady }),

    selectAssistant: (id) => set({ selectedMsgId: id, sourcesOpen: true }),
    closeSources: () => set({ sourcesOpen: false, selectedMsgId: null }),

    markVerified: (messageId) =>
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === messageId ? { ...m, verified: true } : m
        ),
      })),
  }))
);

/** Shallow selectors for hot paths — avoids re-rendering on unrelated store updates. */
export const selectChatMessages = (s: ChatStoreState) => s.messages;
export const selectChatInput = (s: ChatStoreState) => s.input;
export const selectChatSending = (s: ChatStoreState) => s.sending;
export const selectChatError = (s: ChatStoreState) => s.error;
export const selectChatStreamStatus = (s: ChatStoreState) => s.streamStatus;
export const selectChatStreamStartedAt = (s: ChatStoreState) =>
  s.streamStartedAt;

export function getActiveSources(
  messages: ChatMsg[],
  selectedId: string | null,
  lastAssistantId: string | null
): Source[] {
  const activeId = selectedId ?? lastAssistantId;
  const msg = messages.find((m) => m.id === activeId);
  return msg?.sources ?? [];
}

export function findLastAssistantId(messages: ChatMsg[]): string | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "assistant") return messages[i].id;
  }
  return null;
}
