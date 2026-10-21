"use client";

import { ClaudeStar } from "@/components/chat/gemini/ClaudeStar";
import type {
  ChatStreamStage,
  ChatStreamStatus,
} from "@/lib/chat/sse-types";
import type { Source } from "@/lib/api";
import { cn } from "@/lib/cn";
import {
  BookOpen,
  Brain,
  ChevronDown,
  CircleCheck,
  Clock3,
  FileText,
  PenLine,
  type LucideIcon,
} from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

function stageIcon(stage: ChatStreamStage): LucideIcon {
  switch (stage) {
    case "routing":
      return Brain;
    case "searching":
      return FileText;
    case "reading":
      return BookOpen;
    case "generating":
      return PenLine;
    case "citations":
      return FileText;
  }
}

type ChatThinkingStatusProps = {
  status: ChatStreamStatus;
  sourceCount?: number;
  sources?: Source[];
  className?: string;
  startedAt?: number | null;
  durationMs?: number;
  mode?: "live" | "completed";
  /** When true, collapse to a compact header so the answer can stream visibly. */
  compact?: boolean;
};

const STAGE_ORDER: readonly ChatStreamStage[] = [
  "routing",
  "searching",
  "reading",
  "generating",
  "citations",
];

const INTENT_LABELS: Record<string, string> = {
  factual: "ข้อมูลข้อเท็จจริง",
  analytic: "การวิเคราะห์",
  followup: "คำถามต่อเนื่อง",
  unknown: "คำถามทั่วไป",
  chitchat: "การสนทนาทั่วไป",
  external_live: "ข้อมูลจากระบบที่เชื่อมต่อ",
  compound: "คำถามหลายส่วน",
  clarification: "รายละเอียดเพิ่มเติม",
  policy: "นโยบาย",
  procedure: "ขั้นตอนปฏิบัติ",
  alarm_diagnostic: "การวินิจฉัยอาการขัดข้อง",
  part_lookup: "การค้นหาชิ้นส่วน",
  safety_loto: "ความปลอดภัย / LOTO",
  io_mapping: "การเชื่อมต่อ I/O",
  drawing: "แบบงาน",
  general: "คำถามทั่วไป",
};

function isStage(phase: ChatStreamStatus["phase"]): phase is ChatStreamStage {
  return STAGE_ORDER.some((stage) => stage === phase);
}

function stageLabel(stage: ChatStreamStage): string {
  switch (stage) {
    case "routing":
      return "วิเคราะห์คำถามและเลือกแนวทาง";
    case "searching":
      return "ค้นข้อมูลที่เกี่ยวข้อง";
    case "reading":
      return "อ่านและคัดหลักฐาน";
    case "generating":
      return "เรียบเรียงคำตอบ";
    case "citations":
      return "ตรวจแหล่งอ้างอิง";
  }
}

function activityTitle(status: ChatStreamStatus): string {
  switch (status.route) {
    case "rag":
      return "ค้นหาและสรุปคำตอบจากเอกสารที่เกี่ยวข้อง";
    case "sql":
      return "วิเคราะห์ข้อมูลจากฐานข้อมูลโรงงาน";
    case "agentic":
      return "รวบรวมข้อมูลจากเครื่องมือและแหล่งที่เกี่ยวข้อง";
    case "cache":
      return "ตรวจคำตอบที่เคยผ่านการตรวจสอบ";
    default:
      return "วิเคราะห์คำถามและเตรียมคำตอบ";
  }
}

function mappedIntent(intent?: string): string | null {
  if (!intent) return null;
  return INTENT_LABELS[intent.toLowerCase()] ?? "คำถามทั่วไป";
}

