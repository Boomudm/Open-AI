"use client";

import { AuthGuard } from "@/components/auth/AuthGuard";
import { WriteGuard } from "@/components/auth/WriteGuard";
import { WorkspaceShell } from "@/components/workspace/WorkspaceShell";
import { ToastProvider } from "@/components/ui/Toast";

function WorkspaceShellLayout({ children }: { children: React.ReactNode }) {
  return (
    <ToastProvider>
      <WorkspaceShell>{children}</WorkspaceShell>
    </ToastProvider>
  );
}

/** Operator/admin workspace — requires write access. */
export function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <WriteGuard>
        <WorkspaceShellLayout>{children}</WorkspaceShellLayout>
      </WriteGuard>
    </AuthGuard>
  );
}

/** Read-only workspace — documents, repairs, inventory for all authenticated users. */
export function ReadWorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <WorkspaceShellLayout>{children}</WorkspaceShellLayout>
    </AuthGuard>
  );
}
