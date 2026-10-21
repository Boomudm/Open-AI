import type { AiDrilldownItem, AiTrendPoint, CorrelationHints, FactoryBenchmarkItem, FeedbackGaps, MachineHeatmapCell, PulseItem, QualityFailures, SymptomTrend } from "./types";
import { http } from "./http";

export const insightsApi = {
  insightsPulse: (params?: { factory_id?: string; days?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.days) qs.set("days", String(params.days));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return http<PulseItem[]>(`/api/v1/insights/problem-pulse${q ? `?${q}` : ""}`);
  },

  insightsAiTrends: (params?: { factory_id?: string; days?: number; bucket?: string }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.days) qs.set("days", String(params.days));
    if (params?.bucket) qs.set("bucket", params.bucket);
    const q = qs.toString();
    return http<AiTrendPoint[]>(`/api/v1/insights/ai-questions/trends${q ? `?${q}` : ""}`);
  },

  insightsAiDrilldown: (params: { topic: string; factory_id?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    qs.set("topic", params.topic);
    if (params.factory_id) qs.set("factory_id", params.factory_id);
    if (params.limit) qs.set("limit", String(params.limit));
    return http<AiDrilldownItem[]>(`/api/v1/insights/ai-questions/drilldown?${qs.toString()}`);
  },

  insightsSymptomTrends: (params?: { factory_id?: string; days?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.days) qs.set("days", String(params.days));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return http<SymptomTrend[]>(`/api/v1/insights/symptom-trends${q ? `?${q}` : ""}`);
  },

  insightsMachineHeatmap: (params?: { factory_id?: string; days?: number }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.days) qs.set("days", String(params.days));
    const q = qs.toString();
    return http<MachineHeatmapCell[]>(`/api/v1/insights/machine-heatmap${q ? `?${q}` : ""}`);
  },

  insightsFeedbackGaps: (params?: { factory_id?: string; days?: number; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.days) qs.set("days", String(params.days));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return http<FeedbackGaps>(`/api/v1/insights/feedback-gaps${q ? `?${q}` : ""}`);
  },

  insightsQualityFailures: (params?: {
    factory_id?: string;
    days?: number;
    limit?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    if (params?.days) qs.set("days", String(params.days));
    if (params?.limit) qs.set("limit", String(params.limit));
    const q = qs.toString();
    return http<QualityFailures>(`/api/v1/insights/quality-failures${q ? `?${q}` : ""}`);
  },

  insightsBucketMeta: (params?: { factory_id?: string }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    const q = qs.toString();
    return http<{ bucket_tz: string }>(`/api/v1/insights/bucket-meta${q ? `?${q}` : ""}`);
  },

  insightsFactoryBenchmark: (params?: { days?: number }) => {
    const qs = new URLSearchParams();
    if (params?.days) qs.set("days", String(params.days));
    const q = qs.toString();
    return http<FactoryBenchmarkItem[]>(`/api/v1/insights/factory-benchmark${q ? `?${q}` : ""}`);
  },

  insightsCorrelationHints: (params?: { factory_id?: string }) => {
    const qs = new URLSearchParams();
    if (params?.factory_id) qs.set("factory_id", params.factory_id);
    const q = qs.toString();
    return http<CorrelationHints>(`/api/v1/insights/correlation-hints${q ? `?${q}` : ""}`);
  },

  insightsDrilldownExportUrl: (params: { topic: string; factory_id?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    qs.set("topic", params.topic);
    if (params.factory_id) qs.set("factory_id", params.factory_id);
    if (params.limit) qs.set("limit", String(params.limit));
    return `/api/v1/insights/ai-questions/drilldown/export?${qs.toString()}`;
  }
};
