"use client";

import type { FeedbackReportPayload } from "@/components/feedback/FeedbackReportModal";
import { cn } from "@/lib/cn";
import { Tooltip } from "@/components/ui/Tooltip";
import { MessageSquareWarning } from "lucide-react";
import { useEffect, useState, type ComponentType } from "react";

type FeedbackReportButtonProps = {
  payload: FeedbackReportPayload;
  className?: string;
  compact?: boolean;
  label?: string;
};

export function FeedbackReportButton({
  payload,
  className,
  compact = false,
  label = "เสนอแนะการแก้ไข",
}: FeedbackReportButtonProps) {
  const [open, setOpen] = useState(false);
  const [FeedbackReportModal, setFeedbackReportModal] = useState<ComponentType<{
    open: boolean;
    onClose: () => void;
    payload: FeedbackReportPayload | null;
  }> | null>(null);

  const hint = "แจ้งกลับว่าเอกสารนี้ควรแก้อย่างไร";

  useEffect(() => {
    if (!open || FeedbackReportModal) return;
    let active = true;
    void import("@/components/feedback/FeedbackReportModal").then((m) => {
      if (active) setFeedbackReportModal(() => m.FeedbackReportModal);
    });
    return () => {
      active = false;
    };
  }, [FeedbackReportModal, open]);

  return (
    <>
      <Tooltip content={hint} disabled={!compact}>
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            setOpen(true);
          }}
          className={cn(
            "inline-flex items-center gap-1 gemini-theme-transition gemini-focus-ring",
            compact
              ? "text-[11px] text-gemini-muted dark:text-gemini-dark-muted hover:text-gemini-blue dark:hover:text-gemini-dark-blue"
              : "text-xs px-2.5 py-1 rounded-full border border-gemini-border/70 dark:border-gemini-dark-border/70 text-gemini-muted dark:text-gemini-dark-muted hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover hover:text-gemini-text dark:hover:text-gemini-dark-text",
            className
          )}
        >
          <MessageSquareWarning className={compact ? "h-3 w-3" : "h-3.5 w-3.5"} />
          {!compact && <span>{label}</span>}
        </button>
      </Tooltip>
      {open && FeedbackReportModal && (
        <FeedbackReportModal open={open} onClose={() => setOpen(false)} payload={payload} />
      )}
    </>
  );
}
