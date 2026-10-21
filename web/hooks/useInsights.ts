"use client";

import { useFactoryIdParam } from "@/hooks/useFactoryIdParam";
import { api } from "@/lib/api";
import { STALE_STATIC } from "@/lib/query-config";
import { queryKeys } from "@/lib/query-keys";
import { keepPreviousData, useQuery } from "@tanstack/react-query";

export type InsightsPeriod = 7 | 30 | 90;

export function useInsightsPulse(days: InsightsPeriod = 7, enabled = true) {
  const factoryId = useFactoryIdParam();
  return useQuery({
    queryKey: queryKeys.insightsPulse({ factory_id: factoryId, days }),
    queryFn: () => api.insightsPulse({ factory_id: factoryId, days }),
    staleTime: STALE_STATIC,
    refetchInterval: 300_000,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useAiQuestionTrends(days: InsightsPeriod = 30, enabled = true) {
  const factoryId = useFactoryIdParam();
  return useQuery({
    queryKey: queryKeys.insightsAiTrends({ factory_id: factoryId, days }),
    queryFn: () => api.insightsAiTrends({ factory_id: factoryId, days, bucket: "week" }),
    staleTime: STALE_STATIC,
    refetchInterval: 300_000,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useSymptomTrends(days: InsightsPeriod = 90, enabled = true) {
  const factoryId = useFactoryIdParam();
  return useQuery({
    queryKey: queryKeys.insightsSymptoms({ factory_id: factoryId, days }),
    queryFn: () => api.insightsSymptomTrends({ factory_id: factoryId, days }),
    staleTime: STALE_STATIC,
    refetchInterval: 300_000,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useMachineHeatmap(days: InsightsPeriod = 30, enabled = true) {
  const factoryId = useFactoryIdParam();
  return useQuery({
    queryKey: queryKeys.insightsHeatmap({ factory_id: factoryId, days }),
    queryFn: () => api.insightsMachineHeatmap({ factory_id: factoryId, days }),
    staleTime: STALE_STATIC,
    refetchInterval: 300_000,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useFeedbackGaps(days: InsightsPeriod = 30, enabled = true) {
  const factoryId = useFactoryIdParam();
  return useQuery({
    queryKey: queryKeys.insightsFeedbackGaps({ factory_id: factoryId, days }),
    queryFn: () => api.insightsFeedbackGaps({ factory_id: factoryId, days }),
    staleTime: STALE_STATIC,
    refetchInterval: 300_000,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useQualityFailures(days: InsightsPeriod = 30, enabled = true) {
  const factoryId = useFactoryIdParam();
  return useQuery({
    queryKey: queryKeys.insightsQualityFailures({ factory_id: factoryId, days }),
    queryFn: () => api.insightsQualityFailures({ factory_id: factoryId, days, limit: 20 }),
    staleTime: STALE_STATIC,
    refetchInterval: 300_000,
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useAiDrilldown(topic: string | null, enabled: boolean) {
  const factoryId = useFactoryIdParam();
  return useQuery({
    queryKey: queryKeys.insightsDrilldown({ factory_id: factoryId, topic }),
    queryFn: () => api.insightsAiDrilldown({ topic: topic!, factory_id: factoryId, limit: 50 }),
    enabled: enabled && !!topic,
    staleTime: STALE_STATIC,
  });
}

export function useInsightsBucketMeta(enabled = true) {
  const factoryId = useFactoryIdParam();
  return useQuery({
    queryKey: queryKeys.insightsBucketMeta({ factory_id: factoryId }),
    queryFn: () => api.insightsBucketMeta({ factory_id: factoryId }),
    staleTime: STALE_STATIC,
    enabled: enabled && Boolean(factoryId),
  });
}
