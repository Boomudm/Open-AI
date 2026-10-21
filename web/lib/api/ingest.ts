import { authHeaders, handleUnauthorized } from "@/lib/auth";
import { parseApiError } from "@/lib/errors";
import type { IngestFileResponse, IngestPreflightResponse, JobErrorRow, JobRow } from "./types";
import { http } from "./http";

export const ingestApi = {
  documentTypes: () => http<string[]>("/api/v1/ingest/document-types"),

  jobs: (params?: { status?: string; factory_id?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.offset != null) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return http<JobRow[]>(`/api/v1/ingest/jobs${query ? `?${query}` : ""}`);
  },

  job: (jobId: string) => http<JobRow>(`/api/v1/ingest/jobs/${jobId}`),

  jobErrors: (jobId: string, params?: { limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit != null) qs.set("limit", String(params.limit));
    if (params?.offset != null) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return http<JobErrorRow[]>(
      `/api/v1/ingest/jobs/${jobId}/errors${query ? `?${query}` : ""}`
    );
  },

  retryJob: (jobId: string) => http<JobRow>(`/api/v1/ingest/jobs/${jobId}/retry`, { method: "POST" }),

  reingestDocument: (docId: string) =>
    http<{ job_id: string; doc_id: string; status: string }>(
      `/api/v1/ingest/documents/${docId}/reingest`,
      { method: "POST" }
    ),

  ingestPreflight: async (form: FormData): Promise<IngestPreflightResponse> => {
    const res = await fetch("/api/v1/ingest/preflight", {
      method: "POST",
      headers: authHeaders(),
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
    return res.json() as Promise<IngestPreflightResponse>;
  },

  ingestFile: async (form: FormData): Promise<IngestFileResponse> => {
    const res = await fetch("/api/v1/ingest/file", {
      method: "POST",
      headers: authHeaders(),
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
    return res.json() as Promise<IngestFileResponse>;
  }
};
