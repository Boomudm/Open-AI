import type { RCAResponse } from "./types";
import { http } from "./http";

export const rcaApi = {
  rcaAnalyze: (
    body: {
      machine_id: string;
      symptom: string;
    },
    options?: { signal?: AbortSignal }
  ) =>
    http<RCAResponse>("/api/v1/rca/analyze", {
      method: "POST",
      body: JSON.stringify(body),
      signal: options?.signal,
    })
};
