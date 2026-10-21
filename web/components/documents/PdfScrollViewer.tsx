"use client";

import { ensurePdfWorker } from "@/lib/pdf-worker";
import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/Tooltip";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Document, Page } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

ensurePdfWorker();

const BATCH = 2;

export type PdfScrollViewerProps = {
  fileUrl: string;
  initialPage?: number;
  /** Evidence snippet — matching text-layer items are wrapped in <mark>. */
  highlight?: string;
  title?: string | null;
  className?: string;
  onPageChange?: (page: number) => void;
  onError?: (message: string) => void;
};

export function PdfScrollViewer({
  fileUrl,
  initialPage = 1,
  highlight,
  title,
  className,
  onPageChange,
  onError,
}: PdfScrollViewerProps) {
  // PDF text layers are fragmented into many small items, so match short
  // word runs from the evidence snippet rather than the whole sentence.
  const highlightNeedles = useMemo(() => {
    const words = (highlight ?? "").trim().split(/\s+/).filter((w) => w.length >= 3);
    if (!words.length) return [] as string[];
    const needles = new Set<string>();
    for (let span = 4; span >= 2; span--) {
      for (let i = 0; i + span <= words.length && needles.size < 12; i++) {
        needles.add(words.slice(i, i + span).join(" ").toLowerCase());
      }
    }
    return [...needles].sort((a, b) => b.length - a.length);
  }, [highlight]);

  const highlightRenderer = useCallback(
    ({ str }: { str: string }) => {
      if (!highlightNeedles.length || !str) return str;
      const lower = str.toLowerCase();
      for (const needle of highlightNeedles) {
        const at = lower.indexOf(needle);
        if (at >= 0) {
          const esc = (s: string) =>
            s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
          return `${esc(str.slice(0, at))}<mark style="background:rgba(250,204,21,.55);color:inherit;border-radius:2px">${esc(
            str.slice(at, at + needle.length)
          )}</mark>${esc(str.slice(at + needle.length))}`;
        }
      }
      return str;
    },
    [highlightNeedles]
  );

  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [pageWidth, setPageWidth] = useState(0);
  const [numPages, setNumPages] = useState(0);
  const [visibleThrough, setVisibleThrough] = useState(BATCH);
  const [currentPage, setCurrentPage] = useState(Math.max(1, initialPage));
  const [loadError, setLoadError] = useState("");

  const scrollToPage = useCallback(
    (page: number, behavior: ScrollBehavior = "auto", attempts = 18) => {
      const run = (remaining: number) => {
        const target = scrollRef.current?.querySelector<HTMLElement>(`#pdf-page-${page}`);
        if (target) {
          target.scrollIntoView({ block: "start", behavior });
          return;
        }
        if (remaining > 0) {
          requestAnimationFrame(() => run(remaining - 1));
        }
      };

      requestAnimationFrame(() => run(attempts));
    },
    []
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const update = () => {
      const w = el.clientWidth;
      if (w > 0) setPageWidth(Math.floor(w));
    };

    update();
    const ro = new ResizeObserver(() => update());
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  useEffect(() => {
    setVisibleThrough(BATCH);
    setCurrentPage(Math.max(1, initialPage));
    setNumPages(0);
    setLoadError("");
  // Only reset when the file itself changes, not when initialPage updates from hover.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fileUrl]);

  useEffect(() => {
    if (numPages === 0) return;
    setVisibleThrough((v) => Math.max(v, Math.min(numPages, currentPage + 1)));
  }, [currentPage, numPages]);

  useEffect(() => {
    if (numPages === 0) return;
    const page = Math.min(Math.max(1, initialPage), numPages);
    setCurrentPage(page);
    setVisibleThrough((v) => Math.max(v, Math.min(numPages, page + BATCH)));
    scrollToPage(page);
  }, [fileUrl, initialPage, numPages, scrollToPage]);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el || numPages === 0) return;
    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 120;
    if (nearBottom && visibleThrough < numPages) {
      setVisibleThrough((v) => Math.min(v + BATCH, numPages));
    }
  }, [numPages, visibleThrough]);

  const handleLoadSuccess = useCallback(({ numPages: n }: { numPages: number }) => {
    setNumPages(n);
    const start = Math.min(Math.max(1, initialPage), n);
    setCurrentPage(start);
    setVisibleThrough(Math.min(n, start + BATCH));
  }, [initialPage]);

  const handleLoadError = useCallback(
    (err: Error) => {
      const msg = err.message || "ไม่สามารถแสดง PDF ได้";
      setLoadError(msg);
      onError?.(msg);
    },
    [onError]
  );

  const goToPage = useCallback(
    (next: number) => {
      if (numPages === 0) return;
      const p = Math.min(Math.max(1, next), numPages);
      setCurrentPage(p);
      onPageChange?.(p);
      setVisibleThrough((v) => Math.max(v, Math.min(numPages, p + 1)));
      scrollToPage(p, "smooth");
    },
    [numPages, onPageChange, scrollToPage]
  );

  if (loadError) {
    return (
      <p className="text-sm text-red-600 dark:text-red-400 text-center py-8 px-4" role="alert">
        {loadError}
      </p>
    );
  }

  const pagesToShow = numPages > 0 ? Math.min(visibleThrough, numPages) : 0;

  return (
    <div ref={containerRef} className={cn("flex-1 min-h-0 flex flex-col", className)}>
      {numPages > 0 && (
        <div className="shrink-0 flex items-center justify-center gap-2 py-2 px-2 flex-wrap">
          <Tooltip content="ไปหน้าก่อนหน้า">
            <button
              type="button"
              disabled={currentPage <= 1}
              onClick={() => goToPage(currentPage - 1)}
              className="h-8 w-8 flex items-center justify-center rounded-full hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover disabled:opacity-40"
              aria-label="หน้าก่อน"
            >
              <ChevronLeft className="h-4 w-4" />
            </button>
          </Tooltip>
          <label className="inline-flex items-center gap-1.5 text-xs text-gemini-muted dark:text-gemini-dark-muted">
            <span className="sr-only">เลือกหน้า</span>
            <select
              value={currentPage}
              onChange={(e) => goToPage(Number(e.target.value))}
              className={cn(
                "h-8 min-w-[5.5rem] rounded-lg border border-gemini-border dark:border-gemini-dark-border",
                "bg-gemini-bg dark:bg-gemini-dark-bg text-gemini-text dark:text-gemini-dark-text",
                "px-2 text-xs tabular-nums"
              )}
              aria-label="เลือกหน้าเอกสาร"
            >
              {Array.from({ length: numPages }, (_, i) => {
                const pageNumber = i + 1;
                return (
                  <option key={pageNumber} value={pageNumber}>
                    หน้า {pageNumber}
                  </option>
                );
              })}
            </select>
            <span className="tabular-nums">/ {numPages}</span>
          </label>
          <Tooltip content="ไปหน้าถัดไป">
            <button
              type="button"
              disabled={currentPage >= numPages}
              onClick={() => goToPage(currentPage + 1)}
              className="h-8 w-8 flex items-center justify-center rounded-full hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover disabled:opacity-40"
              aria-label="หน้าถัดไป"
            >
              <ChevronRight className="h-4 w-4" />
            </button>
          </Tooltip>
        </div>
      )}

      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden gemini-scrollbar"
      >
        <Document
          key={fileUrl}
          file={fileUrl}
          onLoadSuccess={handleLoadSuccess}
          onLoadError={handleLoadError}
          loading={
            <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted py-12 text-center">
              กำลังแสดง PDF…
            </p>
          }
          className="flex flex-col items-center gap-3 py-2 w-full"
        >
          {pagesToShow > 0 &&
            pageWidth > 0 &&
            Array.from({ length: pagesToShow }, (_, i) => {
              const pageNumber = i + 1;
              return (
                <div
                  key={pageNumber}
                  id={`pdf-page-${pageNumber}`}
                  className="w-full flex justify-center shadow-sm rounded-lg overflow-hidden bg-white"
                  onMouseEnter={() => {
                    setCurrentPage(pageNumber);
                    onPageChange?.(pageNumber);
                  }}
                >
                  <Page
                    pageNumber={pageNumber}
                    width={pageWidth}
                    renderTextLayer={pageNumber <= 3 || pageNumber === initialPage}
                    renderAnnotationLayer={pageNumber <= 3}
                    customTextRenderer={
                      pageNumber === initialPage ? highlightRenderer : undefined
                    }
                    loading={
                      <div
                        className="bg-gemini-hover/30 dark:bg-gemini-dark-hover/30 animate-pulse rounded-lg"
                        style={{ width: pageWidth, height: pageWidth * 1.294 }}
                      />
                    }
                  />
                </div>
              );
            })}
        </Document>
        {numPages > 0 && (
          <p className="text-center text-[11px] text-gemini-muted dark:text-gemini-dark-muted py-3">
            {title ? `${title} · ` : ""}
            {numPages} หน้า
            {visibleThrough < numPages && " · เลื่อนลงเพื่อโหลดเพิ่ม"}
          </p>
        )}
      </div>
    </div>
  );
}
