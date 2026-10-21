"use client";

import { LoadingState } from "@/components/ui/State";
import { canWriteFactory, isAuthenticated } from "@/lib/auth";
import { useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

/** Restricts workspace routes to admin / operator / factory write users. */
export function WriteGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [access, setAccess] = useState<"checking" | "allowed" | "denied">("checking");

  useEffect(() => {
    if (isAuthenticated() && canWriteFactory(null)) {
      setAccess("allowed");
      return;
    }
    setAccess("denied");
    router.replace("/chat");
  }, [router]);

  if (access !== "allowed") {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gemini-bg dark:bg-gemini-dark-bg">
        <LoadingState
          message={
            access === "denied"
              ? "คุณไม่มีสิทธิ์เข้าถึงพื้นที่งานนี้ — กำลังไปที่แชท…"
              : "กำลังตรวจสอบสิทธิ์…"
          }
        />
      </div>
    );
  }

  return <>{children}</>;
}
