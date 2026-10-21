"use client";

import { AdminFactorySettingsForm } from "@/components/admin/AdminFactorySettingsForm";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { QueryBoundary } from "@/components/ui/QueryBoundary";
import { api, type FactoryAdmin } from "@/lib/api";
import { isSuperAdminUser } from "@/lib/auth";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Fragment, useState } from "react";

function FactoriesTable({
  factories,
  settingsFactoryId,
  setSettingsFactoryId,
  canDelete,
  onDelete,
  deletingFactoryId,
}: {
  factories: FactoryAdmin[];
  settingsFactoryId: string | null;
  setSettingsFactoryId: (id: string | null) => void;
  canDelete: boolean;
  onDelete: (factoryId: string) => void;
  deletingFactoryId: string | null;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-gemini-border/70">
      <table className="w-full text-sm">
        <thead className="bg-gemini-surface text-left">
          <tr>
            <th className="px-3 py-2">รหัส</th>
            <th className="px-3 py-2">ชื่อ</th>
            <th className="px-3 py-2">ที่ตั้ง</th>
            <th className="px-3 py-2">สร้างเมื่อ</th>
            <th className="px-3 py-2">การตั้งค่า</th>
            {canDelete && <th className="px-3 py-2">ลบ</th>}
          </tr>
        </thead>
        <tbody>
          {factories.map((row) => (
            <Fragment key={row.factory_id}>
              <tr className="border-t border-gemini-border/50">
                <td className="px-3 py-2 font-mono text-xs">{row.factory_id}</td>
                <td className="px-3 py-2">{row.factory_name}</td>
                <td className="px-3 py-2 text-gemini-muted">{row.location ?? "—"}</td>
                <td className="px-3 py-2 text-gemini-muted tabular-nums">
                  {row.created_at
                    ? new Date(row.created_at).toLocaleDateString("th-TH")
                    : "—"}
                </td>
                <td className="px-3 py-2">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() =>
                      setSettingsFactoryId(
                        settingsFactoryId === row.factory_id ? null : row.factory_id,
                      )
                    }
                  >
                    {settingsFactoryId === row.factory_id ? "ซ่อน" : "ตั้งค่า"}
                  </Button>
                </td>
                {canDelete && (
                  <td className="px-3 py-2">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="text-red-600 dark:text-red-400"
                      loading={deletingFactoryId === row.factory_id}
                      disabled={deletingFactoryId != null}
                      onClick={() => {
                        if (
                          !window.confirm(
                            `ลบโรงงาน ${row.factory_id} (${row.factory_name})?\n\nต้องไม่มีเอกสาร เครื่องจักร feedback หรือ QA cache ค้างอยู่`,
                          )
                        ) {
                          return;
                        }
                        onDelete(row.factory_id);
                      }}
                    >
                      ลบ
                    </Button>
                  </td>
                )}
              </tr>
              {settingsFactoryId === row.factory_id && (
                <tr>
                  <td colSpan={canDelete ? 6 : 5}>
                    <AdminFactorySettingsForm
                      factoryId={row.factory_id}
                      onClose={() => setSettingsFactoryId(null)}
                    />
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function AdminFactoriesPanel() {
  const qc = useQueryClient();
  const factoriesQuery = useQuery({
    queryKey: queryKeys.adminFactories(),
    queryFn: () => api.adminListFactories(),
  });

  const [factoryId, setFactoryId] = useState("");
  const [factoryName, setFactoryName] = useState("");
  const [location, setLocation] = useState("");
  const [error, setError] = useState("");
  const [settingsFactoryId, setSettingsFactoryId] = useState<string | null>(null);
  const [deletingFactoryId, setDeletingFactoryId] = useState<string | null>(null);
  const canDeleteFactories = isSuperAdminUser();

  const createFactory = useMutation({
    mutationFn: () =>
      api.adminCreateFactory({
        factory_id: factoryId.trim(),
        factory_name: factoryName.trim(),
        location: location.trim() || undefined,
      }),
    onSuccess: () => {
      setFactoryId("");
      setFactoryName("");
      setLocation("");
      setError("");
      void qc.invalidateQueries({ queryKey: queryKeys.adminFactories() });
      void qc.invalidateQueries({ queryKey: queryKeys.adminUsers() });
      void qc.invalidateQueries({ queryKey: queryKeys.factories() });
    },
    onError: (err: Error) => {
      setError(parseApiError(err) || "ไม่สามารถเพิ่มโรงงานได้");
    },
  });

  const deleteFactory = useMutation({
    mutationFn: (factoryId: string) => api.adminDeleteFactory(factoryId),
    onMutate: (factoryId) => {
      setDeletingFactoryId(factoryId);
      setError("");
    },
    onSuccess: () => {
      setDeletingFactoryId(null);
      setSettingsFactoryId(null);
      void qc.invalidateQueries({ queryKey: queryKeys.adminFactories() });
      void qc.invalidateQueries({ queryKey: queryKeys.adminUsers() });
      void qc.invalidateQueries({ queryKey: queryKeys.factories() });
    },
    onError: (err: Error) => {
      setDeletingFactoryId(null);
      setError(parseApiError(err) || "ไม่สามารถลบโรงงานได้");
    },
  });

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-gemini-border/70 p-4 space-y-3 max-w-lg">
        <h3 className="font-medium text-sm">เพิ่มโรงงาน</h3>
        <Input
          label="รหัสโรงงาน"
          value={factoryId}
          onChange={(e) => setFactoryId(e.target.value.toUpperCase())}
          placeholder="F-03"
        />
        <Input
          label="ชื่อโรงงาน"
          value={factoryName}
          onChange={(e) => setFactoryName(e.target.value)}
          placeholder="โรงงานระยอง"
        />
        <Input
          label="ที่ตั้ง (ไม่บังคับ)"
          value={location}
          onChange={(e) => setLocation(e.target.value)}
          placeholder="ระยอง"
        />
        {error && (
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">
            {error}
          </p>
        )}
        <Button
          type="button"
          variant="primary"
          loading={createFactory.isPending}
          disabled={!factoryId.trim() || !factoryName.trim()}
          onClick={() => createFactory.mutate()}
        >
          เพิ่มโรงงาน
        </Button>
        <p className="text-xs text-gemini-muted">
          รหัสโรงงานใช้ตัวอักษร ตัวเลข ขีด และขีดล่าง (2–19 ตัว) — หลังเพิ่มแล้วสามารถกำหนดสิทธิผู้ใช้ในแท็บผู้ใช้ได้
        </p>
      </div>

      <QueryBoundary
        query={factoriesQuery}
        loadingMessage="กำลังโหลดโรงงาน…"
        errorTitle="โหลดรายการโรงงานไม่สำเร็จ"
        treatEmptyArrayAsEmpty
        emptyTitle="ยังไม่มีโรงงาน"
        emptyMessage="เพิ่มโรงงานแรกด้วยแบบฟอร์มด้านบน"
        className="py-8 border border-gemini-border/70 rounded-xl"
      >
        {(factories) => (
          <FactoriesTable
            factories={factories}
            settingsFactoryId={settingsFactoryId}
            setSettingsFactoryId={setSettingsFactoryId}
            canDelete={canDeleteFactories}
            onDelete={(factoryId) => deleteFactory.mutate(factoryId)}
            deletingFactoryId={deletingFactoryId}
          />
        )}
      </QueryBoundary>
    </div>
  );
}
