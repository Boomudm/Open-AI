"use client";

import { DeleteDocumentButton } from "@/components/documents/DeleteDocumentButton";
import { DocumentVisibilityEditor } from "@/components/documents/DocumentVisibilityEditor";
import { FeedbackReportButton } from "@/components/feedback/FeedbackReportButton";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import {
  getCachedDocument,
  isCachedDocumentStale,
  putCachedDocument,
} from "@/lib/offline/document-cache";
import { isBrowserOnline } from "@/lib/offline/network";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import { Tooltip } from "@/components/ui/Tooltip";
import { useUiStore } from "@/stores/uiStore";
import { Download, WifiOff, X } from "lucide-react";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

const PdfScrollViewer = dynamic(
  () =>
    import("@/components/documents/PdfScrollViewer").then((m) => m.PdfScrollViewer),
  {
    ssr: false,
    loading: () => (
      <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted py-12 text-center">
        กำลังเตรียม PDF viewer…
      </p>
    ),
  }
);

export type DocumentViewerProps = {
  docId: string;
  title?: string | null;
  mimeType?: string | null;
  initialPage?: number;
  /** Evidence snippet to highlight inside the PDF text layer. */
  highlight?: string;
  factoryId?: string | null;
  machineId?: string | null;
  onClose: () => void;
};

function isSpreadsheetMime(mimeType: string | null | undefined): boolean {
  if (!mimeType) return false;
  return (
    mimeType === "application/vnd.ms-excel" ||
    mimeType === "text/csv" ||
    mimeType.includes("spreadsheet")
  );
}

function isSpreadsheetName(name: string | null | undefined): boolean {
  return /\.(xlsx|xls|csv)$/i.test(name ?? "");
}

function isPdfDocument(mimeType: string | null | undefined, name: string | null | undefined): boolean {
  if (isSpreadsheetMime(mimeType) || isSpreadsheetName(name)) return false;
  if (mimeType) return mimeType === "application/pdf" || mimeType.endsWith("/pdf");
  if (/\.(pdf)$/i.test(name ?? "")) return true;
  return true;
}

