import { useCallback, useEffect, useRef } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, type AskResponse } from "@/lib/api";
import type { ChatMsg } from "@/lib/chat";
import { consumeChatStream } from "@/lib/chat/stream-consumer";
import { documentTypeFilter, topKForModel } from "@/lib/chatSettings";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useChatStore } from "@/stores/chatStore";
import type { ChatSettings } from "@/lib/chatSettings";

export type AskQuestionOptions = {
  replaceAssistantId?: string;
  appendUserMessage?: boolean;
  files?: File[];
};

type UseChatAskParams = {
  sessionId: string | undefined;
  machineId: string | null;
  factoryId: string | null;
  chatSettings: ChatSettings;
  activeSessionRef: React.MutableRefObject<string | undefined>;
};

let askIdCounter = 0;

const FALLBACK_PROGRESS: ReadonlyArray<{
  delayMs: number;
  phase: "searching" | "reading" | "generating";
}> = [
  { delayMs: 350, phase: "searching" },
  { delayMs: 1_800, phase: "reading" },
  { delayMs: 6_000, phase: "generating" },
];

const ASK_TIMEOUT_MS = 95_000;

const COMBINING_MARK_RE = /[\p{Mark}\u200d\ufe0e\ufe0f]/u;

function takeRevealChunk(value: string, amount: number): [string, string] {
  const points = Array.from(value);
  let end = Math.min(Math.max(1, amount), points.length);
  while (end < points.length && COMBINING_MARK_RE.test(points[end])) end += 1;
  return [points.slice(0, end).join(""), points.slice(end).join("")];
}

// Sized so the reveal is visibly gradual (a few seconds even for medium
// answers) instead of flashing in — backends often deliver the whole answer
// in one or two SSE frames, so this pacing IS the perceived typing speed.
function revealChunkSize(length: number): number {
  if (length > 4_000) return 48;
  if (length > 1_600) return 20;
  if (length > 600) return 10;
  if (length > 240) return 5;
  if (length > 80) return 3;
  return 2;
}

/** Smooths both real token streams and backends that return one large chunk. */
function createProgressiveRenderer(
  append: (delta: string) => void,
  signal: AbortSignal
) {
  let pending = "";
  let pump: Promise<void> | null = null;

  const waitForNextFrame = () =>
    new Promise<void>((resolve) => window.setTimeout(resolve, 28));

  const startPump = () => {
    if (pump || !pending || signal.aborted) return;
    pump = (async () => {
      while (pending && !signal.aborted) {
        const [chunk, remainder] = takeRevealChunk(
          pending,
          revealChunkSize(pending.length)
        );
        pending = remainder;
        if (chunk) append(chunk);
        if (pending) await waitForNextFrame();
      }
    })().finally(() => {
      pump = null;
      if (pending && !signal.aborted) startPump();
    });
  };

  return {
    enqueue(delta: string) {
      if (!delta || signal.aborted) return;
      pending += delta;
      startPump();
    },
    async drain() {
      while (!signal.aborted && (pending || pump)) {
        startPump();
        if (pump) await pump;
      }
    },
  };
}