/** Claude-style internal monologue for each pipeline stage. */
function chainOfThought(
  stage: ChatStreamStage,
  status: ChatStreamStatus,
  sourceCount: number,
  sources: Source[]
): string {
  const intent = mappedIntent(status.intent);
  const topTitles = sources
    .slice(0, 2)
    .map((s) => s.title || s.source_file)
    .filter(Boolean) as string[];

  switch (stage) {
    case "routing":
      return intent
        ? `ผู้ใช้ถามเรื่อง${intent} ฉันควรแยกประเด็นหลักก่อน แล้วเลือกแหล่งข้อมูลที่ตอบได้ตรงที่สุดโดยไม่เดา`
        : `ผู้ใช้ถามมาเป็นภาษาไทย ฉันควรทำความเข้าใจเจตนาของคำถามก่อน แล้วเลือกแนวทางตอบที่อิงหลักฐาน`;
    case "searching":
      if (status.route === "sql") {
        return `คำถามนี้น่าจะอิงข้อมูลเชิงตัวเลขจากฐานข้อมูลโรงงาน ฉันจะค้นระเบียนที่เกี่ยวข้องก่อนสรุป`;
      }
      if (status.route === "cache") {
        return `อาจมีคำตอบที่เคยตรวจแล้วและยังใช้ได้ ฉันจะตรวจแคชก่อนเพื่อไม่ให้ตอบซ้ำโดยไม่จำเป็น`;
      }
      return intent
        ? `ต่อไปฉันจะค้นเอกสารที่เกี่ยวกับ${intent} เพื่อหาหลักฐานที่ตอบคำถามนี้ได้จริง`
        : `ต่อไปฉันจะค้นเอกสารที่เกี่ยวข้องกับคำถามนี้ เพื่อหาช่วงข้อความที่ใช้ตอบได้`;
    case "reading":
      if (sourceCount > 0 && topTitles.length > 0) {
        return `พบหลักฐานประมาณ ${sourceCount} รายการ เช่น ${topTitles.join(" และ ")} — ฉันจะอ่านเฉพาะส่วนที่ตรงคำถาม แล้วคัดประเด็นที่ใช้ตอบได้`;
      }
      if (sourceCount > 0) {
        return `พบหลักฐานประมาณ ${sourceCount} รายการ ฉันจะเปรียบเทียบเนื้อหา แล้วเก็บเฉพาะข้อความที่สนับสนุนคำตอบ`;
      }
      return `ฉันกำลังอ่านบริบทจากเอกสารที่ดึงมา และคัดเฉพาะส่วนที่ตอบคำถามได้โดยไม่เติมข้อมูลเกินหลักฐาน`;
    case "generating": {
      const toolCount = Math.max(0, status.toolsCalled?.length ?? 0);
      if (status.route === "agentic" && toolCount > 0) {
        return `ฉันได้ผลจากเครื่องมือ ${toolCount} รายการแล้ว ต่อไปจะเรียบเรียงเป็นคำตอบที่อ่านง่ายและอิงหลักฐาน`;
      }
      return `ข้อมูลพอสำหรับตอบแล้ว ฉันจะเรียบเรียงเป็นขั้นตอนที่ชัดเจน ใช้ภาษาที่ตรงประเด็น และไม่สรุปเกินหลักฐาน`;
    }
    case "citations":
      return sourceCount > 0
        ? `ก่อนจบ ฉันจะจับคู่ประโยคสำคัญกับแหล่งอ้างอิง ${sourceCount} รายการ เพื่อให้ตรวจย้อนกลับได้`
        : `ก่อนจบ ฉันจะตรวจว่าประโยคสำคัญสอดคล้องกับข้อมูลที่ใช้ตอบ และไม่ชี้แหล่งเกินจริง`;
  }
}

function safeDuration(value: number | undefined): number {
  return Number.isFinite(value) ? Math.max(0, value ?? 0) : 0;
}

function elapsedFrom(startedAt: number | null | undefined): number {
  if (startedAt == null || !Number.isFinite(startedAt)) return 0;
  return Math.max(0, Date.now() - startedAt);
}

