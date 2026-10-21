"use client";

import type { RetrievalReport } from "@/lib/api";
import { AlertTriangle } from "lucide-react";

type Props = {
  report: RetrievalReport;
};

export function DegradedRetrievalBanner({ report }: Props) {
  if (!report.degraded) return null;

  const reasons =
    report.degraded_reasons && report.degraded_reasons.length > 0
      ? report.degraded_reasons.join(", ")
      : "การค้นหาบางส่วนไม่สมบูรณ์";

  return (
    <div
      role="status"
      className="mb-2 flex items-start gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-900 dark:text-amber-100"
    >
      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden />
      <div>
        <p className="font-medium">การค้นหเอกสารลดคุณภาพชั่วคราว</p>
        <p className="mt-0.5 opacity-90">{reasons}</p>
      </div>
    </div>
  );
}
