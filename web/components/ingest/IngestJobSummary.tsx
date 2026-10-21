"use client";

import { useIngestJobsList } from "@/hooks/useIngestJobs";
import { cn } from "@/lib/cn";
import { useMemo } from "react";

function statusBucket(status: string): "active" | "done" | "failed" | "other" {
  const s = status.toLowerCase();
  if (s === "queued" || s === "running" || s === "pending") return "active";
  if (s === "completed" || s === "done") return "done";
  if (s === "failed" || s === "error") return "failed";
  return "other";
}

export function IngestJobSummary({ className }: { className?: string }) {
  const { jobs, isLoading } = useIngestJobsList();

  const counts = useMemo(() => {
    let active = 0;
    let done = 0;
    let failed = 0;
    for (const j of jobs) {
      const b = statusBucket(j.status);
      if (b === "active") active += 1;
      else if (b === "done") done += 1;
      else if (b === "failed") failed += 1;
    }
    return { total: jobs.length, active, done, failed };
  }, [jobs]);

  const items = [
    { label: "Jobs", value: counts.total, accent: "text-spark-text-primary" },
    { label: "Active", value: counts.active, accent: "text-spark-warning" },
    { label: "Completed", value: counts.done, accent: "text-spark-success" },
    { label: "Failed", value: counts.failed, accent: "text-spark-critical" },
  ];

  return (
    <div
      className={cn(
        "grid grid-cols-2 sm:grid-cols-4 gap-2",
        className
      )}
    >
      {items.map((item) => (
        <div
          key={item.label}
          className="rounded-sm border border-spark-border bg-spark-surface/80 px-3 py-2"
        >
          <p className="font-mono text-[10px] uppercase tracking-wider text-spark-text-muted">
            {item.label}
          </p>
          <p
            className={cn(
              "font-mono text-lg font-semibold tabular-nums mt-0.5",
              item.accent,
              isLoading && "opacity-50"
            )}
          >
            {isLoading ? "—" : item.value}
          </p>
        </div>
      ))}
    </div>
  );
}
