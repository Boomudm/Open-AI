import type { RepairRow } from "@/lib/api";

export type RepairSortKey =
  | "repair_date"
  | "machine_id"
  | "symptom"
  | "root_cause"
  | "downtime_hours"
  | "cost_thb"
  | "result";

export type AnalyticsFilters = {
  q: string;
  symptom: string;
  rootCause: string;
  machines: string[];
  severity: string[];
  dateFrom: string;
  dateTo: string;
  sortBy: RepairSortKey;
  sortDir: "asc" | "desc";
  page: number;
};

export type RepairSummary = {
  total: number;
  total_downtime_hours: number;
  total_cost_thb: number;
  avg_downtime_hours: number;
};

export const DEFAULT_ANALYTICS_FILTERS: AnalyticsFilters = {
  q: "",
  symptom: "",
  rootCause: "",
  machines: [],
  severity: [],
  dateFrom: "",
  dateTo: "",
  sortBy: "repair_date",
  sortDir: "desc",
  page: 1,
};

export function formatRepairDate(iso: string | null): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleDateString("th-TH", {
      day: "2-digit",
      month: "short",
      year: "2-digit",
    });
  } catch {
    return iso;
  }
}

export function formatRepairNum(n: number | null, digits = 1): string {
  if (n == null) return "—";
  return n.toLocaleString("th-TH", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function resultBadgeVariant(
  result: string | null
): "ok" | "warning" | "critical" | "neutral" {
  if (!result) return "neutral";
  const r = result.toLowerCase();
  if (r.includes("success") || r.includes("pass") || r.includes("ok")) return "ok";
  if (r.includes("fail") || r.includes("critical") || r.includes("error"))
    return "critical";
  if (r.includes("warn") || r.includes("partial")) return "warning";
  return "neutral";
}

export function buildRepairsQueryParams(filters: AnalyticsFilters) {
  return {
    q: filters.q || undefined,
    symptom: filters.symptom || undefined,
    root_cause: filters.rootCause || undefined,
    machine_ids:
      filters.machines.length > 0 ? filters.machines.join(",") : undefined,
    severity:
      filters.severity.length > 0 ? filters.severity.join(",") : undefined,
    date_from: filters.dateFrom
      ? new Date(filters.dateFrom).toISOString()
      : undefined,
    date_to: filters.dateTo
      ? new Date(`${filters.dateTo}T23:59:59`).toISOString()
      : undefined,
    sort_by: filters.sortBy,
    sort_dir: filters.sortDir,
    page: filters.page,
    page_size: 50,
  };
}

export const EXPORT_COLUMNS = [
  { key: "repair_date", label: "Date" },
  { key: "machine_id", label: "Machine" },
  { key: "factory_id", label: "Factory" },
  { key: "symptom", label: "Symptom" },
  { key: "root_cause", label: "Root cause" },
  { key: "solution", label: "Solution" },
  { key: "downtime_hours", label: "Downtime h" },
  { key: "cost_thb", label: "Cost THB" },
  { key: "result", label: "Result" },
] as const;

export function repairToExportRow(row: RepairRow): Record<string, unknown> {
  return {
    repair_date: row.repair_date ?? "",
    machine_id: row.machine_id,
    factory_id: row.factory_id,
    symptom: row.symptom ?? "",
    root_cause: row.root_cause ?? "",
    solution: row.solution ?? "",
    downtime_hours: row.downtime_hours ?? "",
    cost_thb: row.cost_thb ?? "",
    result: row.result ?? "",
  };
}
