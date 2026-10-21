"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/State";
import { useFactoryIdParam } from "@/hooks/useFactoryIdParam";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { STALE_STATIC } from "@/lib/query-config";
import { useQuery } from "@tanstack/react-query";

export function CorrelationHintsPanel() {
  const factoryId = useFactoryIdParam();
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.insightsCorrelationHints({ factory_id: factoryId }),
    queryFn: () => api.insightsCorrelationHints({ factory_id: factoryId }),
    staleTime: STALE_STATIC,
    enabled: Boolean(factoryId),
  });

  if (!factoryId) return null;

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Correlation hints</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gemini-muted">กำลังโหลด…</p>
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <ErrorState title="โหลด hints ไม่สำเร็จ" onRetry={() => void refetch()} />
    );
  }

  const items = data?.items ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Correlation hints</CardTitle>
        <p className="text-xs text-amber-700 dark:text-amber-400">{data?.disclaimer}</p>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.length === 0 ? (
          <p className="text-sm text-gemini-muted">ไม่พบ signal ที่น่าสนใจในช่วงนี้</p>
        ) : (
          items.map((hint) => (
            <div
              key={`${hint.machine_id}-${hint.topic}`}
              className="rounded-lg border border-gemini-border/50 p-3 text-sm"
            >
              <p className="font-medium">
                {hint.machine_id} · {hint.topic}
              </p>
              <p className="text-xs text-gemini-muted mt-1">
                spike {hint.spike_count} vs baseline {hint.baseline_count} · ซ่อมใกล้เคียง{" "}
                {hint.repair_count_nearby} · score {hint.correlation_score}
              </p>
            </div>
          ))
        )}
      </CardContent>
    </Card>
  );
}
