"use client";

import {
  PRIVACY_ONBOARD_PARAM,
  PRIVACY_ONBOARD_VALUE,
  SESSION_REDIRECT_GUARD_KEY,
  SWITCH_ACCOUNT_PARAM,
  clearSessionRedirectGuard,
  flagApiUnreachable,
  getPostLoginPath,
  logoutSession,
  refreshAuthProfile,
} from "@/lib/auth";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState, type ReactNode } from "react";
import { useQueryClient } from "@tanstack/react-query";

function GuestGuardInner({ children }: { children: ReactNode }) {
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [checking, setChecking] = useState(true);

  const switchingAccount = searchParams.get(SWITCH_ACCOUNT_PARAM) === "1";
  const privacyOnboarding =
    searchParams.get(PRIVACY_ONBOARD_PARAM) === PRIVACY_ONBOARD_VALUE;
  const fromPath = searchParams.get("from");

  useEffect(() => {
    let cancelled = false;

    async function init() {
      if (switchingAccount) {
        clearSessionRedirectGuard();
        await logoutSession(queryClient);
        if (!cancelled) setChecking(false);
        return;
      }

      if (privacyOnboarding) {
        if (!cancelled) setChecking(false);
        return;
      }

      const profile = await refreshAuthProfile();
      const redirectGuard = sessionStorage.getItem(SESSION_REDIRECT_GUARD_KEY);
      if (!cancelled && profile && !redirectGuard) {
        sessionStorage.setItem(SESSION_REDIRECT_GUARD_KEY, "1");
        const dest = getPostLoginPath(fromPath);
        window.location.assign(dest);
        return;
      }
      if (!cancelled && profile && redirectGuard) {
        clearSessionRedirectGuard();
      }
      if (!cancelled && !profile) {
        clearSessionRedirectGuard();
      }
      if (!cancelled) setChecking(false);
    }

    void init();
    return () => {
      cancelled = true;
    };
  }, [switchingAccount, privacyOnboarding, fromPath, queryClient]);

  return <div aria-busy={checking}>{children}</div>;
}

export function GuestGuard({ children }: { children: ReactNode }) {
  return (
    <Suspense fallback={children}>
      <GuestGuardInner>{children}</GuestGuardInner>
    </Suspense>
  );
}
