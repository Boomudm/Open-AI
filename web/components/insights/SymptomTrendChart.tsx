"use client";

import type { SymptomTrend } from "@/lib/api";
import { cn } from "@/lib/cn";

type SymptomTrendChartProps = {
  data: SymptomTrend[];
  loading?: boolean;
};

export function SymptomTrendChart({ data, loading }: SymptomTrendChartProps) {
  if (loading) {
    return <div className="h-48 rounded-2xl bg-gemini-surface/60 animate-pulse" />;
  }

  if (!data.length) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted py-8 text-center">
        ไม่มีข้อมูลอาการซ่อมในช่วงเวลานี้
      </p>
    );
  }

  const max = Math.max(...data.map((d) => d.count), 1);

  return (
    <div className="space-y-2">
      {data.map((row) => (
        <div key={row.symptom} className="space-y-1">
          <div className="flex justify-between gap-2 text-xs">
            <span className="text-gemini-text dark:text-gemini-dark-text line-clamp-1 flex-1">
              {row.symptom}
            </span>
            <span className="text-gemini-muted dark:text-gemini-dark-muted shrink-0">
              {row.count} · {row.downtime_hours.toFixed(1)}h
            </span>
          </div>
          <div className="h-2 rounded-full bg-gemini-border/30 dark:bg-gemini-dark-border/30 overflow-hidden">
            <div
              className={cn("h-full rounded-full bg-amber-500/80")}
              style={{ width: `${(row.count / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