function formatDuration(durationMs: number, minimumSeconds = 0): string {
  const seconds = Math.max(
    minimumSeconds,
    Math.round(safeDuration(durationMs) / 1000)
  );
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function useTypewriter(fullText: string, enabled: boolean): string {
  const [visibleLen, setVisibleLen] = useState(enabled ? 0 : fullText.length);
  const fullTextRef = useRef(fullText);
  const [reduceMotion, setReduceMotion] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(prefers-reduced-motion: reduce)");
    const sync = () => setReduceMotion(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    fullTextRef.current = fullText;
    if (!enabled || reduceMotion) {
      setVisibleLen(fullText.length);
      return;
    }
    setVisibleLen(0);
  }, [enabled, fullText, reduceMotion]);

  useEffect(() => {
    if (!enabled || reduceMotion) return;
    if (visibleLen >= fullText.length) return;

    const remaining = fullText.length - visibleLen;
    const step = remaining > 40 ? 6 : remaining > 16 ? 3 : 2;
    const delay = remaining > 40 ? 8 : 14;
    const timer = window.setTimeout(() => {
      setVisibleLen((prev) =>
        Math.min(fullTextRef.current.length, prev + step)
      );
    }, delay);
    return () => window.clearTimeout(timer);
  }, [enabled, fullText.length, reduceMotion, visibleLen]);

  if (!enabled || reduceMotion) return fullText;
  return fullText.slice(0, visibleLen);
}

