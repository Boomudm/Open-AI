"use client";

import { documentTypeLabel } from "@/lib/document-categories";
import type { IngestPreflightResponse } from "@/lib/api";
import { cn } from "@/lib/cn";
import { AlertTriangle, CheckCircle2, Loader2, ScanLine, Sparkles } from "lucide-react";

type IngestPreflightBannerProps = {
  result: IngestPreflightResponse | null;
  loading?: boolean;
  error?: string | null;
  suggestedType?: string | null;
  userOverrodeType?: boolean;
  className?: string;
};

export function IngestPreflightBanner({
  result,
  loading,
  error,
  suggestedType,
  userOverrodeType,
  className,
}: IngestPreflightBannerProps) {
  if (loading && !result) {
    return (
      <div
        className={cn(
          "flex items-center gap-2 rounded-lg border border-gemini-border/60 dark:border-gemini-dark-border/60",
          "bg-gemini-surface/40 dark:bg-gemini-dark-surface/40 px-3 py-2 text-xs text-gemini-muted",
          className
        )}
        role="status"
      >
        <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
        กำลังตรวจสอบไฟล์…
      </div>
    );
  }

  if (error) {
    return (
      <div
        className={cn(
          "rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-300",
          className
        )}
        role="alert"
      >
        ตรวจสอบไฟล์ไม่สำเร็จ: {error}
      </div>
    );
  }

  if (!result) return null;

  const resolvedType = result.document_type ?? suggestedType;
  const showSuggestion =
    resolvedType &&
    suggestedType &&
    resolvedType === suggestedType &&
    !userOverrodeType;

  const warnings = result.policy_hints.filter((h) => h.severity !== "low");
  const border = result.accepted
    ? "border-emerald-500/30 bg-emerald-500/10"
    : "border-red-500/30 bg-red-500/10";

  return (
    <div
      className={cn("rounded-lg border px-3 py-2.5 text-xs space-y-1.5", border, className)}
      role="status"
      data-testid="ingest-preflight-banner"
    >
      <div className="flex items-start gap-2">
        {result.accepted ? (
          <CheckCircle2 className="h-3.5 w-3.5 text-emerald-600 dark:text-emerald-400 shrink-0 mt-0.5" />
        ) : (
          <AlertTriangle className="h-3.5 w-3.5 text-red-500 shrink-0 mt-0.5" />
        )}
        <div className="min-w-0 space-y-1">
          {showSuggestion && (
            <p className="flex items-center gap-1.5 font-medium text-gemini-text dark:text-gemini-dark-text">
              <Sparkles className="h-3.5 w-3.5 text-gemini-blue dark:text-gemini-dark-blue shrink-0" />
              แนะนำประเภท: {documentTypeLabel(resolvedType!)}
            </p>
          )}
          {result.accepted ? (
            <p className="text-emerald-700 dark:text-emerald-400">
              ไฟล์พร้อมอัปโหลด
              {result.estimated_pages != null && (
                <span className="text-gemini-muted dark:text-gemini-dark-muted">
                  {" "}
                  · ~{result.estimated_pages} หน้า
                  {result.estimated_chunks != null && ` · ~${result.estimated_chunks} chunks`}
                </span>
              )}
            </p>
          ) : (
            <ul className="text-red-600 dark:text-red-400 space-y-0.5">
              {result.reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
          {result.ocr_required && (
            <p className="flex items-center gap-1 text-gemini-muted dark:text-gemini-dark-muted">
              <ScanLine className="h-3 w-3 shrink-0" />
              อาจต้องใช้ OCR (สแกน/ภาพ)
            </p>
          )}
          {warnings.length > 0 && (
            <ul className="text-amber-700 dark:text-amber-400 space-y-0.5">
              {warnings.slice(0, 3).map((h) => (
                <li key={h.rule_id}>{h.message}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
