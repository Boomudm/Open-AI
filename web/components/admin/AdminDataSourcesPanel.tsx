"use client";

import { Button } from "@/components/ui/Button";
import { ErrorState, LoadingState } from "@/components/ui/State";
import {
  api,
  type ExternalDataSourceCreate,
  type ExternalDataSourceOut,
  type ExternalDiscoveredTable,
  type JobPositionBrief,
} from "@/lib/api";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Database, Loader2, Plug, Trash2 } from "lucide-react";
import { useMemo, useState } from "react";

/** Per-table access scope the admin is editing: which factories / job positions can see it. */
type TableScope = { factory_ids: string[]; position_ids: string[] };

function scopeKey(schemaName: string, tableName: string): string {
  return `${schemaName}.${tableName}`;
}

function toggleInArray(list: string[], value: string): string[] {
  return list.includes(value) ? list.filter((v) => v !== value) : [...list, value];
}

const inputCls =
  "w-full h-9 rounded-md border border-gemini-border dark:border-gemini-dark-border bg-gemini-bg/50 dark:bg-gemini-dark-bg/50 px-2 text-sm outline-none focus:border-gemini-blue";

const emptyForm: ExternalDataSourceCreate = {
  name: "",
  host: "localhost",
  port: 5432,
  database_name: "",
  username: "",
  password: "",
  ssl_mode: "prefer",
  factory_id: "",
  scope_column: "",
  is_enabled: false,
};

