"use client";

import { ClientPortal } from "@/components/ui/ClientPortal";
import { api, type FeedbackRow } from "@/lib/api";
import { cn } from "@/lib/cn";
import { formatSessionTime } from "@/lib/chat";
import { parseApiError } from "@/lib/errors";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import { X } from "lucide-react";
import { useCallback, useState } from "react";

const STATUS_OPTIONS = [
  { value: "open", label: "เปิด" },
  { value: "triaged", label: "รับเรื่องแล้ว" },
  { value: "resolved", label: "แก้แล้ว" },
  { value: "wont_fix", label: "ไม่แก้" },
];

type FeedbackDetailDrawerProps = {
  feedback: FeedbackRow;
  onClose: () => void;
  onPatched: () => void;
  onOpenDocument?: (docId: string, page?: number, title?: string | null) => void;
};

export function FeedbackDetailDrawer({
  feedback,
  onClose,
  onPatched,
  onOpenDocument,
}: FeedbackDetailDrawerProps) {
  const [status, setStatus] = useState(feedback.status);
  const [resolutionNote, setResolutionNote] = useState(feedback.resolution_note ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const ctx = feedback.context as Record<string, unknown> | null;

  const handleSave = useCallback(async () => {
    setSaving(true);
    setError("");
    try {
      await api.patchFeedback(feedback.feedback_id, {
        status: status !== feedback.status ? status : undefined,
        resolution_note: resolutionNote !== (feedback.resolution_note ?? "") ? resolutionNote : undefined,
      });
      onPatched();
      onClose();
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setSaving(false);
    }
  }, [feedback, status, resolutionNote, onClose, onPatched]);

  return (
    <ClientPortal>
      <button
        type="button"
        aria-label="Close detail"
        className="fixed inset-0 bg-black/30 dark:bg-black/50"
        style={{ zIndex: Z_OVERLAY_BACKDROP }}
        onClick={onClose}
      />
      <aside
        className={cn(
          "fixed top-0 right-0 bottom-0 w-full max-w-md flex flex-col",
          "bg-gemini-bg dark:bg-gemini-dark-bg",
          "border-l border-gemini-border dark:border-gemini-dark-border shadow-xl"
        )}
        style={{ zIndex: Z_OVERLAY_PANEL }}
        aria-label="Feedback detail"
      >
        <div className="shrink-0 flex items-center justify-between px-4 h-14 border-b border-gemini-border/60 dark:border-gemini-dark-border/60">
          <h2 className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text">
            รายละเอียดแจ้งกลับ
          </h2>
          <button
            type="button"
            onClick={onClose}
            className="h-9 w-9 flex items-center justify-center rounded-full hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
            aria-label="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4 gemini-scrollbar">
          <div>
            <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted">ความคิดเห็น</p>
            <p className="text-sm text-gemini-text dark:text-gemini-dark-text mt-1 whitespace-pre-wrap">
              {feedback.comment}
            </p>
          </div>

          {feedback.issue_type && (
            <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted">
              ประเภท: {feedback.issue_type}
            </p>
          )}

          <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted">
            ส่งเมื่อ {formatSessionTime(feedback.created_at)}
            {feedback.machine_id && ` · ${feedback.machine_id}`}
          </p>

          {feedback.attachments.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {feedback.attachments.map((a) => (
                <a
                  key={a.attachment_id}
                  href={a.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block h-24 w-24 rounded-lg overflow-hidden border border-gemini-border/60"
                >
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img src={a.url} alt="" className="h-full w-full object-cover" />
                </a>
              ))}
            </div>
          )}

          {typeof ctx?.answer_excerpt === "string" && ctx.answer_excerpt.length > 0 && (
            <div className="rounded-lg bg-gemini-surface dark:bg-gemini-dark-surface p-3 text-xs text-gemini-muted dark:text-gemini-dark-muted">
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text mb-1">
                คำตอบ AI
              </p>
              <p className="line-clamp-6">{ctx.answer_excerpt}</p>
            </div>
          )}

          {typeof ctx?.question === "string" && ctx.question.length > 0 && (
            <div className="rounded-lg bg-gemini-surface dark:bg-gemini-dark-surface p-3 text-xs">
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text mb-1">
                คำถาม
              </p>
              <p className="whitespace-pre-wrap text-gemini-muted dark:text-gemini-dark-muted">
                {ctx.question}
              </p>
            </div>
          )}

          {typeof ctx?.answer === "string" && ctx.answer.length > 0 && (
            <div className="rounded-lg bg-gemini-surface dark:bg-gemini-dark-surface p-3 text-xs">
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text mb-1">
                คำตอบเต็ม
              </p>
              <p className="whitespace-pre-wrap text-gemini-muted dark:text-gemini-dark-muted line-clamp-12">
                {ctx.answer}
              </p>
            </div>
          )}

          {Array.isArray(ctx?.sources) && ctx.sources.length > 0 && (
            <div className="text-xs text-gemini-muted dark:text-gemini-dark-muted">
              <p className="font-medium text-gemini-text dark:text-gemini-dark-text mb-1">
                แหล่งอ้างอิง ({ctx.sources.length})
              </p>
              <ul className="space-y-1">
                {(ctx.sources as Array<Record<string, unknown>>).slice(0, 5).map((s, i) => {
                  const docId = s.doc_id ? String(s.doc_id) : null;
                  const page =
                    s.page != null && s.page !== "" ? Number(s.page) : undefined;
                  const label = String(s.source_file ?? s.doc_id ?? `source ${i + 1}`);
                  if (docId && onOpenDocument) {
                    return (
                      <li key={i}>
                        <button
                          type="button"
                          onClick={() =>
                            onOpenDocument(
                              docId,
                              Number.isFinite(page) ? page : undefined,
                              label
                            )
                          }
                          className="text-left text-gemini-accent hover:underline line-clamp-2"
                        >
                          {label}
                          {Number.isFinite(page) ? ` (p.${page})` : ""}
                        </button>
                      </li>
                    );
                  }
                  return (
                    <li key={i} className="line-clamp-2">
                      {label}
                    </li>
                  );
                })}
              </ul>
            </div>
          )}

          {feedback.doc_id && onOpenDocument && (
            <button
              type="button"
              onClick={() => {
                onOpenDocument(
                  feedback.doc_id!,
                  feedback.page ?? undefined,
                  (ctx?.doc_title as string) ?? undefined
                );
              }}
              className="text-sm text-gemini-blue dark:text-gemini-dark-blue hover:underline"
            >
              เปิดเอกสาร
            </button>
          )}

          <div>
            <label className="block text-xs font-medium text-gemini-muted dark:text-gemini-dark-muted mb-1">
              สถานะ
            </label>
            <select
              value={status}
              onChange={(e) => setStatus(e.target.value)}
              className="w-full rounded-lg border border-gemini-border dark:border-gemini-dark-border bg-transparent px-3 py-2 text-sm"
            >
              {STATUS_OPTIONS.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs font-medium text-gemini-muted dark:text-gemini-dark-muted mb-1">
              บันทึกการแก้ไข
            </label>
            <textarea
              value={resolutionNote}
              onChange={(e) => setResolutionNote(e.target.value)}
              rows={3}
              placeholder="เช่น อัปเดต SOP rev.3 แล้ว — รอ re-ingest"
              className="w-full rounded-lg border border-gemini-border dark:border-gemini-dark-border bg-transparent px-3 py-2 text-sm"
            />
          </div>

          {error && (
            <p className="text-sm text-red-600 dark:text-red-400" role="alert">
              {error}
            </p>
          )}
        </div>

        <div className="shrink-0 p-4 border-t border-gemini-border/60 dark:border-gemini-dark-border/60 flex gap-2 justify-end">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 text-sm rounded-full border border-gemini-border dark:border-gemini-dark-border"
          >
            ปิด
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={saving}
            className="px-4 py-2 text-sm rounded-full bg-gemini-blue dark:bg-gemini-dark-blue text-white disabled:opacity-60"
          >
            {saving ? "กำลังบันทึก…" : "บันทึก"}
          </button>
        </div>
      </aside>
    </ClientPortal>
  );
}
