"use client";

import { ClientPortal } from "@/components/ui/ClientPortal";
import { ErrorState } from "@/components/ui/State";
import type { AiDrilldownItem } from "@/lib/api";
import { api } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import { X } from "lucide-react";
import { useEffect, useId, useRef } from "react";

type QuestionDrilldownDrawerProps = {
  open: boolean;
  topic: string | null;
  factoryId?: string | null;
  items: AiDrilldownItem[];
  loading?: boolean;
  error?: boolean;
  onRetry?: () => void;
  onClose: () => void;
};

export function QuestionDrilldownDrawer({
  open,
  topic,
  factoryId,
  items,
  loading,
  error,
  onRetry,
  onClose,
}: QuestionDrilldownDrawerProps) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);
  const closeBtnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    closeBtnRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
        return;
      }
      if (e.key !== "Tab" || !panelRef.current) return;
      const focusable = panelRef.current.querySelectorAll<HTMLElement>(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!open || !topic) return null;

  return (
    <ClientPortal>
      <button
        type="button"
        className="fixed inset-0 bg-black/40"
        style={{ zIndex: Z_OVERLAY_BACKDROP }}
        aria-label="ปิด"
        onClick={onClose}
      />
      <aside
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          "fixed right-0 top-0 h-full w-full max-w-md",
          "bg-gemini-bg dark:bg-gemini-dark-bg border-l border-gemini-border/60",
          "shadow-xl flex flex-col gemini-theme-transition"
        )}
        style={{ zIndex: Z_OVERLAY_PANEL }}
      >
        <div className="flex items-center justify-between p-4 border-b border-gemini-border/40">
          <div>
            <h2
              id={titleId}
              className="text-sm font-semibold text-gemini-text dark:text-gemini-dark-text"
            >
              คำถามดิบ — {topic}
            </h2>
            <p className="text-xs text-gemini-muted mt-0.5">
              ไม่แสดงชื่อผู้ถาม · ใช้เพื่อ triage ปัญหาเท่านั้น · ห้ามแชร์นอกทีมบริหาร
            </p>
          </div>
          <button
            ref={closeBtnRef}
            type="button"
            onClick={onClose}
            className="touch-target p-2 rounded-lg gemini-focus-ring"
            aria-label="ปิด"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        {topic && (
          <div className="px-4 pb-2">
            <button
              type="button"
              className="text-xs text-gemini-blue dark:text-gemini-dark-blue hover:underline"
              onClick={async () => {
                const url = api.insightsDrilldownExportUrl({
                  topic,
                  factory_id: factoryId ?? undefined,
                });
                const res = await fetch(url, { credentials: "same-origin", headers: authHeaders() });
                if (!res.ok) return;
                const blob = await res.blob();
                const objectUrl = URL.createObjectURL(blob);
                const anchor = document.createElement("a");
                anchor.href = objectUrl;
                anchor.download = `drilldown-${topic.slice(0, 40)}.csv`;
                anchor.click();
                URL.revokeObjectURL(objectUrl);
              }}
            >
              Export CSV
            </button>
          </div>
        )}
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {error && (
            <ErrorState
              title="โหลดรายละเอียดไม่สำเร็จ"
              onRetry={onRetry}
              className="py-6 border-0 bg-transparent"
            />
          )}
          {!error && loading && <p className="text-sm text-gemini-muted">กำลังโหลด…</p>}
          {!error && !loading && !items.length && (
            <p className="text-sm text-gemini-muted">ไม่มีคำถามในหัวข้อนี้</p>
          )}
          {!error &&
            items.map((row) => (
              <div
                key={row.message_id}
                className="p-3 rounded-xl border border-gemini-border/50 bg-gemini-surface dark:bg-gemini-dark-surface"
              >
                <p className="text-sm text-gemini-text dark:text-gemini-dark-text">{row.question}</p>
                <p className="text-[11px] text-gemini-muted mt-2">
                  {row.machine_id ?? "—"} ·{" "}
                  {row.asked_at ? new Date(row.asked_at).toLocaleString("th-TH") : ""}
                </p>
              </div>
            ))}
        </div>
      </aside>
    </ClientPortal>
  );
}
