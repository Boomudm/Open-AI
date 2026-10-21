import { logoutSession } from "@/lib/auth";

/** Google OAuth starts through the same-origin Next proxy to avoid browser-side 127.0.0.1/env drift. */
export const GOOGLE_LOGIN_PATH = "/api/v1/auth/google/login";

/** Clear any local session so Google account choice maps to a fresh Neo Chat login. */
export async function startGoogleSignIn(from?: string | null): Promise<void> {
  await logoutSession();
  const url = new URL(GOOGLE_LOGIN_PATH, window.location.origin);
  if (from?.trim()) {
    url.searchParams.set("from", from.trim());
  }
  window.location.assign(url.toString());
}

const OAUTH_ERROR_MESSAGES: Record<string, string> = {
  google_denied: "Google sign-in was cancelled.",
  not_configured: "Google sign-in is not configured on the server.",
  oauth_failed: "Google sign-in failed. Please try again.",
  invalid_state: "Sign-in session expired. Please try again.",
  google_token_failed: "Could not verify your Google account.",
  no_email: "Your Google account has no email address.",
  email_not_verified: "Your Google email address is not verified.",
  account_inactive: "This account has been deactivated. Contact your administrator.",
  signup_failed: "Could not create your account. Please try again.",
  account_conflict: "This Google account cannot be linked to your profile. Contact support.",
  domain_not_allowed:
    "Your email domain is not authorized for this plant. Use your company Google account.",
  not_linked:
    "No Neo Chat account is linked to this Google email. Contact your plant administrator.",
};

export function oauthErrorMessage(code: string, fallback?: string | null): string {
  return OAUTH_ERROR_MESSAGES[code] ?? fallback ?? "Google sign-in failed.";
}

export const OAUTH_SESSION_KEY = "spark_oauth_login";

export type OAuthLoginPayload = {
  token: string;
  username: string;
  email?: string;
  fullName?: string;
  pictureUrl?: string;
  factories: Array<{ factory_id: string; factory_name: string }>;
  needs_job_position?: boolean;
  needs_privacy_acceptance?: boolean;
  is_super_admin?: boolean;
};

export function storeOAuthLogin(payload: OAuthLoginPayload): void {
  sessionStorage.setItem(OAUTH_SESSION_KEY, JSON.stringify(payload));
}

export function consumeOAuthLogin(): OAuthLoginPayload | null {
  const raw = sessionStorage.getItem(OAUTH_SESSION_KEY);
  sessionStorage.removeItem(OAUTH_SESSION_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as OAuthLoginPayload;
  } catch {
    return null;
  }
}

export async function exchangeOAuthCode(code: string): Promise<OAuthLoginPayload> {
  const res = await fetch("/api/v1/auth/oauth/exchange", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ code }),
  });
  if (!res.ok) {
    throw new Error("oauth_exchange_failed");
  }
  const data = (await res.json()) as {
    token: string;
    username: string;
    email?: string;
    full_name?: string;
    picture_url?: string;
    factories: OAuthLoginPayload["factories"];
    needs_job_position?: boolean;
    needs_privacy_acceptance?: boolean;
    is_super_admin?: boolean;
  };
  return {
    token: data.token,
    username: data.username,
    email: data.email,
    fullName: data.full_name,
    pictureUrl: data.picture_url,
    factories: data.factories ?? [],
    needs_job_position: Boolean(data.needs_job_position),
    needs_privacy_acceptance: Boolean(data.needs_privacy_acceptance),
    is_super_admin: Boolean(data.is_super_admin),
  };
}
