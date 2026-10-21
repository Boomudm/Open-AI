"use client";

import type { AiTrendPoint } from "@/lib/api";
import { cn } from "@/lib/cn";
import { useMemo } from "react";

type AiQuestionTrendChartProps = {
  data: AiTrendPoint[];
  loading?: boolean;
  onSelectTopic?: (topic: string) => void;
};

export function AiQuestionTrendChart({ data, loading, onSelectTopic }: AiQuestionTrendChartProps) {
  const { topics, buckets, matrix, max } = useMemo(() => {
    const topicSet = new Set<string>();
    const bucketSet = new Set<string>();
    for (const row of data) {
      topicSet.add(row.topic);
      bucketSet.add(row.bucket);
    }
    const topics = Array.from(topicSet).slice(0, 8);
    const buckets = Array.from(bucketSet).sort();
    const matrix = new Map<string, number>();
    let max = 0;
    for (const row of data) {
      if (!topics.includes(row.topic)) continue;
      const key = `${row.bucket}|${row.topic}`;
      matrix.set(key, row.count);
      max = Math.max(max, row.count);
    }
    return { topics, buckets, matrix, max: max || 1 };
  }, [data]);

  if (loading) {
    return <div className="h-48 rounded-2xl bg-gemini-surface/60 animate-pulse" />;
  }

  if (!data.length) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted py-8 text-center">
        ยังไม่มีคำถาม AI ในช่วงนี้ — ข้อมูลจะสะสมเมื่อช่างใช้แชท
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2">
        {topics.map((topic) => (
          <button
            key={topic}
            type="button"
            onClick={() => onSelectTopic?.(topic)}
            className="text-xs px-2 py-1 rounded-lg bg-gemini-active dark:bg-gemini-dark-active text-gemini-text dark:text-gemini-dark-text hover:opacity-80 gemini-focus-ring"
          >
            {topic}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <div className="min-w-[320px] space-y-1">
          {topics.map((topic) => (
            <div key={topic} className="flex items-center gap-2">
              <span className="w-24 shrink-0 text-[10px] text-gemini-muted dark:text-gemini-dark-muted truncate">
                {topic}
              </span>
              <div className="flex flex-1 gap-0.5 items-end h-6">
                {buckets.map((bucket) => {
                  const count = matrix.get(`${bucket}|${topic}`) ?? 0;
                  const h = Math.max(4, Math.round((count / max) * 24));
                  return (
                    <div
                      key={bucket}
                      title={`${bucket}: ${count}`}
                      className={cn(
                        "flex-1 rounded-sm bg-gemini-blue/70 dark:bg-gemini-dark-blue/70 min-w-[8px]"
                      )}
                      style={{ height: `${h}px` }}
                    />
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
