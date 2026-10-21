import type { Paginated, RepairPatch, RepairRow, RepairsQuery } from "./types";
import { http } from "./http";

export const analyticsApi = {
  repairHistory: (params?: RepairsQuery) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.machine_id) qs.set("machine_id", params.machine_id);
    if (params?.machine_ids) qs.set("machine_ids", params.machine_ids);
    if (params?.q) qs.set("q", params.q);
    if (params?.symptom) qs.set("symptom", params.symptom);
    if (params?.root_cause) qs.set("root_cause", params.root_cause);
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.sort_by) qs.set("sort_by", params.sort_by);
    if (params?.sort_dir) qs.set("sort_dir", params.sort_dir);
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    const query = qs.toString();
    return http<Paginated<RepairRow>>(
      `/api/v1/analytics/repairs${query ? `?${query}` : ""}`
    );
  },

  repairMonthlyBuckets: (
    params?: Omit<RepairsQuery, "page" | "page_size" | "sort_by" | "sort_dir">
  ) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.machine_id) qs.set("machine_id", params.machine_id);
    if (params?.machine_ids) qs.set("machine_ids", params.machine_ids);
    if (params?.q) qs.set("q", params.q);
    if (params?.symptom) qs.set("symptom", params.symptom);
    if (params?.root_cause) qs.set("root_cause", params.root_cause);
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.severity) qs.set("severity", params.severity);
    const query = qs.toString();
    return http<
      {
        key: string;
        count: number;
        downtime_hours: number;
        cost_thb: number;
      }[]
    >(`/api/v1/analytics/repairs/monthly-buckets${query ? `?${query}` : ""}`);
  },

  repairSummary: (params?: Omit<RepairsQuery, "page" | "page_size" | "sort_by" | "sort_dir">) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.machine_id) qs.set("machine_id", params.machine_id);
    if (params?.machine_ids) qs.set("machine_ids", params.machine_ids);
    if (params?.q) qs.set("q", params.q);
    if (params?.symptom) qs.set("symptom", params.symptom);
    if (params?.root_cause) qs.set("root_cause", params.root_cause);
    if (params?.date_from) qs.set("date_from", params.date_from);
    if (params?.date_to) qs.set("date_to", params.date_to);
    if (params?.severity) qs.set("severity", params.severity);
    const query = qs.toString();
    return http<{
      total: number;
      total_downtime_hours: number;
      total_cost_thb: number;
      avg_downtime_hours: number;
    }>(`/api/v1/analytics/repairs/summary${query ? `?${query}` : ""}`);
  },

  updateRepair: (repairId: string, patch: RepairPatch) =>
    http<RepairRow>(`/api/v1/analytics/repairs/${repairId}`, {
      method: "PATCH",
      body: JSON.stringify(patch),
    })
};
