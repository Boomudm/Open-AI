"use client";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Tooltip } from "@/components/ui/Tooltip";
import { api } from "@/lib/api";
import { canWriteFactory } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { removeCachedDocument } from "@/lib/offline/document-cache";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2, Loader2 } from "lucide-react";
import { useState } from "react";

export type DeleteDocumentButtonProps = {
  docId: string;
  factoryId?: string | null;
  label?: string;
  compact?: boolean;
  className?: string;
  onDeleted?: () => void;
};

export function DeleteDocumentButton({
  docId,
  factoryId,
  label = "ลบ",
  compact = false,
  className,
  onDeleted,
}: DeleteDocumentButtonProps) {
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  if (!canWriteFactory(factoryId)) {
    return null;
  }

  async function doDelete() {
    setLoading(true);
    setError("");
    try {
      await api.deleteDocument(docId);
      await removeCachedDocument(docId);
      await queryClient.invalidateQueries({ queryKey: ["documents"] });
      await queryClient.invalidateQueries({ queryKey: ["ingestJobs"] });
      setConfirmOpen(false);
      onDeleted?.();
    } catch (err) {
      setError(parseApiError(err));
    } finally {
      setLoading(false);
    }
  }

  function handleClick(e: React.MouseEvent) {
    e.stopPropagation();
    if (loading) return;
    setConfirmOpen(true);
  }

  const hint = compact ? "ลบเอกสารถาวร" : label;

  return (
    <span className={cn("inline-flex flex-col items-end", className)}>
      <Tooltip content={hint} disabled={!compact}>
        <button
          type="button"
          onClick={handleClick}
          disabled={loading}
          aria-label={label}
        className={cn(
          "inline-flex items-center gap-1 gemini-theme-transition gemini-focus-ring relative",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          compact
            ? "h-8 w-8 justify-center rounded-full text-gemini-muted dark:text-gemini-dark-muted hover:bg-red-500/10 hover:text-red-600 dark:hover:text-red-400"
            : "text-xs px-2.5 py-1 rounded-full border border-gemini-border/70 dark:border-gemini-dark-border/70 text-gemini-muted dark:text-gemini-dark-muted hover:bg-red-500/10 hover:text-red-600 dark:hover:text-red-400",
          loading && compact && "text-transparent"
        )}
      >
        <Trash2 className={compact ? "h-4 w-4" : "h-3.5 w-3.5"} />
        {!compact && <span>{loading ? "กำลังลบ…" : label}</span>}
        {compact && loading && (
          <Loader2 className="h-4 w-4 animate-spin absolute inset-0 m-auto" aria-hidden />
        )}
      </button>
      </Tooltip>
      {error && (
        <span className="text-[10px] text-red-600 dark:text-red-400 mt-0.5 max-w-[8rem] text-right">
          {error}
        </span>
      )}
      <ConfirmDialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={() => void doDelete()}
        title="ลบเอกสารถาวร?"
        message="เอกสาร ไฟล์ต้นฉบับ และข้อมูลใน RAG จะถูกลบ — AI จะไม่สามารถอ้างอิงเอกสารนี้ในคำตอบได้อีก การกระทำนี้ย้อนกลับไม่ได้"
        confirmLabel="ลบถาวร"
        cancelLabel="ยกเลิก"
        destructive
        loading={loading}
      />
    </span>
  );
}
