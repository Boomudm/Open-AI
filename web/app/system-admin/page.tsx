import { SystemAdminDashboardView } from "@/components/system-admin/SystemAdminDashboardView";
import { Suspense } from "react";

export default function SystemAdminPage() {
  return (
    <Suspense
      fallback={
        <div className="noc-root flex h-[100dvh] items-center justify-center text-slate-400">
          Loading control room…
        </div>
      }
    >
      <SystemAdminDashboardView />
    </Suspense>
  );
}
