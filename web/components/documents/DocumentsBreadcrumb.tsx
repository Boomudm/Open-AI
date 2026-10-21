"use client";

import { cn } from "@/lib/cn";
import { ChevronLeft } from "lucide-react";

export type DocumentsBreadcrumbProps = {
  segments: string[];
  onBack?: () => void;
  className?: string;
};

export function DocumentsBreadcrumb({
  segments,
  onBack,
  className,
}: DocumentsBreadcrumbProps) {
  if (segments.length === 0) return null;

  return (
    <div className={cn("flex items-center gap-2 min-w-0", className)}>
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="shrink-0 inline-flex items-center gap-0.5 h-8 px-2 rounded-full hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover text-gemini-muted dark:text-gemini-dark-muted text-sm font-medium"
          aria-label="ย้อนกลับ"
        >
          <ChevronLeft className="h-4 w-4" />
          <span className="hidden sm:inline">กลับ</span>
        </button>
      )}
      <nav aria-label="Breadcrumb" className="min-w-0">
        <ol className="flex items-center gap-1 text-sm text-gemini-muted dark:text-gemini-dark-muted flex-wrap">
          {segments.map((seg, i) => (
            <li key={`${seg}-${i}`} className="flex items-center gap-1 min-w-0">
              {i > 0 && <span aria-hidden className="opacity-50">›</span>}
              <span
                className={cn(
                  "truncate",
                  i === segments.length - 1
                    ? "font-medium text-gemini-text dark:text-gemini-dark-text"
                    : ""
                )}
              >
                {seg}
              </span>
            </li>
          ))}
        </ol>
      </nav>
    </div>
  );
}
