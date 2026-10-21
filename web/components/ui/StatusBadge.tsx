import { cn } from "@/lib/cn";
import type { HTMLAttributes } from "react";

export type MachineStatus = "OK" | "WARNING" | "CRITICAL" | "INFO";
export type StockStatus = "OK" | "LOW" | "DEAD";
export type StatusBadgeStatus = MachineStatus | StockStatus;

const statusConfig: Record<
  StatusBadgeStatus,
  { label: string; classes: string; dot: string; pulse?: boolean }
> = {
  OK: {
    label: "OK",
    classes: "bg-spark-success-muted text-spark-success border-spark-success/30",
    dot: "bg-spark-success",
  },
  LOW: {
    label: "LOW",
    classes: "bg-spark-warning-muted text-spark-warning border-spark-warning/30",
    dot: "bg-spark-warning",
    pulse: true,
  },
  DEAD: {
    label: "DEAD",
    classes: "bg-spark-elevated text-spark-text-muted border-spark-border",
    dot: "bg-spark-text-muted",
  },
  WARNING: {
    label: "WARNING",
    classes: "bg-spark-warning-muted text-spark-warning border-spark-warning/30",
    dot: "bg-spark-warning",
    pulse: true,
  },
  CRITICAL: {
    label: "CRITICAL",
    classes: "bg-spark-danger-muted text-spark-danger border-spark-danger/40",
    dot: "bg-spark-danger",
    pulse: true,
  },
  INFO: {
    label: "INFO",
    classes: "bg-spark-info-muted text-spark-info border-spark-info/30",
    dot: "bg-spark-info",
  },
};

export type StatusBadgeProps = HTMLAttributes<HTMLSpanElement> & {
  status: StatusBadgeStatus | string;
  showDot?: boolean;
  size?: "sm" | "md";
};

export function normalizeStatus(status: string): StatusBadgeStatus {
  const s = status.toUpperCase();
  if (s === "OK" || s === "ACTIVE" || s === "RESOLVED") return "OK";
  if (s === "LOW") return "LOW";
  if (s === "DEAD") return "DEAD";
  if (s === "WARNING" || s === "WARN") return "WARNING";
  if (s === "CRITICAL" || s === "ERROR" || s === "FAILED") return "CRITICAL";
  if (s === "INFO") return "INFO";
  return "INFO";
}

export function StatusBadge({
  status,
  showDot = true,
  size = "sm",
  className,
  ...props
}: StatusBadgeProps) {
  const normalized = normalizeStatus(status);
  const config = statusConfig[normalized];

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono font-medium border rounded-sm uppercase tracking-wide tabular-nums",
        size === "sm" ? "text-[10px] px-1.5 py-0.5" : "text-xs px-2 py-0.5",
        config.classes,
        className
      )}
      {...props}
    >
      {showDot && (
        <span
          className={cn(
            "h-1.5 w-1.5 shrink-0",
            config.dot,
            config.pulse && "animate-status-pulse"
          )}
          aria-hidden
        />
      )}
      {config.label}
    </span>
  );
}
