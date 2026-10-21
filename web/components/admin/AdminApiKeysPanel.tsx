"use client";

import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { QueryBoundary } from "@/components/ui/QueryBoundary";
import { api, type ApiKeyOut } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

function formatWhen(iso?: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("th-TH", {
    day: "numeric",
    month: "short",
    year: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function keyStatus(row: ApiKeyOut): { label: string; variant: "ok" | "critical" | "warning" } {
  if (!row.is_active) return { label: "เพิกถอนแล้ว", variant: "critical" };
  if (row.expires_at && new Date(row.expires_at) <= new Date()) {
    return { label: "หมดอายุ", variant: "warning" };
  }
  return { label: "ใช้งาน", variant: "ok" };
}

export function AdminApiKeysPanel() {
  const qc = useQueryClient();
  const keysQuery = useQuery({
    queryKey: queryKeys.adminApiKeys(),
    queryFn: () => api.adminListApiKeys(),
  });
  const usersQuery = useQuery({
    queryKey: queryKeys.adminUsers({ page: 1, page_size: 100 }),
    queryFn: () => api.adminListUsers({ page: 1, page_size: 100 }),
  });

  const [name, setName] = useState("");
  const [userId, setUserId] = useState("");
  const [expiresDate, setExpiresDate] = useState("");
  const [revealedKey, setRevealedKey] = useState<{ name: string; apiKey: string } | null>(null);
  const [confirmRevoke, setConfirmRevoke] = useState<ApiKeyOut | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<ApiKeyOut | null>(null);

  const activeUsers = (usersQuery.data?.items ?? []).filter((u) => u.is_active);

  const createKey = useMutation({
    mutationFn: () =>
      api.adminCreateApiKey({
        name: name.trim(),
        user_id: userId,
        expires_at: expiresDate ? new Date(`${expiresDate}T23:59:59`).toISOString() : null,
      }),
    onSuccess: (created) => {
      setName("");
      setExpiresDate("");
      setRevealedKey({ name: created.name, apiKey: created.api_key });
      void qc.invalidateQueries({ queryKey: queryKeys.adminApiKeys() });
    },
  });

  const revokeKey = useMutation({
    mutationFn: (keyId: string) => api.adminRevokeApiKey(keyId),
    onSuccess: () => {
      setConfirmRevoke(null);
      void qc.invalidateQueries({ queryKey: queryKeys.adminApiKeys() });
    },
  });

  const deleteKey = useMutation({
    mutationFn: (keyId: string) => api.adminDeleteApiKey(keyId),
    onSuccess: () => {
      setConfirmDelete(null);
      void qc.invalidateQueries({ queryKey: queryKeys.adminApiKeys() });
    },
  });

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-gemini-border/70 p-4 space-y-3 max-w-lg">
        <h3 className="font-medium text-sm">ออก API key ใหม่</h3>
        <p className="text-xs text-gemini-muted">
          Key ใช้สิทธิของบัญชีที่เลือกเสมอ — แนะนำให้สร้างบัญชีบริการ (service account)
          แยกต่อ 1 ผู้ใช้ภายนอก และให้สิทธิเท่าที่จำเป็นในแท็บผู้ใช้ก่อน
        </p>
        <Input
          label="ชื่อ (สื่อว่าให้ใครใช้)"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="partner-x-website"
          maxLength={100}
        />
        <label className="block text-sm">
          <span className="text-gemini-muted">บัญชีที่ key จะใช้สิทธิ</span>
          <select
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
          >
            <option value="">— เลือกบัญชี —</option>
            {activeUsers.map((u) => (
              <option key={u.user_id} value={u.user_id}>
                {u.username}
                {u.full_name ? ` (${u.full_name})` : ""}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-sm">
          <span className="text-gemini-muted">วันหมดอายุ (เว้นว่าง = ไม่หมดอายุ)</span>
          <input
            type="date"
            value={expiresDate}
            onChange={(e) => setExpiresDate(e.target.value)}
            min={new Date().toISOString().slice(0, 10)}
            className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
          />
        </label>
        {createKey.isError && (
          <p className="text-sm text-spark-critical">
            ออก key ไม่สำเร็จ: {createKey.error instanceof Error ? createKey.error.message : "ลองใหม่อีกครั้ง"}
          </p>
        )}
        <Button
          type="button"
          variant="primary"
          loading={createKey.isPending}
          disabled={!name.trim() || !userId}
          onClick={() => createKey.mutate()}
        >
          ออก API key
        </Button>
      </div>

      <QueryBoundary
        query={keysQuery}
        loadingMessage="กำลังโหลด API keys…"
        errorTitle="โหลดรายการ API keys ไม่สำเร็จ"
        treatEmptyArrayAsEmpty
        emptyTitle="ยังไม่มี API key"
        emptyMessage="ออก key แรกด้วยแบบฟอร์มด้านบน เพื่อให้ระบบภายนอกเรียกใช้ API ได้"
        className="py-8 border border-gemini-border/70 rounded-xl"
      >
        {(keys) => (
          <div className="overflow-x-auto rounded-xl border border-gemini-border/70">
            <table className="w-full text-sm">
              <thead className="bg-gemini-surface text-left">
                <tr>
                  <th className="px-3 py-2">ชื่อ</th>
                  <th className="px-3 py-2">Key</th>
                  <th className="px-3 py-2">บัญชี</th>
                  <th className="px-3 py-2">สถานะ</th>
                  <th className="px-3 py-2">ใช้ล่าสุด</th>
                  <th className="px-3 py-2">หมดอายุ</th>
                  <th className="px-3 py-2">สร้างเมื่อ</th>
                  <th className="px-3 py-2" />
                </tr>
              </thead>
              <tbody>
                {keys.map((row) => {
                  const status = keyStatus(row);
                  return (
                    <tr key={row.key_id} className="border-t border-gemini-border/50">
                      <td className="px-3 py-2">{row.name}</td>
                      <td className="px-3 py-2 font-mono text-xs">{row.key_prefix}…</td>
                      <td className="px-3 py-2">{row.username ?? row.user_id}</td>
                      <td className="px-3 py-2">
                        <Badge variant={status.variant}>{status.label}</Badge>
                      </td>
                      <td className="px-3 py-2 text-xs">{formatWhen(row.last_used_at)}</td>
                      <td className="px-3 py-2 text-xs">{formatWhen(row.expires_at)}</td>
                      <td className="px-3 py-2 text-xs">{formatWhen(row.created_at)}</td>
                      <td className="px-3 py-2 text-right whitespace-nowrap">
                        {row.is_active && (
                          <Button type="button" variant="ghost" onClick={() => setConfirmRevoke(row)}>
                            เพิกถอน
                          </Button>
                        )}
                        <Button type="button" variant="ghost" onClick={() => setConfirmDelete(row)}>
                          ลบ
                        </Button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </QueryBoundary>

      {confirmRevoke && (
        <ConfirmDialog
          open
          onClose={() => setConfirmRevoke(null)}
          onConfirm={() => revokeKey.mutate(confirmRevoke.key_id)}
          title="เพิกถอน API key?"
          message={`ระบบภายนอกที่ใช้ "${confirmRevoke.name}" จะเรียก API ไม่ได้ทันที และย้อนกลับไม่ได้`}
          confirmLabel="เพิกถอน"
          cancelLabel="ยกเลิก"
          destructive
          loading={revokeKey.isPending}
        />
      )}

      {confirmDelete && (
        <ConfirmDialog
          open
          onClose={() => setConfirmDelete(null)}
          onConfirm={() => deleteKey.mutate(confirmDelete.key_id)}
          title="ลบ API key?"
          message={`ลบ "${confirmDelete.name}" ออกจากรายการถาวร — key นี้จะใช้ไม่ได้ทันที`}
          confirmLabel="ลบถาวร"
          cancelLabel="ยกเลิก"
          destructive
          loading={deleteKey.isPending}
        />
      )}

      {revealedKey && (
        <Modal open onClose={() => setRevealedKey(null)} title="API key ใหม่">
          <p className="text-sm text-gemini-muted mb-3">
            ออก key <strong>{revealedKey.name}</strong> แล้ว — คัดลอกตอนนี้เท่านั้น
            ระบบเก็บเฉพาะ hash และจะไม่แสดง key เต็มอีก
          </p>
          <div className="flex items-center gap-2 rounded-lg border border-gemini-border px-3 py-2 font-mono text-sm bg-gemini-surface dark:bg-gemini-dark-surface">
            <span className="flex-1 break-all select-all">{revealedKey.apiKey}</span>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                void navigator.clipboard.writeText(revealedKey.apiKey);
              }}
            >
              คัดลอก
            </Button>
          </div>
          <p className="text-xs text-gemini-muted mt-3">
            ใช้เป็น header: <code className="font-mono">Authorization: Bearer {"<key>"}</code> —
            เก็บฝั่ง server เท่านั้น ห้ามฝังในโค้ดหน้าเว็บ
          </p>
        </Modal>
      )}
    </div>
  );
}
