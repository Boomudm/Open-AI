import { cn } from "@/lib/cn";

type SkeletonProps = {
  className?: string;
};

function Shimmer({ className }: SkeletonProps) {
  return (
    <div
      className={cn("skeleton-shimmer rounded-sm", className)}
      aria-hidden
    />
  );
}

export function SkeletonText({
  lines = 1,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={cn("space-y-2", className)} aria-hidden>
      {Array.from({ length: lines }).map((_, i) => (
        <Shimmer
          key={i}
          className={cn("h-3", i === lines - 1 && lines > 1 ? "w-3/4" : "w-full")}
        />
      ))}
    </div>
  );
}

export function SkeletonRow({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "flex items-center gap-3 px-3 py-2 border-b border-spark-border",
        className
      )}
      aria-hidden
    >
      <Shimmer className="h-4 w-4 shrink-0" />
      <Shimmer className="h-3 flex-1" />
      <Shimmer className="h-3 w-16" />
      <Shimmer className="h-3 w-20" />
    </div>
  );
}

export function SkeletonCard({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        "border border-spark-border rounded-sm bg-spark-surface p-3 space-y-3",
        className
      )}
      aria-hidden
    >
      <div className="flex items-center justify-between">
        <Shimmer className="h-4 w-24" />
        <Shimmer className="h-5 w-14" />
      </div>
      <Shimmer className="h-3 w-full" />
      <div className="flex gap-4">
        <Shimmer className="h-3 w-16" />
        <Shimmer className="h-3 w-20" />
      </div>
    </div>
  );
}

export function SkeletonTable({
  rows = 8,
  className,
}: {
  rows?: number;
  className?: string;
}) {
  return (
    <div
      className={cn("border border-spark-border rounded-sm overflow-hidden", className)}
      role="status"
      aria-label="Loading table"
    >
      <div className="flex items-center gap-3 px-3 py-2 border-b border-spark-border bg-spark-elevated">
        <Shimmer className="h-3 w-20" />
        <Shimmer className="h-3 flex-1" />
        <Shimmer className="h-3 w-24" />
        <Shimmer className="h-3 w-16" />
      </div>
      {Array.from({ length: rows }).map((_, i) => (
        <SkeletonRow key={i} />
      ))}
    </div>
  );
}

export function SkeletonGrid({
  count = 6,
  className,
}: {
  count?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3",
        className
      )}
      role="status"
      aria-label="Loading grid"
    >
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} />
      ))}
    </div>
  );
}
