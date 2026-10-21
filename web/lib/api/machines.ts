import { authHeaders, handleUnauthorized } from "@/lib/auth";
import { parseApiError } from "@/lib/errors";
import type { Machine, MachinesQuery, MachineCreatePayload, MachinePatchPayload, Paginated } from "./types";
import { http } from "./http";

export const machinesApi = {
  machines: (params?: MachinesQuery) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.machine_type) qs.set("machine_type", params.machine_type);
    if (params?.q) qs.set("q", params.q);
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    if (params?.include_inactive) qs.set("include_inactive", "true");
    const query = qs.toString();
    return http<Paginated<Machine>>(
      `/api/v1/machines${query ? `?${query}` : ""}`
    );
  },

  createMachine: (body: MachineCreatePayload) =>
    http<Machine>("/api/v1/machines", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  updateMachine: (machineId: string, body: MachinePatchPayload) =>
    http<Machine>(`/api/v1/machines/${encodeURIComponent(machineId)}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),

  addMachineAlias: (machineId: string, alias: string) =>
    http<{ alias: string; machine_id: string }>(
      `/api/v1/machines/${encodeURIComponent(machineId)}/aliases`,
      {
        method: "POST",
        body: JSON.stringify({ alias, source: "manual" }),
      }
    ),

  getMachineImageBlob: async (machineId: string): Promise<Blob> => {
    const res = await fetch(`/api/v1/machines/${encodeURIComponent(machineId)}/image`, {
      headers: authHeaders(),
      credentials: "same-origin",
    });
    if (res.status === 404) {
      throw new Error("404 not found");
    }
    if (res.status === 401 && typeof window !== "undefined") {
      handleUnauthorized();
      throw new Error("401 unauthorized");
    }
    if (!res.ok) {
      const text = await res.text();
      throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
    }
    return res.blob();
  },

  uploadMachineImage: async (machineId: string, file: File): Promise<void> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`/api/v1/machines/${encodeURIComponent(machineId)}/image`, {
      method: "POST",
      headers: authHeaders(),
      credentials: "same-origin",
      body: form,
    });
    if (res.status === 401 && typeof window !== "undefined") {
      handleUnauthorized();
      throw new Error("401 unauthorized");
    }
    if (!res.ok) {
      const text = await res.text();
      throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
    }
  },

  deleteMachineImage: async (machineId: string): Promise<void> => {
    const res = await fetch(`/api/v1/machines/${encodeURIComponent(machineId)}/image`, {
      method: "DELETE",
      headers: authHeaders(),
      credentials: "same-origin",
    });
    if (res.status === 401 && typeof window !== "undefined") {
      handleUnauthorized();
      throw new Error("401 unauthorized");
    }
    if (!res.ok && res.status !== 204) {
      const text = await res.text();
      throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
    }
  }
};
