"use client";

import { useUiStore } from "@/stores/uiStore";
import { cn } from "@/lib/cn";

export function FactoryScopeBadge({ className }: { className?: string }) {
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);

  return (
    <span
      className={cn(
        "inline-flex items-center px-2 py-0.5 rounded-sm border font-mono text-[10px] uppercase tracking-wide tabular-nums",
        selectedFactoryId
          ? "bg-spark-accent-muted text-spark-accent border-spark-accent/40"
          : "bg-spark-elevated text-spark-text-secondary border-spark-border",
        className
      )}
    >
      {selectedFactoryId ? `Factory ${selectedFactoryId}` : "All factories"}
    </span>
  );
}
