import { http } from "./http";
import type { SystemActionResult, SystemAdminDashboard } from "./types";

export const systemAdminApi = {
  getDashboard: () => http<SystemAdminDashboard>("/api/v1/system-admin/dashboard"),
  clearCache: () =>
    http<SystemActionResult>("/api/v1/system-admin/actions/clear-cache", { method: "POST" }),
  forceQdrantSync: () =>
    http<SystemActionResult>("/api/v1/system-admin/actions/qdrant-sync", { method: "POST" }),
  toggleMaintenance: (enabled: boolean, message?: string) =>
    http<SystemActionResult>("/api/v1/system-admin/actions/maintenance", {
      method: "POST",
      body: JSON.stringify({ enabled, message: message ?? "" }),
    }),
  resetAgenticCircuit: () =>
    http<SystemActionResult>("/api/v1/system-admin/actions/reset-agentic-circuit", {
      method: "POST",
    }),
  resetRagCircuit: () =>
    http<SystemActionResult>("/api/v1/system-admin/actions/reset-rag-circuit", {
      method: "POST",
    }),
};
