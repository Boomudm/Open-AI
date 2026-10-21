"use client";

import type { QualityFailures } from "@/lib/api";
import { formatSessionTime } from "@/lib/chat";

type QualityFailuresPanelProps = {
  data: QualityFailures | undefined;
  loading?: boolean;
  onOpenDocument?: (docId: string, page?: number, title?: string | null) => void;
};

function sourceLabel(source: Record<string, unknown>, index: number): string {
  const name = source.source_file ?? source.title ?? source.doc_id;
  if (name) return String(name);
  return `แหล่ง ${index + 1}`;
}

export function QualityFailuresPanel({
  data,
  loading,
  onOpenDocument,
}: QualityFailuresPanelProps) {
  if (loading) {
    return <div className="h-40 rounded-2xl bg-gemini-surface/60 animate-pulse" />;
  }

  const items = data?.items ?? [];
  if (!items.length) {
    return (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted py-6 text-center">
        ไม่มีคำตอบที่ถูกรายงานว่าไม่ถูกต้องในช่วงนี้
      </p>
    );
  }

  return (
    <ul className="space-y-3">
      {items.slice(0, 8).map((row) => (
        <li
          key={`${row.factory_id}-${row.question.slice(0, 40)}`}
          className="rounded-xl border border-gemini-border/50 dark:border-gemini-dark-border/50 p-3"
        >
          <p className="text-sm text-gemini-text dark:text-gemini-dark-text line-clamp-2">
            {row.question}
          </p>
          <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-1">
            {row.factory_id} · รายงาน {row.feedback_count} ครั้ง
            {row.last_seen ? ` · ล่าสุด ${formatSessionTime(row.last_seen)}` : ""}
          </p>
          {Array.isArray(row.sources) && row.sources.length > 0 && (
            <ul className="mt-2 flex flex-wrap gap-1.5">
              {row.sources.slice(0, 3).map((source, i) => {
                const docId = source.doc_id ? String(source.doc_id) : null;
                const page =
                  source.page != null && source.page !== ""
                    ? Number(source.page)
                    : undefined;
                const label = sourceLabel(source, i);
                if (docId && onOpenDocument) {
                  return (
                    <li key={`${docId}-${i}`}>
                      <button
                        type="button"
                        onClick={() =>
                          onOpenDocument(
                            docId,
                            Number.isFinite(page) ? page : undefined,
                            label
                          )
                        }
                        className="text-[11px] px-2 py-0.5 rounded-full bg-gemini-surface dark:bg-gemini-dark-surface text-gemini-accent hover:underline"
                      >
                        {label}
                        {Number.isFinite(page) ? ` p.${page}` : ""}
                      </button>
                    </li>
                  );
                }
                return (
                  <li
                    key={`${label}-${i}`}
                    className="text-[11px] px-2 py-0.5 rounded-full bg-gemini-surface/60 dark:bg-gemini-dark-surface/60 text-gemini-muted dark:text-gemini-dark-muted"
                  >
                    {label}
                  </li>
                );
              })}
            </ul>
          )}
        </li>
      ))}
    </ul>
  );
}
