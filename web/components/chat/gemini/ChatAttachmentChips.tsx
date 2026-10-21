"use client";

import { cn } from "@/lib/cn";
import type { ChatAttachmentMeta } from "@/lib/chat";
import { FileText, ImageIcon, X } from "lucide-react";

type Props = {
  attachments: ChatAttachmentMeta[];
  onRemove?: (index: number) => void;
  compact?: boolean;
};

export function ChatAttachmentChips({ attachments, onRemove, compact }: Props) {
  if (attachments.length === 0) return null;

  return (
    <div className={cn("flex flex-wrap gap-2", compact ? "mt-2" : "mb-2")}>
      {attachments.map((att, index) => {
        const isImage = att.mime_type.startsWith("image/");
        const href = att.url || att.previewUrl;
        const chip = (
          <span
            className={cn(
              "inline-flex items-center gap-1.5 max-w-full rounded-full text-xs gemini-theme-transition",
              "border border-gemini-border/70 dark:border-gemini-dark-border/70",
              "bg-gemini-surface dark:bg-gemini-dark-surface",
              "text-gemini-muted dark:text-gemini-dark-muted",
              compact ? "px-2 py-1" : "px-2.5 py-1.5"
            )}
          >
            {isImage ? (
              <ImageIcon className="h-3.5 w-3.5 shrink-0" aria-hidden />
            ) : (
              <FileText className="h-3.5 w-3.5 shrink-0" aria-hidden />
            )}
            <span className="truncate max-w-[12rem]">{att.filename}</span>
            {onRemove && (
              <button
                type="button"
                onClick={() => onRemove(index)}
                className="-mr-1 flex h-6 w-6 shrink-0 items-center justify-center rounded-full hover:bg-gemini-hover hover:text-gemini-text dark:hover:bg-gemini-dark-hover dark:hover:text-gemini-dark-text gemini-focus-ring"
                aria-label={`นำไฟล์ ${att.filename} ออก`}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            )}
          </span>
        );

        if (href && !onRemove) {
          return (
            <a
              key={`${att.filename}-${att.sort_order ?? index}`}
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="min-w-0 hover:opacity-90"
              aria-label={`${att.filename} (เปิดในแท็บใหม่)`}
            >
              {chip}
            </a>
          );
        }

        return (
          <div key={`${att.filename}-${att.sort_order ?? index}`} className="min-w-0">
            {chip}
          </div>
        );
      })}
    </div>
  );
}
