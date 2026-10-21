"use client";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/Card";
import { ErrorState } from "@/components/ui/State";
import { api, type FactoryBenchmarkItem } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { STALE_STATIC } from "@/lib/query-config";
import { useQuery } from "@tanstack/react-query";

type Props = {
  days?: number;
};

export function FactoryBenchmarkPanel({ days = 7 }: Props) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: queryKeys.insightsFactoryBenchmark({ days }),
    queryFn: () => api.insightsFactoryBenchmark({ days }),
    staleTime: STALE_STATIC,
  });

  if (isLoading) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">เปรียบเทียบโรงงาน</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-gemini-muted">กำลังโหลด…</p>
        </CardContent>
      </Card>
    );
  }

  if (isError) {
    return (
      <ErrorState
        title="โหลด benchmark ไม่สำเร็จ"
        message="ต้องมีสิทธิ์ admin"
        onRetry={() => void refetch()}
      />
    );
  }

  const rows = data ?? [];

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">เปรียบเทียบโรงงาน ({days} วัน)</CardTitle>
        <p className="text-xs text-gemini-muted">Admin — คำถาม AI · ซ่อม · hotness score</p>
      </CardHeader>
      <CardContent className="overflow-x-auto">
        {rows.length === 0 ? (
          <p className="text-sm text-gemini-muted">ไม่มีข้อมูล</p>
        ) : (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-gemini-muted border-b border-gemini-border/50">
                <th className="py-2 pr-3">โรงงาน</th>
                <th className="py-2 pr-3">คำถาม AI</th>
                <th className="py-2 pr-3">งานซ่อม</th>
                <th className="py-2 pr-3">Downtime (h)</th>
                <th className="py-2">Hotness</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row: FactoryBenchmarkItem) => (
                <tr key={row.factory_id} className="border-b border-gemini-border/30">
                  <td className="py-2 pr-3 font-medium">{row.factory_id}</td>
                  <td className="py-2 pr-3">{row.question_count}</td>
                  <td className="py-2 pr-3">{row.repair_count}</td>
                  <td className="py-2 pr-3">{row.repair_downtime_hours.toFixed(1)}</td>
                  <td className="py-2">{row.hotness_score.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </CardContent>
    </Card>
  );
}
