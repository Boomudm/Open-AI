"use client";

import { cn } from "@/lib/cn";
import { Search, Wrench } from "lucide-react";

export type PipelineBadgeProps = {
  machineId: string | null;
};

export function PipelineBadge({ machineId }: PipelineBadgeProps) {
  const scoped = Boolean(machineId);

  return (
    <span
      className={cn(
        "inline-flex select-none items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium tracking-wide",
        "bg-gemini-hover/70 text-gemini-muted dark:bg-gemini-dark-hover/70 dark:text-gemini-dark-muted"
      )}
    >
      {scoped ? (
        <>
          <Wrench className="h-3 w-3" />
          เฉพาะ {machineId}
        </>
      ) : (
        <>
          <Search className="h-3 w-3" />
          อัตโนมัติ
        </>
      )}
    </span>
  );
}
