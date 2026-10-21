"use client";

import dynamic from "next/dynamic";

const AdminJobPositionsPanel = dynamic(
  () => import("@/components/admin/AdminJobPositionsPanel").then(m => m.AdminJobPositionsPanel),
);
const AdminUsersPanel = dynamic(
  () => import("@/components/admin/AdminUsersPanel").then(m => m.AdminUsersPanel),
);
const AdminDataSourcesPanel = dynamic(
  () => import("@/components/admin/AdminDataSourcesPanel").then((m) => m.AdminDataSourcesPanel),
);
const AdminApiKeysPanel = dynamic(
  () => import("@/components/admin/AdminApiKeysPanel").then((m) => m.AdminApiKeysPanel),
);
import { LoadingState } from "@/components/ui/State";
import { cn } from "@/lib/cn";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { STALE_STATIC } from "@/lib/query-config";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type AdminTab = "users" | "positions" | "data-sources" | "api-keys";

export default function AdminPage() {
  const router = useRouter();
  const [tab, setTab] = useState<AdminTab>("users");
  const { data: profile, isLoading, isError } = useQuery({
    queryKey: queryKeys.myProfile(),
    queryFn: () => api.getMyProfile(),
    staleTime: STALE_STATIC,
    retry: false,
  });

  const isAdmin = Boolean(profile?.roles.includes("admin"));

  useEffect(() => {
    if (isLoading) return;
    if (isError || !isAdmin) {
      router.replace("/chat");
    }
  }, [isAdmin, isError, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <LoadingState message="กำลังตรวจสอบสิทธิ์ผู้ดูแลระบบ…" />
      </div>
    );
  }

  if (!isAdmin) {
    return null;
  }

  return (
    <>
      <header className="sticky top-0 z-20 border-b border-gemini-border/50 dark:border-gemini-dark-border/50 bg-gemini-bg/90 dark:bg-gemini-dark-bg/90 backdrop-blur-md">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <h1 className="text-lg font-semibold text-gemini-text dark:text-gemini-dark-text">
            ผู้ดูแลระบบ
          </h1>
          <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
            จัดการผู้ใช้ ตำแหน่งงาน แหล่งข้อมูลภายนอก และสิทธิการเข้าถึง
          </p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6 space-y-6">
        <div className="flex gap-2 border-b border-gemini-border/70 dark:border-gemini-dark-border/70">
          {(
            [
              ["users", "ผู้ใช้"],
              ["positions", "ตำแหน่งงาน"],
              ["data-sources", "Postgres ภายนอก"],
              ["api-keys", "API keys"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={cn(
                "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition-colors",
                tab === id
                  ? "border-gemini-accent text-gemini-text dark:text-gemini-dark-text"
                  : "border-transparent text-gemini-muted hover:text-gemini-text"
              )}
            >
              {label}
            </button>
          ))}
        </div>

        {tab === "users" ? (
          <AdminUsersPanel />
        ) : tab === "positions" ? (
          <AdminJobPositionsPanel />
        ) : tab === "data-sources" ? (
          <AdminDataSourcesPanel />
        ) : (
          <AdminApiKeysPanel />
        )}
      </main>
    </>
  );
}
