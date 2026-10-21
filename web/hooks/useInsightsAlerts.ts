"use client";

import { api } from "@/lib/api";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo } from "react";
import { queryKeys } from "@/lib/query-keys";

export const INSIGHTS_HOTNESS_THRESHOLD = 5.0;

export function useInsightsAlerts(factoryId: string | null) {
  const query = useQuery({
    queryKey: queryKeys.alerts({ factory_id: factoryId, type: "insights_hotness" }),
    queryFn: () =>
      api.listAlerts({
        factory_id: factoryId || undefined,
        page: 1,
        page_size: 100,
      }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  });

  const insightsAlerts = useMemo(
    () => (query.data?.items ?? []).filter((a) => a.type === "insights_hotness"),
    [query.data]
  );

  const unacknowledgedCount = useMemo(
    () => insightsAlerts.filter((a) => !a.acknowledged).length,
    [insightsAlerts]
  );

  return {
    ...query,
    insightsAlerts,
    unacknowledgedCount,
  };
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (alertId: string) => api.acknowledgeAlert(alertId),
    onMutate: async (alertId) => {
      await qc.cancelQueries({ queryKey: ["alerts"] });
      const snapshots: { key: readonly unknown[]; data: unknown }[] = [];
      for (const [key, data] of qc.getQueriesData({ queryKey: ["alerts"] })) {
        if (!data || typeof data !== "object" || !("items" in data)) continue;
        const page = data as { items: Array<{ alert_id: string; acknowledged: boolean }> };
        snapshots.push({ key, data });
        qc.setQueryData(key, {
          ...page,
          items: page.items.map((a) =>
            a.alert_id === alertId ? { ...a, acknowledged: true } : a
          ),
        });
      }
      return { snapshots };
    },
    onError: (_e, _id, context) => {
      context?.snapshots?.forEach(({ key, data }) => {
        qc.setQueryData(key, () => data);
      });
    },
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ["alerts"] });
    },
  });
}
