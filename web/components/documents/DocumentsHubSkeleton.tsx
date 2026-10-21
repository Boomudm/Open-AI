"use client";

import { cn } from "@/lib/cn";

export function CategoryCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "p-4 rounded-2xl border border-gemini-border/50 dark:border-gemini-dark-border/50 animate-pulse",
        className
      )}
    >
      <div className="flex gap-3">
        <div className="h-10 w-10 rounded-xl bg-gemini-hover dark:bg-gemini-dark-hover" />
        <div className="flex-1 space-y-2">
          <div className="h-4 w-24 rounded bg-gemini-hover dark:bg-gemini-dark-hover" />
          <div className="h-3 w-full rounded bg-gemini-hover/70 dark:bg-gemini-dark-hover/70" />
          <div className="h-3 w-16 rounded bg-gemini-hover/70 dark:bg-gemini-dark-hover/70" />
        </div>
      </div>
    </div>
  );
}

export function MachineCardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-gemini-border/50 dark:border-gemini-dark-border/50 overflow-hidden animate-pulse",
        className
      )}
    >
      <div className="aspect-[4/3] bg-gemini-hover dark:bg-gemini-dark-hover" />
      <div className="p-3 space-y-2">
        <div className="h-4 w-20 rounded bg-gemini-hover dark:bg-gemini-dark-hover" />
        <div className="h-3 w-32 rounded bg-gemini-hover/70 dark:bg-gemini-dark-hover/70" />
      </div>
    </div>
  );
}
