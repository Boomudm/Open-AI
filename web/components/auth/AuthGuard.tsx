"use client";

import { ErrorState, LoadingState } from "@/components/ui/State";
import { cn } from "@/lib/cn";
import { useAuthProfile } from "@/hooks/useAuthProfile";
import { useCallback, useEffect, useState, type ReactNode } from "react";

type AuthState = "loading" | "ready" | "slow" | "redirecting";

export function AuthGuard({ children }: { children: ReactNode }) {
  const { profile, isLoading, isFetching, isFetched, isError, refetch, needsPrivacy } =
    useAuthProfile();
  const [state, setState] = useState<AuthState>("loading");
  const [retrying, setRetrying] = useState(false);

  const redirectToLogin = useCallback(() => {
    setState("redirecting");
    const from =
      typeof window !== "undefined"
        ? encodeURIComponent(window.location.pathname + window.location.search)
        : "";
    void (async () => {
      try {
        await fetch("/api/auth/session", { method: "DELETE" });
      } catch {
        /* proceed to login even if cookie clear fails */
      }
      const base = from ? `/login?switch=1&from=${from}` : "/login?switch=1";
      window.location.replace(base);
    })();
  }, []);

  useEffect(() => {
    if (profile) {
      if (needsPrivacy) {
        setState("redirecting");
        window.location.replace("/login?onboard=privacy");
        return;
      }
      setState("ready");
      return;
    }

    if (!isFetched || isLoading || isFetching) {
      setState((prev) => (prev === "ready" ? prev : "loading"));
      const slowTimer = window.setTimeout(() => {
        setState((s) => (s === "loading" ? "slow" : s));
      }, 4000);
      return () => window.clearTimeout(slowTimer);
    }

    redirectToLogin();
  }, [profile, isFetched, isLoading, isFetching, needsPrivacy, redirectToLogin]);

  const handleRetry = useCallback(async () => {
    setRetrying(true);
    setState("loading");
    const result = await refetch();
    setRetrying(false);
    if (result.error || !result.data) {
      setState(isError ? "slow" : "loading");
    }
  }, [refetch, isError]);

  if (state === "ready") {
    return <>{children}</>;
  }

  if (state === "slow") {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-4 bg-gemini-sidebar dark:bg-gemini-dark-bg gemini-theme-transition px-4">
        <LoadingState message="เชื่อมต่อช้า — กำลังตรวจสอบเซสชัน…" />
        <div className="flex flex-wrap items-center justify-center gap-3">
          <button
            type="button"
            disabled={retrying}
            onClick={() => void handleRetry()}
            className={cn(
              "px-4 py-2 rounded-lg text-sm font-medium",
              "bg-gemini-blue dark:bg-gemini-dark-blue text-white",
              "hover:opacity-90 disabled:opacity-50 gemini-focus-ring"
            )}
          >
            {retrying ? "กำลังลองใหม่…" : "ลองอีกครั้ง"}
          </button>
          <button
            type="button"
            onClick={redirectToLogin}
            className="px-4 py-2 rounded-lg text-sm text-gemini-muted hover:text-gemini-text gemini-focus-ring"
          >
            ไปหน้าเข้าสู่ระบบ
          </button>
        </div>
        {isError && (
          <ErrorState
            title="ไม่สามารถโหลดโปรไฟล์ได้"
            message="ตรวจสอบการเชื่อมต่อเครือข่ายแล้วลองอีกครั้ง"
            onRetry={() => void handleRetry()}
            className="w-full max-w-md border-0 bg-transparent"
          />
        )}
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gemini-sidebar dark:bg-gemini-dark-bg gemini-theme-transition">
      <LoadingState message="กำลังตรวจสอบเซสชัน…" />
    </div>
  );
}
