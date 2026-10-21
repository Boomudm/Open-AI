"use client";

import { Button } from "@/components/ui/Button";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Modal } from "@/components/ui/Modal";
import { QueryBoundary } from "@/components/ui/QueryBoundary";
import { api, type AdminUserBrief, type AdminUserCreate, type AdminUserUpdate, type FactoryAccessEntry } from "@/lib/api";
import { roleDisplayLabel } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useMutation, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";

type AccessLevel = "none" | "read" | "write" | "admin";

function accessForFactory(user: AdminUserBrief, factoryId: string): AccessLevel {
  const row = user.factory_access.find((f) => f.factory_id === factoryId);
  if (!row) return "none";
  return row.access_level as AccessLevel;
}

export function AdminUsersPanel() {
  const qc = useQueryClient();
  const {
    data: usersPages,
    isLoading,
    isError,
    error,
    refetch,
    hasNextPage,
    fetchNextPage,
    isFetchingNextPage,
  } = useInfiniteQuery({
    queryKey: queryKeys.adminUsers(),
    queryFn: ({ pageParam = 1 }) => api.adminListUsers({ page: pageParam, page_size: 50 }),
    initialPageParam: 1,
    getNextPageParam: (last) => {
      const loaded = last.page * last.page_size;
      return loaded < last.total ? last.page + 1 : undefined;
    },
  });
  const users = useMemo(
    () => usersPages?.pages.flatMap((p) => p.items) ?? [],
    [usersPages]
  );
  const { data: factories = [] } = useQuery({
    queryKey: queryKeys.adminFactories(),
    queryFn: () => api.adminListFactories(),
  });
  const { data: positions = [] } = useQuery({
    queryKey: queryKeys.adminJobPositions(),
    queryFn: () => api.adminListJobPositions(),
  });

  const [selected, setSelected] = useState<AdminUserBrief | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [createEmail, setCreateEmail] = useState("");
  const [createFullName, setCreateFullName] = useState("");
  const [createUsername, setCreateUsername] = useState("");
  const [createPassword, setCreatePassword] = useState("");
  const [createRole, setCreateRole] = useState("employee");
  const [createFactoryLevels, setCreateFactoryLevels] = useState<Record<string, AccessLevel>>({});
  const [createPositionIds, setCreatePositionIds] = useState<string[]>([]);
  const [role, setRole] = useState("");
  const [isActive, setIsActive] = useState(true);
  const [factoryLevels, setFactoryLevels] = useState<Record<string, AccessLevel>>({});
  const [positionIds, setPositionIds] = useState<string[]>([]);
  const [message, setMessage] = useState("");
  const [createMessage, setCreateMessage] = useState("");
  const [editMessage, setEditMessage] = useState("");
  const [promoteConfirm, setPromoteConfirm] = useState<AdminUserBrief | null>(null);
  const [revealedPassword, setRevealedPassword] = useState<{
    userLabel: string;
    password: string;
  } | null>(null);

  const factoryIds = useMemo(() => {
    const ids = new Set(factories.map((f) => f.factory_id));
    for (const user of users) {
      for (const fa of user.factory_access) ids.add(fa.factory_id);
    }
    return [...ids].sort();
  }, [users, factories]);

  const updateUser = useMutation({
    mutationFn: (body: { userId: string; payload: AdminUserUpdate }) =>
      api.adminUpdateUser(body.userId, body.payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.adminUsers() });
      setEditMessage(
        "บันทึกแล้ว — session ของผู้ใช้ถูกยกเลิกทันที (การเรียก API ครั้งถัดไปจะต้องเข้าสู่ระบบใหม่)"
      );
      setMessage("");
      setCreateMessage("");
    },
    onError: (e) => {
      setEditMessage(parseApiError(e));
      setMessage("");
    },
  });

  const createUser = useMutation({
    mutationFn: (body: AdminUserCreate) => api.adminCreateUser(body),
    onSuccess: (user, variables) => {
      void qc.invalidateQueries({ queryKey: queryKeys.adminUsers() });
      setShowCreate(false);
      setCreateEmail("");
      setCreateFullName("");
      setCreateUsername("");
      setCreatePassword("");
      setCreateRole("employee");
      setCreateFactoryLevels({});
      setCreatePositionIds([]);
      setCreateMessage("");
      setEditMessage("");
      setMessage("");
      setRevealedPassword({
        userLabel: user.full_name || user.username,
        password: variables.password,
      });
    },
    onError: (e) => {
      setCreateMessage(parseApiError(e));
      setMessage("");
    },
  });

  const promote = useMutation({
    mutationFn: (userId: string) => api.adminPromoteOperator(userId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: queryKeys.adminUsers() });
      setMessage(
        "เลื่อนขั้นเป็น Operator แล้ว — session ถูกยกเลิกทันที (ผู้ใช้ต้องเข้าสู่ระบบใหม่)"
      );
      setCreateMessage("");
      setEditMessage("");
    },
    onError: (e) => setMessage(parseApiError(e)),
  });

  function openEdit(user: AdminUserBrief) {
    setSelected(user);
    setRole(user.roles[0] ?? "employee");
    setIsActive(user.is_active);
    const levels: Record<string, AccessLevel> = {};
    for (const fid of factoryIds) {
      levels[fid] = accessForFactory(user, fid);
    }
    setFactoryLevels(levels);
    setPositionIds([...user.job_position_ids]);
    setMessage("");
    setCreateMessage("");
    setEditMessage("");
  }

  function buildFactoryAccessFromLevels(levels: Record<string, AccessLevel>): FactoryAccessEntry[] {
    const entries: FactoryAccessEntry[] = [];
    for (const [factory_id, level] of Object.entries(levels)) {
      if (level !== "none") {
        entries.push({ factory_id, access_level: level });
      }
    }
    return entries;
  }

  function buildFactoryAccess(): FactoryAccessEntry[] {
    return buildFactoryAccessFromLevels(factoryLevels);
  }

  function submitCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!createEmail.trim() || createPassword.length < 8) {
      setCreateMessage("กรอกอีเมลและรหัสผ่านอย่างน้อย 8 ตัว");
      return;
    }
    createUser.mutate({
      email: createEmail.trim(),
      full_name: createFullName.trim() || null,
      username: createUsername.trim() || null,
      password: createPassword,
      role: createRole,
      factory_access: buildFactoryAccessFromLevels(createFactoryLevels),
      job_position_ids: createPositionIds,
    });
  }

  function openCreateForm() {
    setShowCreate(true);
    setSelected(null);
    setMessage("");
    setCreateMessage("");
    setEditMessage("");
    const levels: Record<string, AccessLevel> = {};
    for (const fid of factoryIds) {
      levels[fid] = "read";
    }
    setCreateFactoryLevels(levels);
  }

  function grantReadAllFactories() {
    const levels: Record<string, AccessLevel> = {};
    for (const fid of factoryIds) {
      levels[fid] = "read";
    }
    setCreateFactoryLevels(levels);
  }

  function saveEdit() {
    if (!selected) return;
    updateUser.mutate({
      userId: selected.user_id,
      payload: {
        role,
        is_active: isActive,
        factory_access: buildFactoryAccess(),
        job_position_ids: positionIds,
      },
    });
  }

  function togglePosition(id: string) {
    setPositionIds((prev) =>
      prev.includes(id) ? prev.filter((p) => p !== id) : [...prev, id]
    );
  }

  function isPromoting(userId: string) {
    return promote.isPending && promote.variables === userId;
  }

  const usersListQuery = {
    isLoading,
    isError,
    error: (error as Error | null) ?? null,
    refetch,
    data: users,
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button type="button" variant="primary" onClick={openCreateForm}>
          เพิ่มผู้ใช้
        </Button>
      </div>

      {message && (
        <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm">
          {message}
        </div>
      )}

      {showCreate && (
        <form
          onSubmit={submitCreate}
          className="rounded-xl border border-gemini-blue/40 dark:border-gemini-dark-blue/40 bg-gemini-blue/5 dark:bg-gemini-dark-blue/10 p-4 space-y-4 max-w-3xl"
        >
          <h3 className="font-medium">เพิ่มผู้ใช้ใหม่</h3>
          {createMessage && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-300">
              {createMessage}
            </div>
          )}
          <p className="text-xs text-gemini-muted">
            สร้างบัญชีด้วยอีเมลและรหัสผ่าน — แจ้งรหัสให้ผู้ใช้เข้าสู่ระบบที่ /login
          </p>
          <label className="block text-sm">
            <span className="text-gemini-muted">อีเมล *</span>
            <input
              type="email"
              required
              value={createEmail}
              onChange={(e) => setCreateEmail(e.target.value)}
              className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
            />
          </label>
          <label className="block text-sm">
            <span className="text-gemini-muted">ชื่อ-นามสกุล</span>
            <input
              type="text"
              value={createFullName}
              onChange={(e) => setCreateFullName(e.target.value)}
              className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
            />
          </label>
          <label className="block text-sm">
            <span className="text-gemini-muted">ชื่อผู้ใช้ (ไม่บังคับ)</span>
            <input
              type="text"
              value={createUsername}
              onChange={(e) => setCreateUsername(e.target.value)}
              placeholder="สร้างจากอีเมลอัตโนมัติ"
              className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
            />
          </label>
          <label className="block text-sm">
            <span className="text-gemini-muted">รหัสผ่านชั่วคราว *</span>
            <input
              type="password"
              required
              minLength={8}
              value={createPassword}
              onChange={(e) => setCreatePassword(e.target.value)}
              className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
            />
          </label>
          <label className="block text-sm">
            <span className="text-gemini-muted">ระดับสิทธิ</span>
            <select
              value={createRole}
              onChange={(e) => setCreateRole(e.target.value)}
              className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
            >
              <option value="employee">พนักงาน</option>
              <option value="operator">Operator</option>
              <option value="admin">ผู้ดูแลระบบ</option>
            </select>
          </label>
          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium">สิทธิต่อโรงงาน</p>
              <Button type="button" variant="ghost" onClick={grantReadAllFactories}>
                ให้สิทธิอ่านทุกโรงงาน
              </Button>
            </div>
            {factoryIds.map((fid) => (
              <div key={fid} className="flex items-center gap-2 text-sm">
                <span className="font-mono text-xs w-16">{fid}</span>
                <select
                  value={createFactoryLevels[fid] ?? "none"}
                  onChange={(e) =>
                    setCreateFactoryLevels((prev) => ({
                      ...prev,
                      [fid]: e.target.value as AccessLevel,
                    }))
                  }
                  className="h-8 flex-1 rounded-md border border-gemini-border px-2"
                >
                  <option value="none">ไม่มี</option>
                  <option value="read">อ่าน</option>
                  <option value="write">เขียน</option>
                  <option value="admin">admin</option>
                </select>
              </div>
            ))}
          </div>
          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">ตำแหน่งงาน</legend>
            <div className="flex flex-wrap gap-2">
              {positions.map((pos) => (
                <label
                  key={pos.position_id}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gemini-border/60 px-2 py-1 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={createPositionIds.includes(pos.position_id)}
                    onChange={() =>
                      setCreatePositionIds((prev) =>
                        prev.includes(pos.position_id)
                          ? prev.filter((p) => p !== pos.position_id)
                          : [...prev, pos.position_id]
                      )
                    }
                  />
                  {pos.name_th}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex gap-2">
            <Button type="submit" variant="primary" loading={createUser.isPending}>
              สร้างผู้ใช้
            </Button>
            <Button type="button" variant="ghost" onClick={() => setShowCreate(false)}>
              ยกเลิก
            </Button>
          </div>
        </form>
      )}

      {selected && (
        <div className="rounded-xl border border-gemini-blue/40 dark:border-gemini-dark-blue/40 bg-gemini-blue/5 dark:bg-gemini-dark-blue/10 p-4 space-y-4 max-w-3xl">
          <h3 className="font-medium">แก้ไข {selected.full_name || selected.username}</h3>
          {editMessage && (
            <div
              className={cn(
                "rounded-lg border px-3 py-2 text-sm",
                editMessage.includes("บันทึกแล้ว")
                  ? "border-blue-500/30 bg-blue-500/10"
                  : "border-red-500/30 bg-red-500/10 text-red-700 dark:text-red-300"
              )}
            >
              {editMessage}
            </div>
          )}

          <label className="block text-sm">
            <span className="text-gemini-muted">ระดับสิทธิ</span>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value)}
              className="mt-1 w-full h-9 rounded-md border border-gemini-border px-2"
            >
              <option value="employee">พนักงาน</option>
              <option value="operator">Operator</option>
              <option value="admin">ผู้ดูแลระบบ</option>
            </select>
          </label>

          <label className="inline-flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
            />
            บัญชีใช้งานได้
          </label>

          <div className="space-y-2">
            <p className="text-sm font-medium">สิทธิต่อโรงงาน</p>
            <div className="space-y-2 lg:hidden">
              {factoryIds.map((fid) => (
                <div
                  key={fid}
                  className="flex flex-col gap-1.5 rounded-lg border border-gemini-border/60 p-3"
                >
                  <span className="font-mono text-xs text-gemini-muted">{fid}</span>
                  <select
                    value={factoryLevels[fid] ?? "none"}
                    onChange={(e) =>
                      setFactoryLevels((prev) => ({
                        ...prev,
                        [fid]: e.target.value as AccessLevel,
                      }))
                    }
                    className="h-9 w-full rounded-md border border-gemini-border px-2 text-sm"
                  >
                    <option value="none">ไม่มี</option>
                    <option value="read">อ่าน</option>
                    <option value="write">เขียน</option>
                    <option value="admin">admin</option>
                  </select>
                </div>
              ))}
            </div>
            <div className="hidden lg:block rounded-lg border border-gemini-border/60">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-gemini-muted">
                    <th className="px-2 py-1.5">โรงงาน</th>
                    <th className="px-2 py-1.5">สิทธิ</th>
                  </tr>
                </thead>
                <tbody>
                  {factoryIds.map((fid) => (
                    <tr key={fid} className="border-t border-gemini-border/40">
                      <td className="px-2 py-1.5 font-mono text-xs">{fid}</td>
                      <td className="px-2 py-1.5">
                        <select
                          value={factoryLevels[fid] ?? "none"}
                          onChange={(e) =>
                            setFactoryLevels((prev) => ({
                              ...prev,
                              [fid]: e.target.value as AccessLevel,
                            }))
                          }
                          className="h-8 w-full rounded-md border border-gemini-border px-2 text-sm"
                        >
                          <option value="none">ไม่มี</option>
                          <option value="read">อ่าน</option>
                          <option value="write">เขียน</option>
                          <option value="admin">admin</option>
                        </select>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <fieldset className="space-y-2">
            <legend className="text-sm font-medium">ตำแหน่งงาน</legend>
            <div className="flex flex-wrap gap-2">
              {positions.map((pos) => (
                <label
                  key={pos.position_id}
                  className="inline-flex items-center gap-1.5 rounded-lg border border-gemini-border/60 px-2 py-1 text-xs"
                >
                  <input
                    type="checkbox"
                    checked={positionIds.includes(pos.position_id)}
                    onChange={() => togglePosition(pos.position_id)}
                  />
                  {pos.name_th} ({pos.position_code})
                </label>
              ))}
            </div>
          </fieldset>

          <div className="flex gap-2">
            <Button type="button" variant="primary" loading={updateUser.isPending} onClick={saveEdit}>
              บันทึก
            </Button>
            <Button type="button" variant="ghost" onClick={() => setSelected(null)}>
              ปิด
            </Button>
          </div>
        </div>
      )}

      <QueryBoundary
        query={usersListQuery}
        loadingMessage="กำลังโหลดผู้ใช้…"
        errorTitle="โหลดรายชื่อผู้ใช้ไม่สำเร็จ"
        className="py-8 border border-gemini-border/70 dark:border-gemini-dark-border/70 rounded-xl"
      >
        {() => (
      <div className="overflow-x-auto rounded-xl border border-gemini-border/70 dark:border-gemini-dark-border/70">
        <table className="w-full text-sm">
          <thead className="bg-gemini-surface dark:bg-gemini-dark-surface text-left">
            <tr>
              <th className="px-3 py-2 font-medium">ชื่อ</th>
              <th className="px-3 py-2 font-medium">อีเมล</th>
              <th className="px-3 py-2 font-medium">ระดับสิทธิ</th>
              <th className="px-3 py-2 font-medium">ตำแหน่ง</th>
              <th className="px-3 py-2 font-medium">สถานะ</th>
              <th className="px-3 py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr
                key={user.user_id}
                className={cn(
                  "border-t border-gemini-border/50 dark:border-gemini-dark-border/50",
                  selected?.user_id === user.user_id &&
                    "bg-gemini-blue/5 dark:bg-gemini-dark-blue/10"
                )}
              >
                <td className="px-3 py-2">{user.full_name || user.username}</td>
                <td className="px-3 py-2 text-gemini-muted">{user.email || "—"}</td>
                <td className="px-3 py-2">
                  {user.roles.map((r) => roleDisplayLabel(r)).join(", ")}
                </td>
                <td className="px-3 py-2">{user.job_position_ids.length} ตำแหน่ง</td>
                <td className="px-3 py-2">{user.is_active ? "ใช้งาน" : "ปิด"}</td>
                <td className="px-3 py-2 text-right space-x-2">
                  <Button type="button" variant="ghost" onClick={() => openEdit(user)}>
                    แก้ไข
                  </Button>
                  {user.roles.includes("employee") && (
                    <Button
                      type="button"
                      variant="secondary"
                      loading={isPromoting(user.user_id)}
                      onClick={() => setPromoteConfirm(user)}
                    >
                      เลื่อนเป็น Operator
                    </Button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {hasNextPage && (
          <div className="p-3 border-t border-gemini-border/50 text-center">
            <button
              type="button"
              onClick={() => fetchNextPage()}
              disabled={isFetchingNextPage}
              className="text-sm text-gemini-blue hover:underline disabled:opacity-50 min-h-[44px] px-4"
            >
              {isFetchingNextPage ? "กำลังโหลด…" : "โหลดผู้ใช้เพิ่ม"}
            </button>
          </div>
        )}
      </div>
        )}
      </QueryBoundary>

      {promoteConfirm && (
        <ConfirmDialog
          open
          onClose={() => setPromoteConfirm(null)}
          onConfirm={() => {
            promote.mutate(promoteConfirm.user_id);
            setPromoteConfirm(null);
          }}
          title="เลื่อนขั้นเป็น Operator?"
          message={`เลื่อน ${promoteConfirm.full_name || promoteConfirm.username} เป็น Operator?`}
          confirmLabel="เลื่อนเป็น Operator"
          cancelLabel="ยกเลิก"
          loading={isPromoting(promoteConfirm.user_id)}
        />
      )}

      {revealedPassword && (
        <Modal
          open
          onClose={() => setRevealedPassword(null)}
          title="รหัสผ่านชั่วคราว"
        >
          <p className="text-sm text-gemini-muted mb-3">
            สร้างบัญชี <strong>{revealedPassword.userLabel}</strong> แล้ว — คัดลอกรหัสนี้ให้ผู้ใช้เข้าสู่ระบบที่ /login
          </p>
          <div className="flex items-center gap-2 rounded-lg border border-gemini-border px-3 py-2 font-mono text-sm bg-gemini-surface dark:bg-gemini-dark-surface">
            <span className="flex-1 break-all select-all">{revealedPassword.password}</span>
            <Button
              type="button"
              variant="secondary"
              onClick={() => {
                void navigator.clipboard.writeText(revealedPassword.password);
              }}
            >
              คัดลอก
            </Button>
          </div>
        </Modal>
      )}
    </div>
  );
}