export function ChatThinkingStatus({
  status,
  sourceCount,
  sources = [],
  className,
  startedAt,
  durationMs,
  mode = "live",
  compact = false,
}: ChatThinkingStatusProps) {
  const panelId = useId();
  const headingId = useId();
  const [completedExpanded, setCompletedExpanded] = useState(false);
  const [elapsedMs, setElapsedMs] = useState(0);

  const currentStage = isStage(status.phase) ? status.phase : undefined;

  useEffect(() => {
    if (mode !== "live") return;
    const tick = () => {
      setElapsedMs(startedAt != null ? elapsedFrom(startedAt) : 0);
    };
    tick();
    const timer = window.setInterval(tick, 1000);
    return () => window.clearInterval(timer);
  }, [mode, startedAt]);

  const stages = useMemo(() => {
    const reached = new Set<ChatStreamStage>(status.visitedPhases ?? []);
    if (currentStage) reached.add(currentStage);
    if (reached.size === 0) return ["routing"] satisfies ChatStreamStage[];
    return STAGE_ORDER.filter((stage) => reached.has(stage));
  }, [currentStage, status.visitedPhases]);

  const safeSourceCount = Number.isFinite(sourceCount)
    ? Math.max(0, Math.floor(sourceCount ?? 0))
    : 0;
  const completedDuration =
    durationMs == null ? elapsedFrom(startedAt) : safeDuration(durationMs);
  const showTimeline =
    (mode === "live" && !compact) || (mode === "completed" && completedExpanded);

  const thoughts = useMemo(
    () =>
      stages.map((stage) => ({
        stage,
        text: chainOfThought(stage, status, safeSourceCount, sources),
      })),
    [safeSourceCount, sources, stages, status]
  );

  const liveCurrentText =
    mode === "live" && currentStage
      ? thoughts.find((t) => t.stage === currentStage)?.text ?? ""
      : "";
  const typedCurrent = useTypewriter(
    liveCurrentText,
    mode === "live" && !compact
  );
  const typing =
    mode === "live" &&
    !compact &&
    Boolean(currentStage) &&
    typedCurrent.length < liveCurrentText.length;

  const stalled = mode === "live" && !compact && elapsedMs >= 20_000;

  const timeline = showTimeline ? (
    <section
      id={panelId}
      role="region"
      aria-labelledby={headingId}
      className={cn("min-w-0", mode === "completed" && "mt-1.5")}
    >
      {mode === "completed" ? (
        <h3
          id={headingId}
          className="chat-activity-heading mb-3 min-w-0 text-[0.8125rem] font-normal leading-6"
        >
          {activityTitle(status)}
        </h3>
      ) : null}

      <ol className="chat-thinking-rail relative mt-0 space-y-4">
        {thoughts.map(({ stage, text }) => {
          const current = mode === "live" && stage === currentStage;
          // Live: Claude-style single stream — only expand the current thought.
          // Past stages stay as compact icon+label so the panel does not bury the answer.
          if (mode === "live" && !current) {
            const Icon = stageIcon(stage);
            return (
              <li
                key={stage}
                data-stage={stage}
                data-state="complete"
                className="chat-activity-step relative grid min-w-0 grid-cols-[1.125rem_minmax(0,1fr)] gap-x-3"
              >
                <span
                  className="relative z-[1] mt-0.5 flex h-[1.125rem] w-[1.125rem] items-center justify-center bg-[var(--gemini-main-bg)] text-gemini-muted dark:text-gemini-dark-muted"
                  aria-hidden
                >
                  <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />
                </span>
                <p className="chat-activity-detail text-[0.75rem] leading-5 text-gemini-muted/80 dark:text-gemini-dark-muted/80">
                  {stageLabel(stage)}
                </p>
              </li>
            );
          }

          const Icon = stageIcon(stage);
          const displayText =
            current && mode === "live"
              ? typedCurrent || text.slice(0, 1)
              : text;

          return (
            <li
              key={stage}
              data-stage={stage}
              data-state={current ? "current" : "complete"}
              aria-current={current ? "step" : undefined}
              className="chat-activity-step relative grid min-w-0 grid-cols-[1.125rem_minmax(0,1fr)] gap-x-3"
            >
              <span
                className="relative z-[1] mt-0.5 flex h-[1.125rem] w-[1.125rem] items-center justify-center bg-[var(--gemini-main-bg)] text-gemini-muted dark:text-gemini-dark-muted"
                aria-hidden
              >
                <Icon
                  className={cn(
                    "h-3.5 w-3.5",
                    current &&
                      "motion-safe:animate-pulse motion-reduce:animate-none"
                  )}
                  strokeWidth={1.75}
                />
              </span>
              <div className="min-w-0">
                <p className="sr-only">{stageLabel(stage)}</p>
                <p
                  className={cn(
                    "chat-activity-detail break-words text-[0.8125rem] leading-[1.6] [overflow-wrap:anywhere]",
                    "text-gemini-muted dark:text-gemini-dark-muted",
                    current && "chat-activity-label"
                  )}
                >
                  {displayText}
                  {current && typing ? (
                    <span
                      className="ml-0.5 inline-block h-[1em] w-[2px] translate-y-[0.1em] bg-current align-baseline motion-safe:animate-pulse"
                      aria-hidden
                    />
                  ) : null}
                </p>
                {stage === "citations" && sources.length > 0 ? (
                  <ul className="mt-2.5 overflow-hidden rounded-xl border border-gemini-border/70 bg-black/[0.03] dark:border-gemini-dark-border/70 dark:bg-white/[0.03]">
                    {sources.slice(0, 3).map((source, index) => {
                      const title =
                        source.title || source.source_file || "เอกสารอ้างอิง";
                      return (
                        <li
                          key={`${source.doc_id ?? title}-${index}`}
                          className="flex min-w-0 items-center gap-2.5 border-b border-gemini-border/50 px-3 py-2 last:border-b-0 dark:border-gemini-dark-border/50"
                        >
                          <FileText
                            className="h-3.5 w-3.5 shrink-0 text-gemini-muted dark:text-gemini-dark-muted"
                            aria-hidden
                          />
                          <span className="min-w-0 flex-1 truncate text-[0.75rem] text-gemini-muted dark:text-gemini-dark-muted">
                            {title}
                          </span>
                          {source.page ? (
                            <span className="shrink-0 text-[0.75rem] text-gemini-muted dark:text-gemini-dark-muted">
                              หน้า {source.page}
                            </span>
                          ) : null}
                        </li>
                      );
                    })}
                    {sources.length > 3 ? (
                      <li className="px-3 py-2 text-[0.75rem] text-gemini-muted dark:text-gemini-dark-muted">
                        และอีก {sources.length - 3} แหล่งข้อมูล
                      </li>
                    ) : null}
                  </ul>
                ) : null}
              </div>
            </li>
          );
        })}

        {mode === "completed" ? (
          <li className="relative grid min-w-0 grid-cols-[1.125rem_minmax(0,1fr)] gap-x-3">
            <span
              className="relative z-[1] mt-0.5 flex h-[1.125rem] w-[1.125rem] items-center justify-center bg-[var(--gemini-main-bg)] text-gemini-muted dark:text-gemini-dark-muted"
              aria-hidden
            >
              <CircleCheck className="h-3.5 w-3.5" strokeWidth={1.75} />
            </span>
            <p className="chat-activity-label text-[0.8125rem] leading-[1.55]">
              Done
            </p>
          </li>
        ) : null}
      </ol>

      {stalled ? (
        <p
          role="status"
          className="mt-3 text-[0.75rem] leading-5 text-gemini-muted dark:text-gemini-dark-muted"
        >
          กำลังค้นและอ่านเอกสารอยู่ อาจใช้เวลานานขึ้นหากคลังเอกสารใหญ่ —
          คำตอบจะปรากฏทันทีเมื่อพร้อม
        </p>
      ) : null}
    </section>
  ) : null;

  return (
    <div
      className={cn("w-full min-w-0 py-0.5", className)}
      data-testid="chat-thinking-status"
    >
      {mode === "completed" ? (
        <button
          type="button"
          aria-expanded={completedExpanded}
          aria-controls={panelId}
          onClick={() => setCompletedExpanded((value) => !value)}
          className={cn(
            "gemini-focus-ring -ml-1.5 inline-flex min-h-9 max-w-full items-center gap-1.5 rounded-md px-1.5",
            "chat-worked-toggle text-left text-[0.8125rem] font-normal gemini-theme-transition",
            "text-gemini-muted hover:bg-gemini-hover/40 hover:text-gemini-text",
            "dark:text-gemini-dark-muted dark:hover:bg-gemini-dark-hover/40 dark:hover:text-gemini-dark-text"
          )}
        >
          <Clock3 className="h-3.5 w-3.5 shrink-0" aria-hidden />
          <span className="min-w-0 break-words">
            Worked for {formatDuration(completedDuration, 1)}
          </span>
          <ChevronDown
            className={cn(
              "h-3.5 w-3.5 shrink-0 transition-transform duration-200 motion-reduce:transition-none",
              completedExpanded && "rotate-180"
            )}
            aria-hidden
          />
          <span className="sr-only">
            {completedExpanded
              ? " ซ่อนสรุปขั้นตอนการทำงาน"
              : " แสดงสรุปขั้นตอนการทำงาน"}
          </span>
        </button>
      ) : null}

      {mode === "live" ? (
        <div data-testid="chat-thinking" className="min-w-0">
          <div className="mb-2 flex items-center gap-2.5">
            <ClaudeStar className="text-[#d97757] motion-safe:animate-pulse motion-reduce:animate-none" />
            <p
              id={headingId}
              className="chat-activity-heading text-[0.8125rem] font-normal leading-6 text-gemini-muted dark:text-gemini-dark-muted"
            >
              {compact ? "กำลังตอบ" : "Thinking"}
              {elapsedMs > 0 ? (
                <span className="ml-1.5 tabular-nums opacity-70">
                  {formatDuration(elapsedMs)}
                </span>
              ) : null}
            </p>
          </div>
          {/* Keep stage markers queryable for e2e even in compact mode. */}
          {compact ? (
            <ol className="sr-only">
              {stages.map((stage) => (
                <li
                  key={stage}
                  data-stage={stage}
                  data-state={
                    stage === currentStage ? "current" : "complete"
                  }
                >
                  {stageLabel(stage)}
                </li>
              ))}
            </ol>
          ) : (
            timeline
          )}
        </div>
      ) : (
        timeline
      )}

      {mode === "live" && currentStage ? (
        <span
          className="sr-only"
          role="status"
          aria-live="polite"
          aria-atomic="true"
        >
          ขั้นตอนปัจจุบัน: {stageLabel(currentStage)}
        </span>
      ) : null}
    </div>
  );
}
