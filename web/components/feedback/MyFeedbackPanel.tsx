"use client";

import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/State";
import { api, type FeedbackRow } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatSessionTime } from "@/lib/chat";
import { parseApiError } from "@/lib/errors";
import { useInfiniteQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";

const PAGE_SIZE = 30;

const STATUS_LABELS: Record<string, string> = {
  open: "รอดำเนินการ",
  triaged: "รับเรื่องแล้ว",
  resolved: "แก้แล้ว",
  wont_fix: "ไม่แก้ไข",
};

type MyFeedbackPanelProps = {
  factoryId?: string | null;
};

export function MyFeedbackPanel({ factoryId }: MyFeedbackPanelProps) {
  const [filter, setFilter] = useState<"all" | "open" | "resolved">("all");

  const apiStatus = filter === "all" ? undefined : filter;

  const { data, isLoading, error, refetch, fetchNextPage, hasNextPage, isFetchingNextPage } =
    useInfiniteQuery({
      queryKey: ["myFeedback", factoryId, filter],
      queryFn: ({ pageParam = 1 }) =>
        api.listFeedback({
          mine: true,
          factory_id: factoryId ?? undefined,
          status: apiStatus,
          page: pageParam,
          page_size: PAGE_SIZE,
        }),
      initialPageParam: 1,
      getNextPageParam: (last) => {
        const loaded = last.page * last.page_size;
        return loaded < last.total ? last.page + 1 : undefined;
      },
    });

  const rows = useMemo(() => data?.pages.flatMap((p) => p.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;

  if (error) {
    return (
      <ErrorState
        message={parseApiError(error)}
        onRetry={() => void refetch()}
      />
    );
  }

  return (
    <div className="flex flex-col h-full min-h-0 p-4">
      <header className="mb-4 shrink-0">
        <h2 className="text-base font-semibold">รายการที่ฉันแจ้ง</h2>
        <p className="text-xs text-gemini-muted mt-1">
          ติดตามสถานะการแจ้งกลับความรู้ที่คุณส่งจากแชทหรือเอกสาร
        </p>
      </header>

      <div className="flex gap-2 mb-3 shrink-0">
        {(
          [
            { id: "all", label: "ทั้งหมด" },
            { id: "open", label: "รอดำเนินการ" },
            { id: "resolved", label: "แก้แล้ว" },
          ] as const
        ).map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setFilter(tab.id)}
            className={cn(
              "rounded-full px-3 py-1 text-xs border transition-colors",
              filter === tab.id
                ? "border-gemini-blue bg-gemini-blue/10 text-gemini-text"
                : "border-gemini-border text-gemini-muted hover:bg-gemini-hover"
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <p className="text-sm text-gemini-muted">กำลังโหลด…</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-gemini-muted py-8 text-center">
          ยังไม่มีรายการแจ้งกลับ — ใช้ปุ่ม &quot;เสนอแนะการแก้ไข&quot; ในแชทหรือเอกสาร
        </p>
      ) : (
        <>
          <p className="text-xs text-gemini-muted mb-2 shrink-0">
            แสดง {rows.length} จาก {total} รายการ
          </p>
          <ul className="flex-1 min-h-0 overflow-y-auto space-y-2">
            {rows.map((row) => (
              <MyFeedbackRow key={row.feedback_id} row={row} />
            ))}
          </ul>
          {hasNextPage && (
            <div className="pt-3 shrink-0">
              <Button
                type="button"
                variant="secondary"
                className="w-full"
                loading={isFetchingNextPage}
                onClick={() => void fetchNextPage()}
              >
                โหลดเพิ่ม
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function MyFeedbackRow({ row }: { row: FeedbackRow }) {
  const statusLabel = STATUS_LABELS[row.status] ?? row.status;
  const isOpen = row.status === "open" || row.status === "triaged";

  return (
    <li
      className={cn(
        "rounded-xl border px-3 py-2.5 text-sm",
        isOpen
          ? "border-amber-500/30 bg-amber-500/5"
          : "border-gemini-border/60 bg-gemini-surface/50"
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <span className="font-mono text-[10px] text-gemini-muted">{row.feedback_id.slice(0, 8)}…</span>
        <span className="text-xs text-gemini-muted shrink-0">{formatSessionTime(row.created_at)}</span>
      </div>
      <p className="mt-1 line-clamp-2">{row.comment}</p>
      <p className="text-xs text-gemini-muted mt-1">
        สถานะ: {statusLabel}
        {row.resolution_note ? ` — ${row.resolution_note}` : ""}
      </p>
    </li>
  );
}
