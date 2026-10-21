import type { HandoverResponse } from "./types";
import { http } from "./http";

export const handoverApi = {
  handoverSummary: (body: { factory_id?: string | null; hours_back?: number }) =>
    http<HandoverResponse>("/api/v1/handover/summary", {
      method: "POST",
      body: JSON.stringify(body),
    })
};
