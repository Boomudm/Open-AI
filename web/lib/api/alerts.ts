import type { AtRiskMachine, Incident, Paginated } from "./types";
import { http } from "./http";

export const alertsApi = {
  listAlerts: (params?: { page?: number; page_size?: number; factory_id?: string }) => {
    const qs = new URLSearchParams();
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    const query = qs.toString();
    return http<
      Paginated<{
        alert_id: string;
        type: string;
        machine_id: string | null;
        severity: string;
        message: string;
        emitted_at: string;
        acknowledged: boolean;
        metric?: string;
        value?: number;
        threshold?: number;
        risk_score?: number;
        reason?: string;
      }>
    >(`/api/v1/alerts${query ? `?${query}` : ""}`);
  },

  acknowledgeAlert: (alertId: string) =>
    http<{ alert_id: string; acknowledged: boolean }>("/api/v1/alerts/acknowledge", {
      method: "POST",
      body: JSON.stringify({ alert_id: alertId }),
    }),

  atRisk: (params?: { n?: number; factory_id?: string }) => {
    const n = params?.n ?? 20;
    const qs = new URLSearchParams({ n: String(n) });
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    return http<AtRiskMachine[]>(`/api/v1/predictive/at-risk?${qs}`);
  },

  incidents: (params?: {
    factory_id?: string;
    machine_id?: string;
    severity?: string;
    status?: string;
  }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.machine_id) qs.set("machine_id", params.machine_id);
    if (params?.severity) qs.set("severity", params.severity);
    if (params?.status) qs.set("status", params.status);
    const query = qs.toString();
    return http<Incident[]>(`/api/v1/specialized/incidents${query ? `?${query}` : ""}`);
  }
};
