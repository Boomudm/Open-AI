"use client";

import type { FeedbackGaps } from "@/lib/api";
import { cn } from "@/lib/cn";

const ISSUE_LABELS: Record<string, string> = {
  incorrect: "ไม่ถูกต้อง",
  outdated: "ล้าสมัย",
  missing_step: "ขาดขั้นตอน",
  unclear: "ไม่ชัดเจน",
  other: "อื่นๆ",
  unknown: "ไม่ระบุ",
};

type FeedbackGapPanelProps = {
  data: FeedbackGaps | undefined;
  loading?: boolean;
};

export function FeedbackGapPanel({ data, loading }: FeedbackGapPanelProps) {
  if (loading) {
    return <div className="h-40 rounded-2xl bg-gemini-surface/60 animate-pulse" />;
  }

  const byType = data?.by_issue_type ?? [];
  const topDocs = data?.top_docs ?? [];
  const maxType = Math.max(...byType.map((x) => x.count), 1);

  if (!byType.length && !topDocs.length) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted py-6 text-center">
        ยังไม่มี feedback ในช่วงนี้
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="space-y-2">
        {byType.map((row) => (
          <div key={row.issue_type} className="space-y-1">
            <div className="flex justify-between text-xs">
              <span>{ISSUE_LABELS[row.issue_type] ?? row.issue_type}</span>
              <span className="text-gemini-muted">{row.count}</span>
            </div>
            <div className="h-1.5 rounded-full bg-gemini-border/30 overflow-hidden">
              <div
                className={cn("h-full rounded-full bg-violet-500/70")}
                style={{ width: `${(row.count / maxType) * 100}%` }}
              />
            </div>
          </div>
        ))}
      </div>
      {topDocs.length > 0 && (
        <div>
          <p className="text-[10px] uppercase tracking-wide text-gemini-muted mb-2">เอกสารที่ถูกรายงานบ่อย</p>
          <ul className="space-y-1 text-xs text-gemini-text dark:text-gemini-dark-text">
            {topDocs.slice(0, 5).map((d) => (
              <li key={`${d.doc_id}-${d.issue_type}`} className="line-clamp-1">
                {d.doc_id.slice(0, 8)}… · {ISSUE_LABELS[d.issue_type ?? "unknown"] ?? d.issue_type} ({d.count})
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
