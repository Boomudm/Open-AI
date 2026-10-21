import { cn } from "@/lib/cn";
import type { HTMLAttributes, ReactNode } from "react";
import {
  deltaBadgeClass,
  deltaTone,
  formatDeltaLabel,
  type KpiDelta,
  type KpiDeltaFormat,
  type KpiMetricKind,
} from "@/lib/kpiDelta";

export type CardProps = HTMLAttributes<HTMLDivElement> & {
  padding?: "none" | "sm" | "md" | "lg";
};

const paddingClasses = {
  none: "",
  sm: "p-3",
  md: "p-4",
  lg: "p-5",
};

export function Card({
  padding = "md",
  className,
  children,
  ...props
}: CardProps) {
  return (
    <div
      className={cn(
        "spark-glass backdrop-blur-xl",
        paddingClasses[padding],
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-3 pb-3 mb-3",
        "border-b border-spark-border",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export function CardTitle({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "font-mono text-sm font-semibold text-spark-text-primary tracking-tight",
        className
      )}
      {...props}
    >
      {children}
    </h3>
  );
}

export function CardDescription({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLParagraphElement>) {
  return (
    <p
      className={cn("text-xs text-spark-text-secondary font-sans", className)}
      {...props}
    >
      {children}
    </p>
  );
}

export function CardContent({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div className={cn("", className)} {...props}>
      {children}
    </div>
  );
}

export function CardFooter({
  className,
  children,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 pt-3 mt-3 border-t border-spark-border",
        className
      )}
      {...props}
    >
      {children}
    </div>
  );
}

export type StatCardProps = {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  accent?: "default" | "success" | "warning" | "critical" | "info";
  loading?: boolean;
  onClick?: () => void;
  delta?: KpiDelta;
  deltaMetric?: KpiMetricKind;
  deltaFormat?: KpiDeltaFormat;
};

/** Alias for StatCard — KPI summary card with optional month-over-month delta. */
export type KPICardProps = StatCardProps;
export const KPICard = StatCard;

const accentBorder: Record<NonNullable<StatCardProps["accent"]>, string> = {
  default: "border-spark-border",
  success: "border-l-[3px] border-l-spark-success bg-spark-success-muted/30",
  warning: "border-l-[3px] border-l-spark-warning bg-spark-warning-muted/30",
  critical: "border-l-[3px] border-l-spark-critical bg-spark-critical-muted/30",
  info: "border-l-[3px] border-l-spark-accent bg-spark-accent-muted/30",
};

export function StatCard({
  label,
  value,
  sub,
  accent = "default",
  loading = false,
  onClick,
  delta,
  deltaMetric,
  deltaFormat = "count",
}: StatCardProps) {
  const showDelta = Boolean(delta && deltaMetric && !loading);

  return (
    <Card
      className={cn(
        accentBorder[accent],
        loading && "animate-pulse-border",
        onClick &&
          "cursor-pointer hover:bg-spark-hover/50 transition-colors spark-focus-ring"
      )}
      role={loading ? "status" : onClick ? "button" : undefined}
      aria-busy={loading || undefined}
      tabIndex={onClick && !loading ? 0 : undefined}
      onClick={loading ? undefined : onClick}
      onKeyDown={
        onClick && !loading
          ? (e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      <p className="text-xs font-mono uppercase tracking-wider text-spark-text-secondary mb-1">
        {label}
      </p>
      {loading ? (
        <div className="h-7 w-16 bg-spark-elevated rounded-sm" />
      ) : (
        <p className="font-mono text-2xl font-semibold text-spark-text-primary tabular-nums">
          {value}
        </p>
      )}
      {showDelta && delta && deltaMetric && (
        <p
          className={cn(
            "font-mono text-[10px] mt-1 tabular-nums",
            deltaBadgeClass(deltaTone(delta, deltaMetric))
          )}
        >
          {formatDeltaLabel(delta, deltaFormat)}
        </p>
      )}
      {sub && !loading && (
        <p className="text-xs text-spark-text-secondary mt-1 font-sans">{sub}</p>
      )}
    </Card>
  );
}
