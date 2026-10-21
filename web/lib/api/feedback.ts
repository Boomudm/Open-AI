import { authHeaders, handleUnauthorized } from "@/lib/auth";
import { parseApiError } from "@/lib/errors";
import type { FeedbackRow, Paginated } from "./types";
import { http } from "./http";

export const feedbackApi = {
  submitFeedback: async (form: FormData): Promise<FeedbackRow> => {
    const res = await fetch("/api/v1/feedback", {
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
    return res.json() as Promise<FeedbackRow>;
  },

  listFeedback: (params?: {
    status?: string;
    factory_id?: string;
    doc_id?: string;
    machine_id?: string;
    mine?: boolean;
    page?: number;
    page_size?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.doc_id) qs.set("doc_id", params.doc_id);
    if (params?.machine_id) qs.set("machine_id", params.machine_id);
    if (params?.mine) qs.set("mine", "true");
    if (params?.page) qs.set("page", String(params.page));
    if (params?.page_size != null) qs.set("page_size", String(params.page_size));
    const query = qs.toString();
    return http<Paginated<FeedbackRow>>(`/api/v1/feedback${query ? `?${query}` : ""}`);
  },

  feedbackOpenCount: (params?: { factory_id?: string; status?: string }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set("status", params.status);
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    const query = qs.toString();
    return http<{ count: number }>(`/api/v1/feedback/count${query ? `?${query}` : ""}`);
  },

  patchFeedback: (feedbackId: string, body: { status?: string; resolution_note?: string }) =>
    http<FeedbackRow>(`/api/v1/feedback/${feedbackId}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    })
};
