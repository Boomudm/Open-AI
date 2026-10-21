"use client";

import { LoadingState } from "@/components/ui/State";
import { useEffect, useState, type ReactNode } from "react";

/** Chat requires sign-in; profile is loaded by AuthGuard before this mounts. */
export function ChatGuard({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setReady(true);
  }, []);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gemini-bg dark:bg-gemini-dark-bg">
        <LoadingState message="กำลังโหลด…" />
      </div>
    );
  }

  return <>{children}</>;
}
