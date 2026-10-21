import { authHeaders, handleUnauthorized } from "@/lib/auth";
import { parseApiError } from "@/lib/errors";
import type { DocumentReleaseResponse, IndexedDocument, PaginatedResponse, PolicyFindingsResponse } from "./types";
import { http } from "./http";

export const documentsApi = {
  listDocuments: (params?: {
    factory_id?: string;
    machine_id?: string;
    document_type?: string;
    document_category?: string;
    status?: string;
    page?: number;
    page_size?: number;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.machine_id) qs.set("machine_id", params.machine_id);
    if (params?.document_type) qs.set("document_type", params.document_type);
    if (params?.document_category) qs.set("document_category", params.document_category);
    if (params?.status) qs.set("status", params.status);
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size) qs.set("page_size", String(params.page_size));
    if (params?.limit) qs.set("limit", String(params.limit));
    if (params?.offset) qs.set("offset", String(params.offset));
    const query = qs.toString();
    return http<PaginatedResponse<IndexedDocument>>(
      `/api/v1/documents${query ? `?${query}` : ""}`
    );
  },

  fetchAllDocuments: async (
    params: {
      factory_id?: string;
      machine_id?: string;
      document_type?: string;
      document_category?: string;
      status?: string;
    },
    opts?: { pageSize?: number; maxItems?: number }
  ): Promise<IndexedDocument[]> => {
    const pageSize = opts?.pageSize ?? 200;
    const maxItems = opts?.maxItems ?? 500;
    const all: IndexedDocument[] = [];
    let page = 1;
    while (all.length < maxItems) {
      const res = await documentsApi.listDocuments({ ...params, page, page_size: pageSize });
      all.push(...res.items);
      if (all.length >= res.total || res.items.length === 0) break;
      page += 1;
    }
    return all.slice(0, maxItems);
  },

  getDocument: (docId: string) => http<IndexedDocument>(`/api/v1/documents/${docId}`),

  getDocumentPolicyFindings: (docId: string) =>
    http<PolicyFindingsResponse>(`/api/v1/documents/${docId}/policy-findings`),

  releaseDocument: (docId: string) =>
    http<DocumentReleaseResponse>(`/api/v1/documents/${docId}/release`, { method: "POST" }),

  patchDocumentVisibility: (docId: string, visiblePositionIds: string[]) =>
    http<IndexedDocument>(`/api/v1/documents/${docId}/visibility`, {
      method: "PATCH",
      body: JSON.stringify({ visible_position_ids: visiblePositionIds }),
    }),

  deleteDocument: (docId: string) =>
    http<void>(`/api/v1/documents/${docId}`, { method: "DELETE" }),

  getDocumentFile: async (
    docId: string,
    disposition: "inline" | "download" = "inline",
    onProgress?: (ratio: number) => void
  ): Promise<Blob> => {
    const qs = new URLSearchParams({ disposition });
    const res = await fetch(`/api/v1/documents/${docId}/file?${qs}`, {
      headers: authHeaders(),
      credentials: "same-origin",
    });
    if (res.status === 401 && typeof window !== "undefined") {
      handleUnauthorized();
      throw new Error("401 unauthorized");
    }
    if (!res.ok) {
      const text = await res.text();
      throw new Error(parseApiError(new Error(`${res.status} ${text}`)));
    }

    if (!onProgress || !res.body) {
      return res.blob();
    }

    const total = Number(res.headers.get("content-length")) || 0;
    const reader = res.body.getReader();
    const chunks: Uint8Array[] = [];
    let loaded = 0;

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      chunks.push(value);
      loaded += value.length;
      if (total > 0) {
        onProgress(Math.min(loaded / total, 1));
      }
    }

    const mimeType = res.headers.get("content-type") || "application/pdf";
    return new Blob(chunks, { type: mimeType });
  }
};