export function useChatAsk({
  sessionId,
  machineId,
  factoryId,
  chatSettings,
  activeSessionRef,
}: UseChatAskParams) {
  const qc = useQueryClient();
  const askAbortRef = useRef<AbortController | null>(null);
  const lastFailedAskRef = useRef<
    (AskQuestionOptions & { question: string; sessionId: string }) | null
  >(null);
  const prevSessionIdRef = useRef(sessionId);

  useEffect(() => {
    if (prevSessionIdRef.current === sessionId) return;
    askAbortRef.current?.abort();
    prevSessionIdRef.current = sessionId;
    lastFailedAskRef.current = null;
  }, [sessionId]);

  const sending = useChatStore((s) => s.sending);
  const regeneratingId = useChatStore((s) => s.regeneratingId);

  const askQuestion = useCallback(
    async (question: string, options?: AskQuestionOptions) => {
      const files = options?.files ?? [];
      const state = useChatStore.getState();
      if (
        (!question.trim() && files.length === 0) ||
        !sessionId ||
        state.sending ||
        state.regeneratingId
      ) {
        return;
      }

      const {
        setError,
        appendUserMessage,
        setRegeneratingId,
        setSending,
        setSelectedMsgId,
        setSourcesOpen,
        startAssistantStream,
        appendStreamDelta,
        replaceStreamContent,
        setStreamPhase,
        applyStreamMeta,
        setPendingStreamSources,
        finalizeStream,
        rollbackOptimisticAsk,
        removeMessages,
      } = useChatStore.getState();

      setError("");
      const trimmed = question.trim() || "ช่วยอธิบายจากไฟล์ที่แนบ";
      const sendingSessionId = sessionId;
      const replaceId = options?.replaceAssistantId;
      const appendUser = options?.appendUserMessage ?? true;
      const tempUserId = appendUser ? `user-${Date.now()}-${++askIdCounter}` : null;
      const optimisticAttachments =
        files.length > 0
          ? files.map((file, index) => ({
              filename: file.name,
              mime_type: file.type || "application/octet-stream",
              previewUrl: file.type.startsWith("image/")
                ? URL.createObjectURL(file)
                : undefined,
              sort_order: index,
            }))
          : undefined;

      if (appendUser && tempUserId) {
        appendUserMessage({
          id: tempUserId,
          role: "user",
          content: trimmed,
          attachments: optimisticAttachments,
        });
      }
      if (replaceId) {
        setRegeneratingId(replaceId);
      }
      setSending(true);
      setSelectedMsgId(null);
      setSourcesOpen(false);

      const streamAsstId = `asst-stream-${Date.now()}-${++askIdCounter}`;
      let streamFinalized = false;
      let controller: AbortController | null = null;
      const progressTimers: number[] = [];
      let timeoutTimer: number | null = null;
      let timedOut = false;

      try {
        askAbortRef.current?.abort();
        controller = new AbortController();
        askAbortRef.current = controller;
        timeoutTimer = window.setTimeout(() => {
          timedOut = true;
          controller?.abort();
        }, ASK_TIMEOUT_MS);
        const filter: Record<string, unknown> = { only_active: false };
        if (machineId) filter.machine_id = machineId;
        if (factoryId) filter.factory_id = factoryId;
        const docType = documentTypeFilter(chatSettings.ragSources);
        if (docType) filter.document_type = docType;
        const useStream = files.length === 0;
        startAssistantStream(streamAsstId);

        for (const progress of FALLBACK_PROGRESS) {
          progressTimers.push(
            window.setTimeout(() => {
              if (
                controller?.signal.aborted ||
                askAbortRef.current !== controller ||
                activeSessionRef.current !== sendingSessionId
              ) {
                return;
              }
              setStreamPhase(progress.phase);
            }, progress.delayMs)
          );
        }

        if (useStream) {
          let streamSources: ChatMsg["sources"] = [];
          let streamRetrievalReport: ChatMsg["retrieval_report"];
          const protocol = {
            done: null as Parameters<typeof finalizeStream>[1] | null,
          };
          let queuedAnswer = "";
          let verifiedAnswer: string | null = null;
          const renderer = createProgressiveRenderer((delta) => {
            if (activeSessionRef.current !== sendingSessionId) return;
            appendStreamDelta(streamAsstId, delta);
          }, controller.signal);

          await consumeChatStream(
            sendingSessionId,
            {
              question: trimmed,
              filter,
              top_k: topKForModel(chatSettings.model),
            },
            {
              onConnected: () => {
                if (activeSessionRef.current !== sendingSessionId) return;
                setStreamPhase("searching");
              },
              onToken: (delta) => {
                if (activeSessionRef.current !== sendingSessionId) return;
                queuedAnswer += delta;
                renderer.enqueue(delta);
              },
              onCitationBlock: (text) => {
                if (activeSessionRef.current !== sendingSessionId) return;
                if (text.startsWith(queuedAnswer)) {
                  const suffix = text.slice(queuedAnswer.length);
                  queuedAnswer = text;
                  renderer.enqueue(suffix);
                  verifiedAnswer = null;
                } else {
                  verifiedAnswer = text;
                }
              },
              onMeta: (meta) => {
                if (activeSessionRef.current !== sendingSessionId) return;
                applyStreamMeta(meta);
              },
              onSources: (payload) => {
                streamSources = payload.sources;
                streamRetrievalReport = payload.retrieval_report ?? undefined;
                if (activeSessionRef.current !== sendingSessionId) return;
                setPendingStreamSources(payload.sources);
              },
              onDone: (payload) => {
                if (activeSessionRef.current !== sendingSessionId) return;
                protocol.done = payload;
              },
              onError: (_code, message) => {
                throw new Error(message);
              },
            },
            { signal: controller.signal }
          );

          if (!protocol.done && !controller.signal.aborted) {
            throw new Error("การเชื่อมต่อสิ้นสุดก่อนรับคำตอบครบ กรุณาลองอีกครั้ง");
          }
          await renderer.drain();
          if (controller.signal.aborted) return;
          const donePayload = protocol.done;
          if (activeSessionRef.current !== sendingSessionId || !donePayload) return;

          if (verifiedAnswer !== null) {
            replaceStreamContent(streamAsstId, verifiedAnswer);
          }
          if (replaceId && donePayload.assistant_message_id === replaceId) {
            removeMessages((msg) => msg.id === replaceId);
          }
          const finalId = finalizeStream(
            streamAsstId,
            donePayload,
            streamSources ?? [],
            streamRetrievalReport
          );
          if (replaceId && finalId !== replaceId) {
            removeMessages((msg) => msg.id === replaceId);
          }
          streamFinalized = true;
        } else {
          setStreamPhase("searching");
          const res: AskResponse = await api.askWithAttachments(
            sendingSessionId,
            {
              question: trimmed,
              filter,
              top_k: topKForModel(chatSettings.model),
              files,
            },
            { signal: controller.signal }
          );
          if (controller.signal.aborted) return;
          if (activeSessionRef.current !== sendingSessionId) return;
          applyStreamMeta({
            stream_phase: "generating",
            route: res.route ?? undefined,
            intent: res.intent,
          });
          // Sync responses arrive as one block — reveal them progressively
          // like the streaming path instead of flashing the answer in.
          const syncRenderer = createProgressiveRenderer((delta) => {
            if (activeSessionRef.current !== sendingSessionId) return;
            appendStreamDelta(streamAsstId, delta);
          }, controller.signal);
          syncRenderer.enqueue(res.answer);
          await syncRenderer.drain();
          if (controller.signal.aborted) return;
          replaceStreamContent(streamAsstId, res.answer);
          setPendingStreamSources(res.sources);
          if (replaceId && res.assistant_message_id === replaceId) {
            removeMessages((msg) => msg.id === replaceId);
          }
          const finalId = finalizeStream(
            streamAsstId,
            {
              assistant_message_id: res.assistant_message_id ?? undefined,
              cache_hit: res.cache_hit,
              intent: res.intent,
              route: res.route ?? undefined,
              confidence_tier: res.confidence_tier ?? undefined,
              citations_verified: res.citations_verified,
            },
            res.sources,
            res.retrieval_report ?? undefined
          );
          if (replaceId && finalId !== replaceId) {
            removeMessages((msg) => msg.id === replaceId);
          }
          streamFinalized = true;
        }

        if (controller.signal.aborted) return;
        if (activeSessionRef.current !== sendingSessionId) return;
        lastFailedAskRef.current = null;
        qc.invalidateQueries({ queryKey: queryKeys.chatSessions() });
        qc.invalidateQueries({ queryKey: ["chatMessages"] });
      } catch (e) {
        if (
          controller?.signal.aborted ||
          (e instanceof DOMException && e.name === "AbortError")
        ) {
          rollbackOptimisticAsk(files.length === 0 ? null : tempUserId, streamAsstId);
          if (timedOut && activeSessionRef.current === sendingSessionId) {
            lastFailedAskRef.current = {
              question: trimmed,
              sessionId: sendingSessionId,
              files: files.length > 0 ? files : undefined,
              replaceAssistantId: replaceId,
              appendUserMessage: false,
            };
            setError("AI ใช้เวลาตอบนานเกิน 95 วินาที กรุณาลองใหม่อีกครั้ง");
          }
          return;
        }
        if (streamFinalized) {
          // The done frame already landed — the answer is rendered and
          // persisted. A late transport/housekeeping failure must not roll it
          // back or flash "ส่งคำถามไม่สำเร็จ" under a correct answer.
          qc.invalidateQueries({ queryKey: queryKeys.chatSessions() });
          qc.invalidateQueries({ queryKey: ["chatMessages"] });
          return;
        }
        const keepOptimisticUser = Boolean(tempUserId && files.length === 0);
        rollbackOptimisticAsk(
          keepOptimisticUser ? null : tempUserId,
          streamAsstId
        );
        if (activeSessionRef.current === sendingSessionId) {
          lastFailedAskRef.current = {
            question: trimmed,
            sessionId: sendingSessionId,
            files: files.length > 0 ? files : undefined,
            replaceAssistantId: replaceId,
            appendUserMessage: keepOptimisticUser ? false : appendUser,
          };
          setError(parseApiError(e));
        }
      } finally {
        if (timeoutTimer !== null) window.clearTimeout(timeoutTimer);
        progressTimers.forEach((timer) => window.clearTimeout(timer));
        optimisticAttachments?.forEach((a) => {
          if (a.previewUrl) URL.revokeObjectURL(a.previewUrl);
        });
        if (askAbortRef.current === controller) {
          setSending(false);
          setRegeneratingId(null);
          askAbortRef.current = null;
        }
      }
    },
    [sessionId, machineId, factoryId, chatSettings, activeSessionRef, qc]
  );

  const abortAsk = useCallback(() => {
    askAbortRef.current?.abort();
  }, []);

  const retryLastAsk = useCallback(() => {
    const last = lastFailedAskRef.current;
    if (!last || last.sessionId !== sessionId) {
      lastFailedAskRef.current = null;
      return;
    }
    void askQuestion(last.question, {
      files: last.files,
      replaceAssistantId: last.replaceAssistantId,
      appendUserMessage: last.appendUserMessage,
    });
    useChatStore.getState().setError("");
  }, [askQuestion, sessionId]);

  return {
    askQuestion,
    abortAsk,
    retryLastAsk,
    sending,
    regeneratingId,
    lastFailedAskRef,
  };
}
