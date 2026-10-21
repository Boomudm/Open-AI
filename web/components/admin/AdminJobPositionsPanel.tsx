"use client";

import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { QueryBoundary } from "@/components/ui/QueryBoundary";
import { api, type JobPositionAdmin } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

export function AdminJobPositionsPanel() {
  const qc = useQueryClient();
  const positionsQuery = useQuery({
    queryKey: queryKeys.adminJobPositions(),
    queryFn: () => api.adminListJobPositions(),
  });

  const [code, setCode] = useState("");
  const [nameTh, setNameTh] = useState("");
  const [confirmDeactivate, setConfirmDeactivate] = useState<JobPositionAdmin | null>(null);
  const [usageText, setUsageText] = useState("");

  const createPosition = useMutation({
    mutationFn: () =>
      api.adminCreateJobPosition({
        position_code: code,
        name_th: nameTh,
      }),
    onSuccess: () => {
      setCode("");
      setNameTh("");
      void qc.invalidateQueries({ queryKey: queryKeys.adminJobPositions() });
      void qc.invalidateQueries({ queryKey: queryKeys.jobPositions() });
    },
  });

  const deactivate = useMutation({
    mutationFn: (positionId: string) =>
      api.adminUpdateJobPosition(positionId, { is_active: false }),
    onSuccess: () => {
      setConfirmDeactivate(null);
      void qc.invalidateQueries({ queryKey: queryKeys.adminJobPositions() });
      void qc.invalidateQueries({ queryKey: queryKeys.jobPositions() });
    },
  });

  async function requestDeactivate(row: JobPositionAdmin) {
    const usage = await api.adminJobPositionUsage(row.position_id);
    setUsageText(
      `ตำแหน่งนี้ผูกอยู่กับเอกสาร ${usage.document_count} รายการ และผู้ใช้ ${usage.user_count} คน — การปิดใช้งานจะทำให้ผู้ใช้ในตำแหน่งนี้ไม่เห็นเอกสารที่จำกัดตำแหน่งเหล่านั้น`
    );
    setConfirmDeactivate(row);
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-gemini-border/70 p-4 space-y-3 max-w-lg">
        <h3 className="font-medium text-sm">เพิ่มตำแหน่งงาน</h3>
        <Input label="รหัส (slug)" value={code} onChange={(e) => setCode(e.target.value)} placeholder="qc" />
        <Input
          label="ชื่อตำแหน่ง (ไทย)"
          value={nameTh}
          onChange={(e) => setNameTh(e.target.value)}
          placeholder="เจ้าหน้าที่ควบคุมคุณภาพ (QC)"
        />
        <Button
          type="button"
          variant="primary"
          loading={createPosition.isPending}
          disabled={!code.trim() || !nameTh.trim()}
          onClick={() => createPosition.mutate()}
        >
          เพิ่มตำแหน่ง
        </Button>
      </div>

      <QueryBoundary
        query={positionsQuery}
        loadingMessage="กำลังโหลดตำแหน่งงาน…"
        errorTitle="โหลดรายการตำแหน่งงานไม่สำเร็จ"
        treatEmptyArrayAsEmpty
        emptyTitle="ยังไม่มีตำแหน่งงาน"
        emptyMessage="เพิ่มตำแหน่งแรกด้วยแบบฟอร์มด้านบน"
        className="py-8 border border-gemini-border/70 rounded-xl"
      >
        {(positions) => (
      <div className="overflow-x-auto rounded-xl border border-gemini-border/70">
        <table className="w-full text-sm">
          <thead className="bg-gemini-surface text-left">
            <tr>
              <th className="px-3 py-2">ชื่อ</th>
              <th className="px-3 py-2">รหัส</th>
              <th className="px-3 py-2">เอกสาร</th>
              <th className="px-3 py-2">ผู้ใช้</th>
              <th className="px-3 py-2">สถานะ</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody>
            {positions.map((row) => (
              <tr key={row.position_id} className="border-t border-gemini-border/50">
                <td className="px-3 py-2">{row.name_th}</td>
                <td className="px-3 py-2 font-mono text-xs">{row.position_code}</td>
                <td className="px-3 py-2">{row.document_count}</td>
                <td className="px-3 py-2">{row.user_count}</td>
                <td className="px-3 py-2">{row.is_active ? "ใช้งาน" : "ปิด"}</td>
                <td className="px-3 py-2 text-right">
                  {row.is_active && (
                    <Button type="button" variant="ghost" onClick={() => void requestDeactivate(row)}>
                      ปิดใช้งาน
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
        )}
      </QueryBoundary>

      {confirmDeactivate && (
        <div className="rounded-xl border border-amber-500/40 bg-amber-500/10 p-4 space-y-3 max-w-lg">
          <p className="text-sm">{usageText}</p>
          <p className="text-sm font-medium">ปิดใช้งาน &quot;{confirmDeactivate.name_th}&quot;?</p>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="primary"
              loading={deactivate.isPending}
              onClick={() => deactivate.mutate(confirmDeactivate.position_id)}
            >
              ยืนยันปิดใช้งาน
            </Button>
            <Button type="button" variant="ghost" onClick={() => setConfirmDeactivate(null)}>
              ยกเลิก
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
