"use client";

import { AdminFactoriesPanel } from "@/components/admin/AdminFactoriesPanel";
import { LoadingState } from "@/components/ui/State";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { STALE_STATIC } from "@/lib/query-config";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

export default function AdminFactoriesPage() {
  const router = useRouter();
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
            จัดการโรงงาน
          </h1>
          <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
            เพิ่มโรงงานใหม่และดูรายการโรงงานทั้งหมดในระบบ
          </p>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-4 py-6">
        <AdminFactoriesPanel />
      </main>
    </>
  );
}