export function DocumentViewer({
  docId,
  title,
  mimeType,
  initialPage = 1,
  highlight,
  factoryId: factoryIdProp,
  machineId: machineIdProp,
  onClose,
}: DocumentViewerProps) {
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const [resolvedFactoryId, setResolvedFactoryId] = useState<string | null>(
    factoryIdProp ?? selectedFactoryId
  );
  const [resolvedMachineId, setResolvedMachineId] = useState<string | null>(
    machineIdProp ?? null
  );
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [pdfFallback, setPdfFallback] = useState(false);
  const [resolvedMime, setResolvedMime] = useState<string | null>(mimeType ?? null);
  const [offlineSource, setOfflineSource] = useState(false);
  const [staleCache, setStaleCache] = useState(false);
  const [docHash, setDocHash] = useState<string | null>(null);
  const [visiblePositionIds, setVisiblePositionIds] = useState<string[]>([]);
  const [loadProgress, setLoadProgress] = useState<number | null>(null);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));

  const docHashRef = useRef(docHash);
  const resolvedFactoryIdRef = useRef(resolvedFactoryId);
  const resolvedMachineIdRef = useRef(resolvedMachineId);
  const autoDownloadKeyRef = useRef<string | null>(null);
  useEffect(() => { docHashRef.current = docHash; }, [docHash]);
  useEffect(() => { resolvedFactoryIdRef.current = resolvedFactoryId; }, [resolvedFactoryId]);
  useEffect(() => { resolvedMachineIdRef.current = resolvedMachineId; }, [resolvedMachineId]);

  const isSpreadsheet = isSpreadsheetMime(resolvedMime) || isSpreadsheetName(title);
  const isPdf = isPdfDocument(resolvedMime, title);

  useEffect(() => {
    setCurrentPage(Math.max(1, initialPage));
  }, [docId, initialPage]);

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    const dismiss = () => onClose();
    window.addEventListener("spark:dismiss-overlays", dismiss);
    return () => window.removeEventListener("spark:dismiss-overlays", dismiss);
  }, [onClose]);

  useEffect(() => {
    if (factoryIdProp) {
      setResolvedFactoryId(factoryIdProp);
      setResolvedMachineId(machineIdProp ?? null);
      return;
    }
    api
      .getDocument(docId)
      .then((doc) => {
        setResolvedFactoryId(doc.factory_id ?? selectedFactoryId);
        setResolvedMachineId(doc.machine_id ?? machineIdProp ?? null);
        setDocHash(doc.file_hash_sha256 ?? null);
        setVisiblePositionIds(doc.visible_position_ids ?? []);
        void isCachedDocumentStale(docId, doc.file_hash_sha256).then(setStaleCache);
      })
      .catch(() => {
        setResolvedFactoryId(selectedFactoryId);
      });
  }, [docId, factoryIdProp, machineIdProp, selectedFactoryId]);

  useEffect(() => {
    let revoked: string | null = null;
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      setPdfFallback(false);
      setOfflineSource(false);
      setBlob(null);
      setBlobUrl(null);
      setLoadProgress(null);

      const applyBlob = (b: Blob, fromOffline: boolean) => {
        if (cancelled) return;
        const url = URL.createObjectURL(b);
        revoked = url;
        setBlob(b);
        setBlobUrl(url);
        setResolvedMime(b.type || mimeType || null);
        setOfflineSource(fromOffline);
      };

      if (isBrowserOnline()) {
        try {
          const b = await api.getDocumentFile(docId, "inline", (ratio) => {
            if (!cancelled) setLoadProgress(ratio);
          });
          applyBlob(b, false);
          void putCachedDocument({
            doc_id: docId,
            blob: b,
            mime_type: b.type || mimeType || "application/pdf",
            file_hash_sha256: docHashRef.current,
            factory_id: resolvedFactoryIdRef.current,
            machine_id: resolvedMachineIdRef.current,
          });
          setStaleCache(false);
          setLoadProgress(null);
          setLoading(false);
          return;
        } catch {
          /* fall through to cache */
        }
      }

      const cached = await getCachedDocument(docId);
      if (cached?.blob) {
        applyBlob(cached.blob, true);
        if (docHashRef.current && cached.file_hash_sha256 !== docHashRef.current) {
          setStaleCache(true);
        }
        setLoading(false);
        return;
      }

      if (!cancelled) {
        setError(
          isBrowserOnline()
            ? "โหลดเอกสารไม่สำเร็จ"
            : "ออฟไลน์ — ยังไม่มีไฟล์นี้ในเครื่อง เปิดครั้งแรกต้องมีเน็ต"
        );
        setLoading(false);
      }
    }

    void load();

    return () => {
      cancelled = true;
      if (revoked) URL.revokeObjectURL(revoked);
    };
  }, [docId, mimeType]);

  const handleDownload = useCallback(async () => {
    try {
      const file = blob ?? (await api.getDocumentFile(docId, "download"));
      const url = URL.createObjectURL(file);
      const a = document.createElement("a");
      a.href = url;
      a.download = title || `document-${docId}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(parseApiError(e));
    }
  }, [blob, docId, title]);

  useEffect(() => {
    if (loading || error || isPdf || !isSpreadsheet || !blob) return;
    const key = `${docId}:${blob.size}:${blob.type || resolvedMime || "unknown"}`;
    if (autoDownloadKeyRef.current === key) return;
    autoDownloadKeyRef.current = key;
    void handleDownload();
  }, [blob, docId, error, handleDownload, isPdf, isSpreadsheet, loading, resolvedMime]);

  const iframeSrc =
    blobUrl && isPdf
      ? initialPage > 1
        ? `${blobUrl}#page=${initialPage}&view=FitH`
        : `${blobUrl}#view=FitH`
      : blobUrl;

  const overlay = (
    <>
      <button
        type="button"
        aria-label="Close document viewer"
        className="fixed inset-0 bg-black/40 dark:bg-black/60 backdrop-blur-[1px] gemini-theme-transition"
        style={{ zIndex: Z_OVERLAY_BACKDROP }}
        onClick={onClose}
      />
      <div
        className={cn(
          "fixed flex flex-col gemini-theme-transition overflow-hidden",
          "inset-0 sm:inset-x-4 sm:top-[4dvh] sm:bottom-[4dvh] sm:max-w-5xl sm:mx-auto sm:rounded-2xl",
          "bg-gemini-bg dark:bg-gemini-dark-bg",
          "border-0 sm:border border-gemini-border dark:border-gemini-dark-border",
          "shadow-gemini-input-dark"
        )}
        style={{ zIndex: Z_OVERLAY_PANEL }}
        role="dialog"
        aria-label="Document viewer"
      >
        <div className="shrink-0 flex items-center justify-between gap-3 px-3 sm:px-4 pt-[env(safe-area-inset-top)] h-12 sm:h-14 border-b border-gemini-border/60 dark:border-gemini-dark-border/60">
          <div className="min-w-0 flex items-center gap-2">
            <p className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text truncate">
              {title || docId}
            </p>
            {offlineSource && (
              <span className="shrink-0 inline-flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 rounded-full bg-amber-500/15 text-amber-700 dark:text-amber-400">
                <WifiOff className="h-3 w-3" />
                ออฟไลน์
              </span>
            )}
            {staleCache && (
              <span className="shrink-0 text-[10px] px-1.5 py-0.5 rounded-full bg-gemini-hover text-gemini-muted">
                เวอร์ชันเก่า
              </span>
            )}
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <DeleteDocumentButton
              docId={docId}
              factoryId={resolvedFactoryId}
              compact
              onDeleted={onClose}
            />
            {resolvedFactoryId && (
              <FeedbackReportButton
                compact
                payload={{
                  factoryId: resolvedFactoryId,
                  sourceType: "document",
                  docId,
                  page: currentPage > 1 ? currentPage : null,
                  machineId: resolvedMachineId,
                  contextLabel: `${title || docId}${currentPage > 1 ? ` · หน้า ${currentPage}` : ""}`,
                  contextSnapshot: {
                    doc_title: title,
                    page: currentPage,
                    submitted_from: "document_viewer",
                  },
                }}
              />
            )}
            <Tooltip content="ดาวน์โหลดไฟล์ต้นฉบับ">
              <button
                type="button"
                onClick={handleDownload}
                className="h-8 w-8 flex items-center justify-center rounded-full hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover text-gemini-muted dark:text-gemini-dark-muted"
                aria-label="ดาวน์โหลด"
              >
                <Download className="h-4 w-4" />
              </button>
            </Tooltip>
            <Tooltip content="ปิดหน้าต่างเอกสาร">
              <button
                type="button"
                onClick={onClose}
                className="h-8 w-8 flex items-center justify-center rounded-full hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover text-gemini-muted dark:text-gemini-dark-muted"
                aria-label="ปิด"
              >
                <X className="h-4 w-4" />
              </button>
            </Tooltip>
          </div>
        </div>

        {!loading && !error && (
          <DocumentVisibilityEditor
            docId={docId}
            factoryId={resolvedFactoryId}
            initialPositionIds={visiblePositionIds}
            className="mx-3 sm:mx-4 mt-2 shrink-0"
          />
        )}

        <div className="flex-1 min-h-0 flex flex-col px-2 sm:px-3 pb-[max(0.5rem,env(safe-area-inset-bottom))] relative">
          {loading && (
            <div className="absolute inset-0 z-10 flex flex-col items-center justify-center gap-3 px-6 bg-gemini-bg dark:bg-gemini-dark-bg">
              <p className="text-base md:text-sm font-medium text-gemini-text dark:text-gemini-dark-text text-center">
                {loadProgress != null && loadProgress > 0
                  ? `กำลังโหลดเอกสาร… ${Math.round(loadProgress * 100)}%`
                  : "กำลังโหลดเอกสาร…"}
              </p>
              {loadProgress != null && loadProgress > 0 && (
                <div
                  className="h-2 md:h-1.5 w-full max-w-sm md:max-w-xs rounded-full bg-gemini-border/60 dark:bg-gemini-dark-border/60 overflow-hidden"
                  role="progressbar"
                  aria-valuenow={Math.round(loadProgress * 100)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                >
                  <div
                    className="h-full bg-gemini-blue dark:bg-gemini-dark-blue transition-[width] duration-150"
                    style={{ width: `${Math.round(loadProgress * 100)}%` }}
                  />
                </div>
              )}
            </div>
          )}
          {error && (
            <div className="flex flex-col items-center justify-center py-12 text-center gap-3 px-4">
              <p className="text-sm text-red-600 dark:text-red-400" role="alert">
                {error}
              </p>
            </div>
          )}
          {!loading && !error && isPdf && blobUrl && !pdfFallback && (
            <PdfScrollViewer
              key={blobUrl}
              fileUrl={blobUrl}
              initialPage={initialPage}
              highlight={highlight}
              title={title}
              onPageChange={setCurrentPage}
              onError={() => setPdfFallback(true)}
            />
          )}
          {!loading && !error && isPdf && blobUrl && pdfFallback && iframeSrc && (
            <iframe
              src={iframeSrc}
              title={title || "Document"}
              className="flex-1 w-full min-h-0 rounded-lg border border-gemini-border/50 bg-gemini-surface"
            />
          )}
          {!loading && !error && !isPdf && blobUrl && (
            <div className="flex flex-col items-center justify-center flex-1 text-center gap-4">
              <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
                {isSpreadsheet
                  ? "ไฟล์ Excel ถูกเปิดด้วยการดาวน์โหลดไฟล์ต้นฉบับ"
                  : "ไม่สามารถแสดงตัวอย่างไฟล์ประเภทนี้ในเบราว์เซอร์ได้"}
              </p>
              <button
                type="button"
                onClick={handleDownload}
                className="px-4 py-2 rounded-full text-sm bg-gemini-blue dark:bg-gemini-dark-blue text-white"
              >
                {isSpreadsheet ? "ดาวน์โหลดอีกครั้ง" : "ดาวน์โหลดไฟล์"}
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  );

  if (typeof document === "undefined") return overlay;
  return createPortal(overlay, document.body);
}
