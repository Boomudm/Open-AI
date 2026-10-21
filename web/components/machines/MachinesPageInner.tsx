"use client";

import { MachineCoverImage, MachineCoverDraftPicker } from "@/components/documents/MachineCoverImage";
import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { QueryBoundary } from "@/components/ui/QueryBoundary";
import { EmptyState } from "@/components/ui/State";
import { useToast } from "@/components/ui/Toast";
import { cn } from "@/lib/cn";
import { useEnsureFactorySelected } from "@/hooks/useEnsureFactorySelected";
import { api, type Machine, type MachineCreatePayload, type MachinePatchPayload } from "@/lib/api";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useUiStore } from "@/stores/uiStore";
import { useMutation, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useRef, useState, useEffect } from "react";

const PAGE_SIZE = 50;

type FormMode = "create" | "edit" | null;

export function MachinesPageInner() {
  const qc = useQueryClient();
  const { showToast } = useToast();
  useEnsureFactorySelected();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const [includeInactive, setIncludeInactive] = useState(false);
  const [q, setQ] = useState("");
  const [formMode, setFormMode] = useState<FormMode>(null);
  const [selected, setSelected] = useState<Machine | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [toggleConfirm, setToggleConfirm] = useState<{
    machine: Machine;
    isActive: boolean;
  } | null>(null);

  const [form, setForm] = useState<MachineCreatePayload>({
    machine_id: "",
    factory_id: selectedFactoryId ?? "",
    machine_name: "",
    machine_type: "",
    manufacturer: "",
    notes: "",
  });
  const [aliasInput, setAliasInput] = useState("");
  const [pendingCoverFile, setPendingCoverFile] = useState<File | null>(null);
  const editorRef = useRef<HTMLFormElement>(null);

  const scrollToEditor = () => {
    requestAnimationFrame(() => {
      editorRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  };

  const listParams = useMemo(
    () => ({
      factory_id: selectedFactoryId ?? undefined,
      q: q.trim() || undefined,
      include_inactive: includeInactive,
    }),
    [selectedFactoryId, q, includeInactive]
  );

  const {
    data,
    isLoading,
    isError,
    error: listError,
    refetch: refetchList,
    fetchNextPage,
    hasNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: queryKeys.machines({ ...listParams, infinite: true }),
    queryFn: ({ pageParam = 1 }) =>
      api.machines({ ...listParams, page: pageParam, page_size: PAGE_SIZE }),
    enabled: Boolean(selectedFactoryId),
    initialPageParam: 1,
    getNextPageParam: (last) => {
      const loaded = last.page * last.page_size;
      return loaded < last.total ? last.page + 1 : undefined;
    },
  });

  const createMachine = useMutation({
    mutationFn: (body: MachineCreatePayload) => api.createMachine(body),
    onSuccess: async (created) => {
      const coverToUpload = pendingCoverFile;
      void qc.invalidateQueries({ queryKey: queryKeys.machines() });
      setSelected(created);
      setFormMode("edit");
      setForm({
        machine_id: created.machine_id,
        factory_id: created.factory_id,
        machine_name: created.machine_name,
        machine_type: created.machine_type ?? "",
        manufacturer: created.manufacturer ?? "",
        notes: "",
      });
      if (coverToUpload) {
        try {
          await api.uploadMachineImage(created.machine_id, coverToUpload);
          void qc.invalidateQueries({ queryKey: queryKeys.machines() });
          void qc.invalidateQueries({ queryKey: ["machineImage", created.machine_id] });
          setSelected((prev) =>
            prev?.machine_id === created.machine_id
              ? { ...prev, image_updated_at: new Date().toISOString() }
              : prev
          );
          showToast("เพิ่มเครื่องและอัปโหลดรูปปกแล้ว");
          setError("");
        } catch (e) {
          showToast("เพิ่มเครื่องแล้ว แต่อัปโหลดรูปไม่สำเร็จ — ลองอัปโหลดอีกครั้ง");
          setError(parseApiError(e));
        }
        setPendingCoverFile(null);
      } else {
        showToast("เพิ่มเครื่องแล้ว — อัปโหลดรูปปกได้ด้านล่าง");
        setError("");
      }
      setMessage("");
      scrollToEditor();
    },
    onError: (e) => setError(parseApiError(e)),
  });

  const updateMachine = useMutation({
    mutationFn: ({ id, body }: { id: string; body: MachinePatchPayload }) =>
      api.updateMachine(id, body),
    onSuccess: (updated, { body }) => {
      void qc.invalidateQueries({ queryKey: queryKeys.machines() });
      if (body.is_active !== undefined) {
        showToast(
          body.is_active
            ? `เปิดใช้งาน ${updated.machine_id} แล้ว`
            : `ปลดระวาง ${updated.machine_id} แล้ว`
        );
        setMessage("");
        if (selected?.machine_id === updated.machine_id) {
          setSelected(updated);
        }
      } else {
        setSelected(updated);
        setForm({
          machine_id: updated.machine_id,
          factory_id: updated.factory_id,
          machine_name: updated.machine_name,
          machine_type: updated.machine_type ?? "",
          manufacturer: updated.manufacturer ?? "",
          notes: "",
        });
        showToast("บันทึกข้อมูลแล้ว");
        setMessage("");
      }
      setError("");
    },
    onError: (e) => setError(parseApiError(e)),
  });

  const addAlias = useMutation({
    mutationFn: ({ id, alias }: { id: string; alias: string }) => api.addMachineAlias(id, alias),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.machines() });
      setAliasInput("");
      showToast("เพิ่มชื่อเรียกแล้ว");
      setMessage("");
      setError("");
    },
    onError: (e) => setError(parseApiError(e)),
  });

  function openCreate() {
    setFormMode("create");
    setSelected(null);
    setPendingCoverFile(null);
    setForm({
      machine_id: "",
      factory_id: selectedFactoryId ?? "",
      machine_name: "",
      machine_type: "",
      manufacturer: "",
      notes: "",
    });
    setError("");
    scrollToEditor();
  }

  function openEdit(machine: Machine) {
    setSelected(machine);
    setFormMode("edit");
    setForm({
      machine_id: machine.machine_id,
      factory_id: machine.factory_id,
      machine_name: machine.machine_name,
      machine_type: machine.machine_type ?? "",
      manufacturer: machine.manufacturer ?? "",
      notes: "",
    });
    setError("");
    scrollToEditor();
  }

  const machines = useMemo(() => data?.pages.flatMap((p) => p.items) ?? [], [data]);
  const total = data?.pages[0]?.total ?? 0;

  useEffect(() => {
    if (!selected) return;
    const fresh = machines.find((m) => m.machine_id === selected.machine_id);
    if (
      fresh &&
      (fresh.image_updated_at !== selected.image_updated_at ||
        fresh.machine_name !== selected.machine_name)
    ) {
      setSelected(fresh);
    }
  }, [machines, selected]);

  function toggleMachineActive(machine: Machine, isActive: boolean) {
    setToggleConfirm({ machine, isActive });
  }

  function isRowUpdating(machineId: string) {
    return updateMachine.isPending && updateMachine.variables?.id === machineId;
  }

  function submitForm(e: React.FormEvent) {
    e.preventDefault();
    if (formMode === "create") {
      createMachine.mutate({
        ...form,
        machine_type: form.machine_type || null,
        manufacturer: form.manufacturer || null,
        notes: form.notes || null,
      });
      return;
    }
    if (formMode === "edit" && selected) {
      updateMachine.mutate({
        id: selected.machine_id,
        body: {
          machine_name: form.machine_name,
          machine_type: form.machine_type || null,
          manufacturer: form.manufacturer || null,
          notes: form.notes || null,
        },
      });
    }
  }

  const isFormSaving =
    createMachine.isPending ||
    (updateMachine.isPending &&
      updateMachine.variables?.body?.is_active === undefined &&
      updateMachine.variables?.id === selected?.machine_id);

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-gemini-border/50 dark:border-gemini-dark-border/50 bg-gemini-bg/90 dark:bg-gemini-dark-bg/90 backdrop-blur-md">
        <div className="max-w-5xl mx-auto px-4 py-3 flex flex-wrap items-center gap-3">
          <div className="flex-1 min-w-0">
            <h1 className="text-lg font-semibold">จัดการเครื่องจักร</h1>
            <p className="text-xs text-gemini-muted mt-0.5">
              เพิ่ม แก้ไข หรือปลดระวางเครื่องในโรงงาน — รหัสเครื่องเช่น MC-001
            </p>
          </div>
          <Button type="button" variant="primary" onClick={openCreate} disabled={!selectedFactoryId}>
            เพิ่มเครื่อง
          </Button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-4">
        {message && (
          <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm">{message}</div>
        )}
        {error && (
          <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        <div className="flex flex-wrap gap-3 items-center">
          <input
            type="search"
            placeholder="ค้นหาชื่อหรือรหัสเครื่อง…"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            className="h-9 flex-1 min-w-[12rem] rounded-lg border border-gemini-border px-3 text-sm"
          />
          <label className="inline-flex items-center gap-2 text-sm text-gemini-muted">
            <input
              type="checkbox"
              checked={includeInactive}
              onChange={(e) => setIncludeInactive(e.target.checked)}
            />
            แสดงเครื่องปลดระวาง
          </label>
        </div>

        {formMode && (
          <>
            <div
              className="md:hidden fixed inset-0 z-[80] bg-black/40"
              aria-hidden
              onClick={() => setFormMode(null)}
            />
            <form
              ref={editorRef}
              onSubmit={submitForm}
              className={cn(
                "rounded-xl border border-gemini-blue/40 dark:border-gemini-dark-blue/40 bg-gemini-blue/5 dark:bg-gemini-dark-blue/10 p-4 md:p-5 space-y-4 max-w-3xl scroll-mt-24",
                "md:relative md:z-auto",
                "fixed inset-x-0 bottom-0 z-[90] max-h-[92dvh] overflow-y-auto rounded-b-none md:rounded-xl md:max-h-none md:overflow-visible"
              )}
            >
              <div className="space-y-1">
                <h2 className="font-semibold text-base">
                  {formMode === "create" ? "เพิ่มเครื่องจักรใหม่" : `แก้ไข ${form.machine_id}`}
                </h2>
                <p className="text-xs text-gemini-muted">
                  อัปโหลดรูปและแก้ไขข้อมูลเครื่อง แล้วกดบันทึก
                </p>
              </div>

              <div className="grid gap-5 md:grid-cols-[minmax(0,220px)_1fr]">
                {formMode === "edit" && selected ? (
                  <MachineCoverImage
                    machineId={selected.machine_id}
                    machineName={form.machine_name}
                    machineType={form.machine_type || selected.machine_type}
                    imageUpdatedAt={selected.image_updated_at}
                    showUpload
                    variant="editor"
                    aspectClass="aspect-square max-w-[220px]"
                    onImageChange={() => {
                      void qc.invalidateQueries({ queryKey: queryKeys.machines() });
                    }}
                  />
                ) : (
                  <MachineCoverDraftPicker
                    machineType={form.machine_type}
                    file={pendingCoverFile}
                    onFileChange={setPendingCoverFile}
                    aspectClass="aspect-square max-w-[220px]"
                  />
                )}

                <div className="space-y-3">
                  {formMode === "create" ? (
                    <div className="rounded-lg border border-gemini-border/60 bg-gemini-bg/50 dark:bg-gemini-dark-bg/50 px-3 py-2 text-sm">
                      <label className="block">
                        <span className="text-gemini-muted">รหัสเครื่อง (MC-…)</span>
                        <input
                          required
                          minLength={3}
                          maxLength={20}
                          value={form.machine_id}
                          onChange={(e) =>
                            setForm((f) => ({ ...f, machine_id: e.target.value.toUpperCase() }))
                          }
                          className="mt-1 w-full bg-transparent font-mono font-medium outline-none placeholder:text-gemini-muted/50"
                          placeholder="MC-006"
                        />
                      </label>
                    </div>
                  ) : (
                    <div className="rounded-lg border border-gemini-border/60 bg-gemini-bg/50 dark:bg-gemini-dark-bg/50 px-3 py-2 text-sm">
                      <span className="text-gemini-muted">รหัสเครื่อง</span>
                      <p className="font-mono font-medium mt-0.5">{form.machine_id}</p>
                    </div>
                  )}
                  <label className="block text-sm">
                    <span className="text-gemini-muted">ชื่อเครื่อง</span>
                    <input
                      required
                      value={form.machine_name}
                      onChange={(e) => setForm((f) => ({ ...f, machine_name: e.target.value }))}
                      className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
                      placeholder="Servo Motor Line A"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-gemini-muted">ประเภท</span>
                    <input
                      value={form.machine_type ?? ""}
                      onChange={(e) => setForm((f) => ({ ...f, machine_type: e.target.value }))}
                      className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
                      placeholder="motor, press, cnc…"
                    />
                  </label>
                  <label className="block text-sm">
                    <span className="text-gemini-muted">ผู้ผลิต</span>
                    <input
                      value={form.manufacturer ?? ""}
                      onChange={(e) => setForm((f) => ({ ...f, manufacturer: e.target.value }))}
                      className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
                      placeholder="Mitsubishi, Fanuc…"
                    />
                  </label>
                </div>
              </div>

              <div className="flex flex-wrap gap-2 pt-1 border-t border-gemini-border/40">
                <Button type="submit" variant="primary" loading={isFormSaving}>
                  บันทึกข้อมูล
                </Button>
                <Button type="button" variant="ghost" onClick={() => setFormMode(null)}>
                  ยกเลิก
                </Button>
              </div>
            </form>
          </>
        )}

        {!selectedFactoryId ? (
          <EmptyState
            title="เลือกโรงงานก่อน"
            message="เลือกโรงงานจากแถบด้านซ้ายเพื่อดูและจัดการเครื่องจักร"
            className="py-12 border-0 bg-transparent"
          />
        ) : (
          <QueryBoundary
            query={{
              isLoading,
              isError,
              error: listError,
              refetch: refetchList,
              data: data ?? { pages: [] },
            }}
            loadingMessage="กำลังโหลดรายการเครื่อง…"
            errorTitle="โหลดรายการเครื่องไม่สำเร็จ"
            className="py-8 border-0 bg-transparent"
          >
            {() => (
              <>
            {machines.length === 0 ? (
              <EmptyState
                title="ยังไม่มีเครื่องจักร"
                message="กด «เพิ่มเครื่อง» เพื่อลงทะเบียนเครื่องแรกในโรงงานนี้"
                className="py-12 border-0 bg-transparent"
              />
            ) : (
              <>
            {machines.length > 0 && (
              <p className="text-xs text-gemini-muted text-center">
                แสดง {machines.length} จาก {total} เครื่อง
              </p>
            )}
            <div className="hidden md:block overflow-x-auto rounded-xl border border-gemini-border/70">
              <table className="w-full text-sm">
                <thead className="bg-gemini-surface dark:bg-gemini-dark-surface text-left">
                  <tr>
                    <th className="px-3 py-2 font-medium">รหัส</th>
                    <th className="px-3 py-2 font-medium">ชื่อ</th>
                    <th className="px-3 py-2 font-medium">ประเภท</th>
                    <th className="px-3 py-2 font-medium">สถานะ</th>
                    <th className="px-3 py-2 font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {machines.map((m) => (
                    <tr
                      key={m.machine_id}
                      className={
                        formMode === "edit" && selected?.machine_id === m.machine_id
                          ? "border-t border-gemini-border/50 bg-gemini-blue/5 dark:bg-gemini-dark-blue/10"
                          : "border-t border-gemini-border/50"
                      }
                    >
                      <td className="px-3 py-2 font-mono text-xs">{m.machine_id}</td>
                      <td className="px-3 py-2">{m.machine_name}</td>
                      <td className="px-3 py-2 text-gemini-muted">{m.machine_type ?? "—"}</td>
                      <td className="px-3 py-2">{m.is_active ? "ใช้งาน" : "ปลดระวาง"}</td>
                      <td className="px-3 py-2 text-right space-x-2">
                        <Button
                          type="button"
                          variant="ghost"
                          onClick={() => {
                            setSelected(m);
                            openEdit(m);
                          }}
                        >
                          แก้ไข
                        </Button>
                        {m.is_active && (
                          <Button
                            type="button"
                            variant="secondary"
                            loading={isRowUpdating(m.machine_id)}
                            onClick={() => toggleMachineActive(m, false)}
                          >
                            ปลดระวาง
                          </Button>
                        )}
                        {!m.is_active && (
                          <Button
                            type="button"
                            variant="secondary"
                            loading={isRowUpdating(m.machine_id)}
                            onClick={() => toggleMachineActive(m, true)}
                          >
                            เปิดใช้งาน
                          </Button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {machines.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-3 py-8 text-center text-gemini-muted">
                        ไม่พบเครื่องจักร
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
            <ul className="md:hidden space-y-3">
              {machines.map((m) => (
                <li
                  key={m.machine_id}
                  className="rounded-xl border border-gemini-border/70 p-4 space-y-2"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div>
                      <p className="font-mono text-xs text-gemini-muted">{m.machine_id}</p>
                      <p className="font-medium">{m.machine_name}</p>
                      <p className="text-xs text-gemini-muted mt-0.5">
                        {m.machine_type ?? "—"} · {m.is_active ? "ใช้งาน" : "ปลดระวาง"}
                      </p>
                    </div>
                  </div>
                  <div className="flex flex-col gap-2">
                    <Button
                      type="button"
                      variant="ghost"
                      className="w-full"
                      onClick={() => {
                        setSelected(m);
                        openEdit(m);
                      }}
                    >
                      แก้ไข
                    </Button>
                    {m.is_active ? (
                      <Button
                        type="button"
                        variant="secondary"
                        className="w-full"
                        loading={isRowUpdating(m.machine_id)}
                        onClick={() => toggleMachineActive(m, false)}
                      >
                        ปลดระวาง
                      </Button>
                    ) : (
                      <Button
                        type="button"
                        variant="secondary"
                        className="w-full"
                        loading={isRowUpdating(m.machine_id)}
                        onClick={() => toggleMachineActive(m, true)}
                      >
                        เปิดใช้งาน
                      </Button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
            {hasNextPage && (
              <div className="flex justify-center pt-2">
                <Button
                  type="button"
                  variant="secondary"
                  loading={isFetchingNextPage}
                  onClick={() => void fetchNextPage()}
                >
                  โหลดเพิ่ม
                </Button>
              </div>
            )}
              </>
            )}
              </>
            )}
          </QueryBoundary>
        )}

        {selected && formMode === null && (
          <div className="rounded-xl border border-gemini-border/70 p-4 space-y-3 max-w-3xl">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <p className="font-mono text-xs text-gemini-muted">{selected.machine_id}</p>
                <h3 className="font-semibold">{selected.machine_name}</h3>
                <p className="text-sm text-gemini-muted mt-0.5">
                  {[selected.machine_type, selected.manufacturer].filter(Boolean).join(" · ") || "—"}
                </p>
              </div>
              <Button type="button" variant="secondary" onClick={() => openEdit(selected)}>
                แก้ไขข้อมูล / รูป
              </Button>
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <MachineCoverImage
                machineId={selected.machine_id}
                machineName={selected.machine_name}
                machineType={selected.machine_type}
                imageUpdatedAt={selected.image_updated_at}
                showUpload
                variant="card"
              />
              <div className="rounded-xl border border-gemini-border/70 p-3 space-y-2">
                <h3 className="text-sm font-medium">ชื่อเรียก (alias)</h3>
                <p className="text-xs text-gemini-muted">
                  ชื่อที่ช่างใช้เรียกในโรงงาน เช่น &quot;เครื่อง 1&quot;
                </p>
                <div className="flex gap-2">
                  <input
                    value={aliasInput}
                    onChange={(e) => setAliasInput(e.target.value)}
                    placeholder="เครื่อง 1"
                    className="flex-1 h-9 rounded-md border border-gemini-border px-2 text-sm"
                  />
                  <Button
                    type="button"
                    variant="secondary"
                    disabled={!aliasInput.trim()}
                    loading={addAlias.isPending}
                    onClick={() =>
                      addAlias.mutate({ id: selected.machine_id, alias: aliasInput.trim() })
                    }
                  >
                    เพิ่ม
                  </Button>
                </div>
              </div>
            </div>

          </div>
        )}
      </main>

      {toggleConfirm && (
        <ConfirmDialog
          open
          onClose={() => setToggleConfirm(null)}
          onConfirm={() => {
            updateMachine.mutate({
              id: toggleConfirm.machine.machine_id,
              body: { is_active: toggleConfirm.isActive },
            });
            setToggleConfirm(null);
          }}
          title={toggleConfirm.isActive ? "เปิดใช้งานเครื่อง?" : "ปลดระวางเครื่อง?"}
          message={`${toggleConfirm.isActive ? "เปิดใช้งาน" : "ปลดระวาง"}เครื่อง ${toggleConfirm.machine.machine_id} (${toggleConfirm.machine.machine_name})?`}
          confirmLabel={toggleConfirm.isActive ? "เปิดใช้งาน" : "ปลดระวาง"}
          cancelLabel="ยกเลิก"
          destructive={!toggleConfirm.isActive}
          loading={
            updateMachine.isPending &&
            updateMachine.variables?.id === toggleConfirm.machine.machine_id
          }
        />
      )}
    </>
  );
}

