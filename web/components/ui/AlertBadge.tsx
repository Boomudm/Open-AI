import { cn } from "@/lib/cn";

export type AlertBadgeProps = {
  count: number;
  className?: string;
  max?: number;
};

export function AlertBadge({ count, className, max = 99 }: AlertBadgeProps) {
  if (count <= 0) return null;

  const label = count > max ? `${max}+` : String(count);

  return (
    <span
      className={cn(
        "inline-flex items-center justify-center min-w-[1.125rem] h-[1.125rem] px-1",
        "font-mono text-[10px] font-semibold tabular-nums",
        "bg-spark-danger text-white border border-spark-danger rounded-sm",
        "animate-status-pulse",
        className
      )}
      aria-label={`${count} unacknowledged alerts`}
    >
      {label}
    </span>
  );
}
