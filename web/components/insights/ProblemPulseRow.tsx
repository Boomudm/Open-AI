"use client";

import type { PulseItem } from "@/lib/api";
import { INSIGHTS_HOTNESS_THRESHOLD } from "@/hooks/useInsightsAlerts";
import { cn } from "@/lib/cn";
import { Flame, TrendingUp } from "lucide-react";

const SOURCE_LABEL: Record<string, string> = {
  ai: "AI",
  repair: "ซ่อม",
  feedback: "Feedback",
  incident: "เหตุการณ์",
};

type ProblemPulseRowProps = {
  items: PulseItem[];
  loading?: boolean;
  onSelectTopic?: (topic: string) => void;
};

export function ProblemPulseRow({ items, loading, onSelectTopic }: ProblemPulseRowProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-24 rounded-2xl bg-gemini-surface/60 dark:bg-gemini-dark-surface/60 animate-pulse" />
        ))}
      </div>
    );
  }

  if (!items.length) {
    return (
      <div className="rounded-2xl border border-dashed border-gemini-border/50 px-4 py-6 text-center">
        <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted">
          ยังไม่มีสัญญาณปัญหาที่โดดเด่นในช่วงเวลานี้
        </p>
        <p className="text-xs text-gemini-muted/80 mt-2">
          เริ่มใช้แชท AI เพื่อสร้างข้อมูลแนวโน้ม — คำถามจากหน้างานจะปรากฏที่นี่
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
      {items.map((item) => {
        const isAi = item.source === "ai";
        const clickable = isAi && onSelectTopic;
        const hot = item.hotness_score >= INSIGHTS_HOTNESS_THRESHOLD;
        return (
          <button
            key={`${item.source}-${item.label}-${item.machine_id ?? ""}`}
            type="button"
            disabled={!clickable}
            onClick={() => clickable && onSelectTopic(item.label)}
            className={cn(
              "text-left p-4 rounded-2xl border gemini-theme-transition",
              "bg-gemini-surface dark:bg-gemini-dark-surface",
              "border-gemini-border/60 dark:border-gemini-dark-border/60",
              hot && "border-amber-500/50 ring-1 ring-amber-500/20",
              clickable && "hover:border-gemini-blue/40 cursor-pointer gemini-focus-ring"
            )}
          >
            <div className="flex items-start justify-between gap-2">
              <span className="text-[10px] uppercase tracking-wide text-gemini-muted dark:text-gemini-dark-muted">
                {SOURCE_LABEL[item.source] ?? item.source}
              </span>
              <span className="flex items-center gap-1 shrink-0">
                <span
                  className={cn(
                    "text-[10px] font-medium tabular-nums",
                    hot ? "text-amber-600 dark:text-amber-400" : "text-gemini-muted"
                  )}
                >
                  {item.hotness_score.toFixed(1)}
                </span>
                <Flame className={cn("h-3.5 w-3.5", hot ? "text-amber-500" : "text-gemini-muted")} />
              </span>
            </div>
            <p className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text mt-1 line-clamp-2">
              {item.label}
            </p>
            {item.machine_id && (
              <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-0.5">{item.machine_id}</p>
            )}
            <div className="flex items-center gap-1.5 mt-2 text-xs">
              <TrendingUp className="h-3 w-3 text-gemini-blue dark:text-gemini-dark-blue" />
              <span className="text-gemini-text dark:text-gemini-dark-text font-medium">
                {item.count_current} ครั้ง
              </span>
              {item.is_new_signal ? (
                <span className="text-amber-600 dark:text-amber-400 font-medium">ใหม่</span>
              ) : (
                <span
                  className={cn(
                    item.delta_pct >= 0 ? "text-amber-600 dark:text-amber-400" : "text-emerald-600"
                  )}
                >
                  {item.delta_pct >= 0 ? "↑" : "↓"} {Math.abs(item.delta_pct)}%
                </span>
              )}
            </div>
          </button>
        );
      })}
    </div>
  );
}
