"use client";

import { DeleteDocumentButton } from "@/components/documents/DeleteDocumentButton";
import { ReingestDocumentButton } from "@/components/documents/ReingestDocumentButton";
import { ReleaseDocumentButton } from "@/components/documents/ReleaseDocumentButton";
import { FeedbackReportButton } from "@/components/feedback/FeedbackReportButton";
import { useCachedDocIds } from "@/hooks/useCachedDocIds";
import type { IndexedDocument } from "@/lib/api";
import { cn } from "@/lib/cn";
import { docDisplayLabel } from "@/lib/documents-library";
import { documentTypeLabel } from "@/lib/document-categories";
import { useUiStore } from "@/stores/uiStore";
import { FileText, HardDrive } from "lucide-react";

export type DocumentRowProps = {
  doc: IndexedDocument;
  onOpen: (doc: IndexedDocument) => void;
  className?: string;
};

// "blocked" is a harder stop than quarantine — the release endpoint rejects it
// (409), so only offer the release action for the two reviewable states.
const RELEASABLE_STATUSES = new Set(["quarantined", "pending_release"]);

function statusBadge(status: string): string | null {
  if (status === "completed") return null;
  if (status === "pending") return "รอประมวลผล";
  if (status === "partial") return "ประมวลผลบางส่วน";
  if (status === "error") return "ผิดพลาด";
  if (status === "quarantined" || status === "pending_release") return "รอตรวจสอบเนื้อหา";
  if (status === "blocked") return "ถูกระงับถาวร";
  if (status === "indexing") return "กำลังทำดัชนีใหม่";
  return status;
}

export function DocumentRow({ doc, onOpen, className }: DocumentRowProps) {
  const badge = statusBadge(doc.ingest_status);
  const ocrMin = doc.extra_metadata?.ocr_confidence_min;
  const lowOcr =
    typeof ocrMin === "number" ? ocrMin < 70 : typeof ocrMin === "string" && Number(ocrMin) < 70;
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const factoryId = doc.factory_id ?? selectedFactoryId;
  const cachedIds = useCachedDocIds();
  const isOfflineReady = cachedIds.has(doc.doc_id);

  return (
    <div
      className={cn(
        "flex items-center gap-2 w-full",
        className
      )}
    >
    <button
      type="button"
      onClick={() => onOpen(doc)}
      className={cn(
        "flex-1 min-w-0",
        "text-left w-full flex items-center gap-3 p-3 rounded-xl gemini-theme-transition",
        "border border-gemini-border/60 dark:border-gemini-dark-border/60",
        "bg-gemini-surface/50 dark:bg-gemini-dark-surface/50",
        "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
      )}
    >
      <FileText className="h-5 w-5 shrink-0 text-gemini-muted dark:text-gemini-dark-muted" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text truncate">
          {docDisplayLabel(doc)}
        </p>
        <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
          {documentTypeLabel(doc.document_type)}
          {doc.chunks_count > 0 && ` · ${doc.chunks_count} chunks`}
        </p>
      </div>
      {isOfflineReady && (
        <span
          className="shrink-0 inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-emerald-500/15 text-emerald-700 dark:text-emerald-400"
          title="พร้อมออฟไลน์"
        >
          <HardDrive className="h-3 w-3" />
        </span>
      )}
      {lowOcr && (
        <span
          className="shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-800 dark:text-amber-300"
          title="คุณภาพ OCR ต่ำ — พิจารณาอัปโหลดใหม่"
        >
          OCR ต่ำ
        </span>
      )}
      {badge && (
        <span
          className={cn(
            "shrink-0 text-[10px] px-2 py-0.5 rounded-full",
            doc.ingest_status === "blocked"
              ? "bg-red-500/15 text-red-700 dark:text-red-400"
              : "bg-amber-500/15 text-amber-700 dark:text-amber-400"
          )}
        >
          {badge}
        </span>
      )}
      {(doc.visible_position_ids?.length ?? 0) > 0 && (
        <span className="shrink-0 text-[10px] px-2 py-0.5 rounded-full bg-violet-500/15 text-violet-700 dark:text-violet-400">
          จำกัดตำแหน่ง
        </span>
      )}
      <span className="shrink-0 text-xs font-medium text-gemini-blue dark:text-gemini-dark-blue">
        เปิด
      </span>
    </button>
    <div className="flex shrink-0 items-center gap-1 relative z-10">
      {RELEASABLE_STATUSES.has(doc.ingest_status) && (
        <ReleaseDocumentButton docId={doc.doc_id} factoryId={factoryId} compact />
      )}
      <ReingestDocumentButton docId={doc.doc_id} factoryId={factoryId} compact />
      <DeleteDocumentButton docId={doc.doc_id} factoryId={factoryId} compact />
      {factoryId && (
        <FeedbackReportButton
          compact
          payload={{
            factoryId,
            sourceType: "document",
            docId: doc.doc_id,
            machineId: doc.machine_id,
            contextLabel: docDisplayLabel(doc),
            contextSnapshot: { doc_title: docDisplayLabel(doc), document_type: doc.document_type },
          }}
        />
      )}
    </div>
    </div>
  );
}