function DataSourceCard({
  source,
  factoryOptions,
  positions,
}: {
  source: ExternalDataSourceOut;
  factoryOptions: string[];
  positions: JobPositionBrief[];
}) {
  const qc = useQueryClient();
  const [discovered, setDiscovered] = useState<ExternalDiscoveredTable[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(source.allowed_tables.map((t) => scopeKey(t.schema_name, t.table_name)))
  );
  const [scopes, setScopes] = useState<Record<string, TableScope>>(() => {
    const initial: Record<string, TableScope> = {};
    for (const t of source.allowed_tables) {
      initial[scopeKey(t.schema_name, t.table_name)] = {
        factory_ids: t.factory_ids,
        position_ids: t.position_ids,
      };
    }
    return initial;
  });
  const [message, setMessage] = useState("");

  function scopeFor(key: string): TableScope {
    return scopes[key] ?? { factory_ids: [], position_ids: [] };
  }
  function updateScope(key: string, patch: Partial<TableScope>) {
    setScopes((prev) => ({ ...prev, [key]: { ...scopeFor(key), ...patch } }));
  }

  const discoverMut = useMutation({
    mutationFn: () => api.adminDiscoverDataSourceTables(source.source_id),
    onSuccess: (rows) => {
      setDiscovered(rows);
      setMessage((prev) => `${prev ? `${prev} · ` : ""}พบ ${rows.length} ตารางในฐานข้อมูล — เลือกตารางที่จะอนุญาตด้านล่าง`);
    },
    onError: (err) => setMessage(parseApiError(err)),
  });

  const testMut = useMutation({
    mutationFn: () => api.adminTestDataSource(source.source_id),
    onSuccess: (res) => {
      setMessage(res.ok ? `✓ ${res.message}` : `✗ ${res.message}`);
      // Connection works — immediately pull the table list so the admin doesn't
      // have to click a second button just to see what's in the database.
      if (res.ok) discoverMut.mutate();
    },
    onError: (err) => setMessage(parseApiError(err)),
  });

  const saveTablesMut = useMutation({
    mutationFn: () => {
      const rows = (discovered ?? []).filter((t) => selected.has(scopeKey(t.schema_name, t.table_name)));
      const fallback = source.allowed_tables
        .filter((t) => selected.has(scopeKey(t.schema_name, t.table_name)))
        .map((t) => ({
          schema_name: t.schema_name,
          table_name: t.table_name,
          description: t.description,
          columns_meta: t.columns_meta,
        }));
      const base =
        rows.length > 0
          ? rows.map((t) => ({
              schema_name: t.schema_name,
              table_name: t.table_name,
              columns_meta: t.columns,
            }))
          : fallback;
      const payload = base.map((t) => ({
        ...t,
        ...scopeFor(scopeKey(t.schema_name, t.table_name)),
      }));
      return api.adminSetDataSourceTables(source.source_id, payload);
    },
    onSuccess: () => {
      setMessage("บันทึกตารางและสิทธิ์เข้าถึงแล้ว");
      void qc.invalidateQueries({ queryKey: queryKeys.adminDataSources() });
    },
    onError: (err) => setMessage(parseApiError(err)),
  });

  const toggleMut = useMutation({
    mutationFn: (enabled: boolean) =>
      api.adminUpdateDataSource(source.source_id, { is_enabled: enabled }),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.adminDataSources() }),
  });

  const deleteMut = useMutation({
    mutationFn: () => api.adminDeleteDataSource(source.source_id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: queryKeys.adminDataSources() }),
  });

  // Before the admin (re)discovers, still show already-saved tables so their
  // factory/position scope stays editable without an extra round-trip.
  const tableRows: ExternalDiscoveredTable[] =
    discovered ??
    source.allowed_tables.map((t) => ({
      schema_name: t.schema_name,
      table_name: t.table_name,
      columns: t.columns_meta.map((c) => ({
        column_name: c.column_name,
        data_type: c.data_type,
        is_nullable: c.is_nullable,
      })),
    }));

  return (
    <div className="rounded-xl border border-gemini-border/70 dark:border-gemini-dark-border/70 p-4 space-y-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="font-medium text-gemini-text dark:text-gemini-dark-text flex items-center gap-2">
            <Database className="h-4 w-4 text-gemini-blue" />
            {source.name}
          </h3>
          <p className="text-xs text-gemini-muted mt-1 font-mono">
            {source.username}@{source.host}:{source.port}/{source.database_name}
            {source.factory_id ? ` · โรงงาน ${source.factory_id}` : " · ทุกโรงงาน"}
          </p>
          {source.scope_column && (
            <p className="text-xs text-gemini-muted">scope column: {source.scope_column}</p>
          )}
        </div>
        <label className="inline-flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={source.is_enabled}
            onChange={(e) => toggleMut.mutate(e.target.checked)}
            disabled={toggleMut.isPending}
          />
          เปิดใช้ในแชท
        </label>
      </div>

      <p className="text-xs text-gemini-muted">
        ตารางที่อนุญาต: {source.allowed_tables.length} รายการ
      </p>

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"
          variant="secondary"
          size="sm"
          loading={testMut.isPending}
          onClick={() => testMut.mutate()}
          leftIcon={<Plug className="h-3.5 w-3.5" />}
        >
          ทดสอบการเชื่อมต่อ
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          loading={discoverMut.isPending}
          onClick={() => discoverMut.mutate()}
        >
          รีเฟรชรายชื่อตาราง
        </Button>
        <Button
          type="button"
          variant="primary"
          size="sm"
          loading={saveTablesMut.isPending}
          onClick={() => saveTablesMut.mutate()}
          disabled={selected.size === 0}
          leftIcon={<CheckCircle2 className="h-3.5 w-3.5" />}
        >
          บันทึกตารางที่เลือก ({selected.size})
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          loading={deleteMut.isPending}
          onClick={() => {
            if (window.confirm(`ลบ ${source.name}?`)) deleteMut.mutate();
          }}
          leftIcon={<Trash2 className="h-3.5 w-3.5" />}
        >
          ลบ
        </Button>
      </div>

      {message && <p className="text-xs text-gemini-muted">{message}</p>}

      {tableRows.length > 0 && (
        <div className="max-h-96 overflow-y-auto gemini-scrollbar rounded-lg border border-gemini-border/50 p-2 space-y-1">
          {tableRows.map((t) => {
            const key = scopeKey(t.schema_name, t.table_name);
            const on = selected.has(key);
            const scope = scopeFor(key);
            return (
              <div
                key={key}
                className={cn("rounded px-2 py-1.5", on && "bg-gemini-blue/10")}
              >
                <label className="flex items-center gap-2 text-xs cursor-pointer">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={() =>
                      setSelected((prev) => {
                        const next = new Set(prev);
                        if (on) next.delete(key);
                        else next.add(key);
                        return next;
                      })
                    }
                  />
                  <span className="font-mono">{key}</span>
                  <span className="text-gemini-muted">({t.columns.length} cols)</span>
                </label>

                {on && (
                  <div className="mt-1.5 ml-5 space-y-1.5">
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="text-[10px] text-gemini-muted shrink-0">โรงงาน:</span>
                      {factoryOptions.length === 0 ? (
                        <span className="text-[10px] text-gemini-muted">— ไม่มีโรงงานให้เลือก —</span>
                      ) : (
                        factoryOptions.map((fid) => {
                          const checked = scope.factory_ids.includes(fid);
                          return (
                            <button
                              key={fid}
                              type="button"
                              onClick={() =>
                                updateScope(key, { factory_ids: toggleInArray(scope.factory_ids, fid) })
                              }
                              className={cn(
                                "rounded-full border px-2 py-0.5 text-[10px]",
                                checked
                                  ? "border-gemini-blue bg-gemini-blue/20 text-gemini-blue"
                                  : "border-gemini-border/60 text-gemini-muted"
                              )}
                            >
                              {fid}
                            </button>
                          );
                        })
                      )}
                      {scope.factory_ids.length === 0 && (
                        <span className="text-[10px] text-gemini-muted">(ว่าง = ทุกโรงงานที่เข้าถึง source นี้ได้)</span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="text-[10px] text-gemini-muted shrink-0">ตำแหน่ง:</span>
                      {positions.length === 0 ? (
                        <span className="text-[10px] text-gemini-muted">— ไม่มีตำแหน่งให้เลือก —</span>
                      ) : (
                        positions.map((p) => {
                          const checked = scope.position_ids.includes(p.position_id);
                          return (
                            <button
                              key={p.position_id}
                              type="button"
                              onClick={() =>
                                updateScope(key, {
                                  position_ids: toggleInArray(scope.position_ids, p.position_id),
                                })
                              }
                              className={cn(
                                "rounded-full border px-2 py-0.5 text-[10px]",
                                checked
                                  ? "border-gemini-blue bg-gemini-blue/20 text-gemini-blue"
                                  : "border-gemini-border/60 text-gemini-muted"
                              )}
                            >
                              {p.name_th}
                            </button>
                          );
                        })
                      )}
                      {scope.position_ids.length === 0 && (
                        <span className="text-[10px] text-gemini-muted">(ว่าง = ทุกตำแหน่ง)</span>
                      )}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function AdminDataSourcesPanel() {
  const qc = useQueryClient();
  const [form, setForm] = useState<ExternalDataSourceCreate>({ ...emptyForm });
  const [formError, setFormError] = useState("");

  const { data: sources = [], isLoading, isError, error: loadError, refetch } = useQuery({
    queryKey: queryKeys.adminDataSources(),
    queryFn: () => api.adminListDataSources(),
  });

  const { data: factories = [] } = useQuery({
    queryKey: queryKeys.adminFactories(),
    queryFn: () => api.adminListFactories(),
  });

  const { data: positions = [] } = useQuery({
    queryKey: queryKeys.jobPositions(),
    queryFn: () => api.listJobPositions(),
  });

  const factoryOptions = useMemo(
    () => factories.map((f) => f.factory_id).sort(),
    [factories]
  );

  const createMut = useMutation({
    mutationFn: () =>
      api.adminCreateDataSource({
        ...form,
        factory_id: form.factory_id?.trim() || null,
        scope_column: form.scope_column?.trim() || null,
        description: form.description?.trim() || null,
      }),
    onSuccess: () => {
      setForm({ ...emptyForm });
      setFormError("");
      setTestMessage("");
      void qc.invalidateQueries({ queryKey: queryKeys.adminDataSources() });
    },
    onError: (err) => setFormError(parseApiError(err)),
  });

  const [testMessage, setTestMessage] = useState("");
  const testFormMut = useMutation({
    mutationFn: () =>
      api.adminTestConnectionParams({
        host: form.host,
        port: form.port ?? 5432,
        database_name: form.database_name,
        username: form.username,
        password: form.password,
        ssl_mode: form.ssl_mode ?? "prefer",
      }),
    onSuccess: (res) => setTestMessage(res.ok ? `✓ ${res.message}` : `✗ ${res.message}`),
    onError: (err) => setTestMessage(`✗ ${parseApiError(err)}`),
  });

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-gemini-border/70 dark:border-gemini-dark-border/70 p-4 space-y-3">
        <h2 className="text-sm font-semibold">เพิ่ม Postgres ภายนอก</h2>
        <p className="text-xs text-gemini-muted">
          ลงทะเบียน DB ของคุณ เลือกตารางที่อนุญาต แล้วผู้ใช้ถามผ่านแชทได้ (live query)
        </p>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="text-xs block">
            ชื่อ
            <input
              className={inputCls}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
            />
          </label>
          <label className="text-xs block">
            โรงงาน (ว่าง = ทุกโรงงาน)
            <select
              className={inputCls}
              value={form.factory_id ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, factory_id: e.target.value }))}
            >
              <option value="">— ทุกโรงงาน —</option>
              {factoryOptions.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs block">
            Host
            <input
              className={inputCls}
              value={form.host}
              onChange={(e) => setForm((f) => ({ ...f, host: e.target.value }))}
            />
          </label>
          <label className="text-xs block">
            Port
            <input
              type="number"
              className={inputCls}
              value={form.port ?? 5432}
              onChange={(e) => setForm((f) => ({ ...f, port: Number(e.target.value) }))}
            />
          </label>
          <label className="text-xs block">
            Database
            <input
              className={inputCls}
              value={form.database_name}
              onChange={(e) => setForm((f) => ({ ...f, database_name: e.target.value }))}
            />
          </label>
          <label className="text-xs block">
            Username
            <input
              className={inputCls}
              value={form.username}
              onChange={(e) => setForm((f) => ({ ...f, username: e.target.value }))}
            />
          </label>
          <label className="text-xs block sm:col-span-2">
            Password
            <input
              type="password"
              className={inputCls}
              value={form.password}
              onChange={(e) => setForm((f) => ({ ...f, password: e.target.value }))}
            />
          </label>
          <label className="text-xs block">
            Scope column (เช่น factory_id)
            <input
              className={inputCls}
              placeholder="factory_id"
              value={form.scope_column ?? ""}
              onChange={(e) => setForm((f) => ({ ...f, scope_column: e.target.value }))}
            />
          </label>
          <label className="text-xs block">
            SSL mode
            <select
              className={inputCls}
              value={form.ssl_mode ?? "prefer"}
              onChange={(e) => setForm((f) => ({ ...f, ssl_mode: e.target.value }))}
            >
              <option value="prefer">prefer</option>
              <option value="require">require</option>
              <option value="disable">disable</option>
            </select>
          </label>
        </div>
        {formError && <p className="text-xs text-red-500">{formError}</p>}
        {testMessage && <p className="text-xs text-gemini-muted">{testMessage}</p>}
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="secondary"
            loading={testFormMut.isPending}
            disabled={!form.host || !form.database_name || !form.username || !form.password}
            onClick={() => testFormMut.mutate()}
            leftIcon={<Plug className="h-3.5 w-3.5" />}
          >
            ทดสอบการเชื่อมต่อ
          </Button>
          <Button
            type="button"
            variant="primary"
            loading={createMut.isPending}
            disabled={!form.name || !form.host || !form.database_name || !form.username || !form.password}
            onClick={() => createMut.mutate()}
          >
            สร้าง data source
          </Button>
        </div>
      </section>

      {isLoading ? (
        <LoadingState message="กำลังโหลด data sources…" />
      ) : isError ? (
        <ErrorState message={parseApiError(loadError)} onRetry={() => refetch()} />
      ) : sources.length === 0 ? (
        <p className="text-sm text-gemini-muted text-center py-8">ยังไม่มี data source</p>
      ) : (
        <div className="space-y-3">
          {sources.map((s) => (
            <DataSourceCard key={s.source_id} source={s} factoryOptions={factoryOptions} positions={positions} />
          ))}
        </div>
      )}
    </div>
  );
}
