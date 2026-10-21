"use client";

import { LoadingState } from "@/components/ui/State";
import { AuthLayout } from "@/components/auth/AuthLayout";
import { getPostLoginPath, logoutSession, persistLogin } from "@/lib/auth";
import { exchangeOAuthCode, storeOAuthLogin } from "@/lib/googleAuth";
import { useUiStore } from "@/stores/uiStore";
import { useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect } from "react";

function AuthCallbackInner() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();

  useEffect(() => {
    const error = searchParams.get("error");
    if (error) {
      const message = searchParams.get("message");
      router.replace(
        `/login?error=${encodeURIComponent(error)}${message ? `&message=${encodeURIComponent(message)}` : ""}`
      );
      return;
    }

    const code = searchParams.get("code");
    if (!code) {
      router.replace("/login?error=oauth_failed");
      return;
    }

    void (async () => {
      const fromPath = searchParams.get("from");
      const loginWithFrom = (path: string) => {
        const url = new URL(path, window.location.origin);
        if (fromPath) url.searchParams.set("from", fromPath);
        router.replace(`${url.pathname}${url.search}`);
      };

      try {
        const payload = await exchangeOAuthCode(code);
        await logoutSession(queryClient);
        useUiStore.getState().resetSession();
        queryClient.clear();

        if (
          payload.factories.length > 1 ||
          payload.needs_privacy_acceptance ||
          payload.needs_job_position
        ) {
          storeOAuthLogin({
            token: payload.token,
            username: payload.username,
            email: payload.email,
            fullName: payload.fullName,
            pictureUrl: payload.pictureUrl,
            factories: payload.factories,
            needs_job_position: payload.needs_job_position,
            needs_privacy_acceptance: payload.needs_privacy_acceptance,
            is_super_admin: payload.is_super_admin,
          });
          loginWithFrom("/login?oauth=1");
          return;
        }

        await persistLogin(payload.token, payload.username, {
          email: payload.email,
          fullName: payload.fullName,
          pictureUrl: payload.pictureUrl,
        });
        router.replace(getPostLoginPath(fromPath));
      } catch {
        router.replace("/login?error=oauth_failed");
      }
    })();
  }, [router, searchParams, queryClient]);

  return (
    <AuthLayout>
      <LoadingState message="Completing Google sign-in…" />
    </AuthLayout>
  );
}

export default function AuthCallbackPage() {
  return (
    <Suspense
      fallback={
        <AuthLayout>
          <LoadingState message="Loading…" />
        </AuthLayout>
      }
    >
      <AuthCallbackInner />
    </Suspense>
  );
}
