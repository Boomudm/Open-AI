import { cn } from "@/lib/cn";
import type { HTMLAttributes } from "react";

export type BadgeVariant = "ok" | "warning" | "critical" | "info" | "neutral";

const variantClasses: Record<BadgeVariant, string> = {
  ok: "bg-spark-success-muted text-spark-success border-spark-success/30",
  warning: "bg-spark-warning-muted text-spark-warning border-spark-warning/30",
  critical: "bg-spark-critical-muted text-spark-critical border-spark-critical/30",
  info: "bg-spark-info-muted text-spark-info border-spark-info/30",
  neutral: "bg-spark-elevated text-spark-text-secondary border-spark-border",
};

export type BadgeProps = HTMLAttributes<HTMLSpanElement> & {
  variant?: BadgeVariant;
  dot?: boolean;
};

export function Badge({
  variant = "neutral",
  dot = false,
  className,
  children,
  ...props
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 font-mono text-xs font-medium",
        "px-1.5 py-0.5 border rounded-sm uppercase tracking-wide",
        variantClasses[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span
          className={cn(
            "h-1.5 w-1.5 rounded-none shrink-0",
            variant === "ok" && "bg-spark-success",
            variant === "warning" && "bg-spark-warning",
            variant === "critical" && "bg-spark-critical",
            variant === "info" && "bg-spark-info",
            variant === "neutral" && "bg-spark-text-secondary"
          )}
          aria-hidden
        />
      )}
      {children}
    </span>
  );
}

/** Map machine/alert status strings to badge variant */
export function statusToBadge(status: string): BadgeVariant {
  const s = status.toUpperCase();
  if (s === "OK" || s === "ACTIVE" || s === "RESOLVED") return "ok";
  if (s === "WARNING" || s === "WARN") return "warning";
  if (s === "CRITICAL" || s === "ERROR" || s === "FAILED") return "critical";
  if (s === "INFO") return "info";
  return "neutral";
}
