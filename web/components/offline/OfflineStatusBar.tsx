"use client";

import { useOfflineSync } from "@/hooks/useOfflineSync";
import { cn } from "@/lib/cn";
import { CloudOff, Loader2, Upload } from "lucide-react";

function formatMb(bytes: number): string {
  return (bytes / (1024 * 1024)).toFixed(1);
}

export function OfflineStatusBar() {
  const { status } = useOfflineSync();

  if (status.online && !status.syncing && status.pendingFeedback === 0) {
    return null;
  }

  return (
    <div
      className={cn(
        "shrink-0 flex items-center justify-center gap-2 px-3 py-1.5 text-xs",
        "border-b gemini-theme-transition",
        status.online
          ? "bg-gemini-blue/10 dark:bg-gemini-dark-blue/10 text-gemini-blue dark:text-gemini-dark-blue border-gemini-border/40"
          : "bg-amber-500/10 text-amber-800 dark:text-amber-300 border-amber-500/20"
      )}
      role="status"
    >
      {status.syncing ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin shrink-0" />
      ) : !status.online ? (
        <CloudOff className="h-3.5 w-3.5 shrink-0" />
      ) : (
        <Upload className="h-3.5 w-3.5 shrink-0" />
      )}
      <span>
        {!status.online
          ? `ออฟไลน์ — เอกสารที่บันทึกไว้ ${status.cachedDocsCount} ไฟล์ (${formatMb(status.cachedBytes)} MB)`
          : status.syncing
            ? "กำลังซิงค์…"
            : status.pendingFeedback > 0
              ? `รอส่ง feedback ${status.pendingFeedback} รายการ`
              : null}
      </span>
    </div>
  );
}
