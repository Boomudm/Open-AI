"use client";

import { FeedbackDetailDrawer } from "@/components/feedback/FeedbackDetailDrawer";
import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/State";
import { api, type FeedbackRow } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatSessionTime } from "@/lib/chat";
import { parseApiError } from "@/lib/errors";
import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo, useState } from "react";

type StatusFilter = "open" | "all" | "resolved";

const STATUS_TABS: { id: StatusFilter; label: string; apiStatus?: string }[] = [
  { id: "open", label: "เปิด", apiStatus: "open" },
  { id: "all", label: "ทั้งหมด" },
  { id: "resolved", label: "แก้แล้ว", apiStatus: "resolved" },
];

const PAGE_SIZE = 50;

function sourceSummary(row: FeedbackRow): string {
  const ctx = row.context as Record<string, unknown> | null;
  if (row.machine_id) return row.machine_id;
  if (ctx?.doc_title && typeof ctx.doc_title === "string") return ctx.doc_title as string;
  if (row.doc_id) return `เอกสาร ${String(row.doc_id).slice(0, 8)}…`;
  return row.source_type;
}

export type FeedbackInboxPanelProps = {
  factoryId?: string | null;
  onOpenDocument?: (docId: string, page?: number, title?: string | null) => void;
};

export function FeedbackInboxPanel({ factoryId, onOpenDocument }: FeedbackInboxPanelProps) {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<StatusFilter>("open");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const apiStatus = STATUS_TABS.find((t) => t.id === filter)?.apiStatus;

  const {
    data,
    isLoading,
    error,
    refetch,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: ["feedback", factoryId, apiStatus],
    queryFn: ({ pageParam = 1 }) =>
      api.listFeedback({
        factory_id: factoryId || undefined,
        status: apiStatus,
        page: pageParam,
        page_size: PAGE_SIZE,
      }),
    initialPageParam: 1,
    getNextPageParam: (last) => {
      const loaded = last.page * last.page_size;
      return loaded < last.total ? last.page + 1 : undefined;
    },
    enabled: Boolean(factoryId),
    staleTime: 30_000,
  });

  const items = useMemo(() => data?.pages.flatMap((p) => p.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;

  const handlePatched = useCallback(() => {
    void refetch();
    qc.invalidateQueries({ queryKey: ["feedback-open-count"] });
  }, [qc, refetch]);

  const selected = items.find((r) => r.feedback_id === selectedId) ?? null;

  return (
    <div className="flex flex-col gap-4 max-w-2xl mx-auto w-full">
      <div className="flex flex-wrap gap-2">
        {STATUS_TABS.map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setFilter(tab.id)}
            className={cn(
              "px-3 py-1.5 rounded-full text-sm gemini-theme-transition",
              filter === tab.id
                ? "bg-gemini-blue dark:bg-gemini-dark-blue text-white"
                : "border border-gemini-border dark:border-gemini-dark-border text-gemini-muted dark:text-gemini-dark-muted hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
            )}
          >
            {tab.label}
            {tab.id === "open" && data && filter === "open" ? ` ${total}` : ""}
          </button>
        ))}
      </div>

      {!factoryId && (
        <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted text-center py-8">
          กำลังเลือกโรงงาน…
        </p>
      )}
      {factoryId && isLoading && (
        <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted text-center py-8">
          กำลังโหลด…
        </p>
      )}
      {factoryId && error && (
        <ErrorState
          title="โหลดรายการแจ้งกลับไม่สำเร็จ"
          message={parseApiError(error)}
          onRetry={() => void refetch()}
        />
      )}
      {factoryId && !isLoading && !error && items.length === 0 && (
        <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted text-center py-12">
          ไม่มีรายการแจ้งกลับ
        </p>
      )}

      {factoryId && !isLoading && !error && items.length > 0 && (
        <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted text-center">
          แสดง {items.length} จาก {total} รายการ
        </p>
      )}

      <ul className="space-y-2">
        {items.map((row) => (
          <li key={row.feedback_id}>
            <button
              type="button"
              onClick={() => setSelectedId(row.feedback_id)}
              className={cn(
                "w-full text-left p-4 rounded-xl gemini-theme-transition",
                "border border-gemini-border/60 dark:border-gemini-dark-border/60",
                "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
                row.status === "open" && "border-l-4 border-l-amber-500"
              )}
            >
              <div className="flex items-center gap-2 text-xs text-gemini-muted dark:text-gemini-dark-muted">
                <span
                  className={cn(
                    "inline-block h-2 w-2 rounded-full",
                    row.status === "open" ? "bg-amber-500" : "bg-emerald-500"
                  )}
                />
                <span className="font-medium text-gemini-text dark:text-gemini-dark-text">
                  {sourceSummary(row)}
                </span>
                {row.page != null && <span>· p.{row.page}</span>}
              </div>
              <p className="text-sm text-gemini-text dark:text-gemini-dark-text mt-1 line-clamp-2">
                &ldquo;{row.comment}&rdquo;
              </p>
              <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-2">
                {row.attachments.length > 0 && `${row.attachments.length} รูป · `}
                {formatSessionTime(row.created_at)}
              </p>
            </button>
          </li>
        ))}
      </ul>

      {hasNextPage && !error && (
        <div className="flex justify-center pt-2">
          <Button
            type="button"
            variant="secondary"
            loading={isFetchingNextPage}
            onClick={() => void fetchNextPage()}
          >
            โหลดเพิ่ม
          </Button>
        </div>
      )}

      {selected && (
        <FeedbackDetailDrawer
          feedback={selected}
          onClose={() => setSelectedId(null)}
          onPatched={handlePatched}
          onOpenDocument={onOpenDocument}
        />
      )}
    </div>
  );
}
