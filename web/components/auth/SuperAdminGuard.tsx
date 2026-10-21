"use client";

import { LoadingState } from "@/components/ui/State";
import { isAdminUser } from "@/lib/auth";
import { api } from "@/lib/api";
import { queryKeys } from "@/lib/query-keys";
import { STALE_STATIC } from "@/lib/query-config";
import { useQuery } from "@tanstack/react-query";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

/** Restricts control-room routes to admin / super-admin users. */
export function SuperAdminGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { data: profile, isLoading, isError } = useQuery({
    queryKey: queryKeys.myProfile(),
    queryFn: () => api.getMyProfile(),
    staleTime: STALE_STATIC,
    retry: false,
  });

  const allowed =
    isAdminUser() ||
    Boolean(profile?.roles?.includes("admin")) ||
    Boolean(profile?.is_super_admin);

  useEffect(() => {
    if (isLoading) return;
    if (isError || !allowed) {
      router.replace("/chat");
    }
  }, [allowed, isError, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#0a0e14]">
        <LoadingState message="กำลังตรวจสอบสิทธิ์ผู้ดูแลระบบ…" />
      </div>
    );
  }

  if (!allowed) {
    return null;
  }

  return <>{children}</>;
}
