import type { QueryClient } from "@tanstack/react-query";
import type { UserProfile } from "@/lib/api";
import { PRIVACY_POLICY_VERSION } from "@/lib/privacy-policy";
import { useUiStore } from "@/stores/uiStore";

export const SESSION_EXPIRED_KEY = "spark_session_expired";
/** Break GuestGuard redirect loops when httpOnly cookie cannot be set (installed PWA). */
export const SESSION_REDIRECT_GUARD_KEY = "spark_session_redirect_guard";
export const AUTH_COOKIE_NAME = "spark_token";
/** Query param: force sign-in form and clear any existing session. */
export const SWITCH_ACCOUNT_PARAM = "switch";
/** Query param: resume privacy onboarding without redirecting into the app. */
export const PRIVACY_ONBOARD_PARAM = "onboard";
export const PRIVACY_ONBOARD_VALUE = "privacy";

export const CURRENT_PRIVACY_VERSION = PRIVACY_POLICY_VERSION;

export const ROLE_ADMIN = "admin";
export const ROLE_OPERATOR = "operator";
export const DEV_ROLE_OVERRIDE_KEY = "spark_dev_role_override";

let cachedProfile: UserProfile | null = null;

export function getAuthProfile(): UserProfile | null {
  return cachedProfile;
}

export function setAuthProfile(profile: UserProfile | null): void {
  cachedProfile = profile;
}

function clearAuthProfile(): void {
  cachedProfile = null;
}

/** Load the signed-in user from the server (httpOnly cookie). */
export async function refreshAuthProfile(): Promise<UserProfile | null> {
  if (typeof window === "undefined") return null;
  try {
    const res = await fetch("/api/v1/auth/me", {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
    });
    if (res.status === 401) {
      clearAuthProfile();
      try {
        await fetch("/api/auth/session", { method: "DELETE" });
      } catch {
        /* cookie clear is best-effort */
      }
      return null;
    }
    if (!res.ok) {
      return cachedProfile;
    }
    const profile = (await res.json()) as UserProfile;
    cachedProfile = profile;
    return profile;
  } catch {
    return cachedProfile;
  }
}

export function isAuthenticated(): boolean {
  return cachedProfile !== null;
}

/** API calls rely on the httpOnly session cookie (credentials: same-origin). */
export function authHeaders(): Record<string, string> {
  return {};
}

export function handleUnauthorized(): void {
  if (typeof window === "undefined") return;
  clearAuthProfile();
  sessionStorage.setItem(SESSION_EXPIRED_KEY, "1");
  void fetch("/api/auth/session", { method: "DELETE" });
  window.location.href = "/login";
}

export function consumeSessionExpiredFlag(): boolean {
  if (typeof window === "undefined") return false;
  const expired = sessionStorage.getItem(SESSION_EXPIRED_KEY) === "1";
  if (expired) sessionStorage.removeItem(SESSION_EXPIRED_KEY);
  return expired;
}

export function clearSession(queryClient?: QueryClient): void {
  void logoutSession(queryClient);
}

export async function logoutSession(queryClient?: QueryClient): Promise<void> {
  if (typeof window !== "undefined") {
    clearAuthProfile();
    localStorage.removeItem(DEV_ROLE_OVERRIDE_KEY);
    localStorage.removeItem("spark_factory_id");
    localStorage.removeItem("spark_alert_acks");
    try {
      await fetch("/api/auth/session", { method: "DELETE" });
    } catch {
      /* proceed — local session is already cleared */
    }
  }
  useUiStore.getState().resetSession();
  queryClient?.clear();
}

export function clearSessionRedirectGuard(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(SESSION_REDIRECT_GUARD_KEY);
}

export async function setSessionCookie(token: string): Promise<boolean> {
  try {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    const res = await fetch("/api/auth/session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
      credentials: "same-origin",
      signal: controller.signal,
    });
    clearTimeout(timeout);
    return res.ok;
  } catch {
    return false;
  }
}

export type LoginProfile = {
  email?: string;
  fullName?: string;
  pictureUrl?: string;
};

/** Set httpOnly cookie during post-login onboarding before the app shell loads. */
export async function stageOnboardingSession(token: string, _username: string): Promise<void> {
  clearSessionRedirectGuard();
  const synced = await setSessionCookie(token);
  if (synced) {
    await refreshAuthProfile();
  }
}

export const API_UNREACHABLE_KEY = "spark_api_unreachable";

export function consumeApiUnreachableFlag(): boolean {
  if (typeof window === "undefined") return false;
  const flagged = sessionStorage.getItem(API_UNREACHABLE_KEY) === "1";
  if (flagged) sessionStorage.removeItem(API_UNREACHABLE_KEY);
  return flagged;
}

export function flagApiUnreachable(): void {
  if (typeof window !== "undefined") {
    sessionStorage.setItem(API_UNREACHABLE_KEY, "1");
  }
}

export async function persistLogin(
  token: string,
  _username: string,
  _profile?: LoginProfile
): Promise<boolean> {
  if (typeof window !== "undefined") {
    localStorage.removeItem(DEV_ROLE_OVERRIDE_KEY);
  }
  clearSessionRedirectGuard();
  const synced = await setSessionCookie(token);
  if (!synced) return false;
  await refreshAuthProfile();
  return true;
}

export type AccessLevel = "read" | "write" | "admin";

export function getUsername(): string | null {
  return cachedProfile?.username ?? null;
}

export function getUserEmail(): string | null {
  return cachedProfile?.email?.trim() || null;
}

export function getUserFullName(): string | null {
  return cachedProfile?.full_name?.trim() || null;
}

export function getUserPictureUrl(): string | null {
  return cachedProfile?.picture_url?.trim() || null;
}

export function needsPrivacyAcceptance(): boolean {
  if (!cachedProfile) return false;
  return (cachedProfile.privacy_policy_version ?? "") !== CURRENT_PRIVACY_VERSION;
}

function factoryAccessMap(): Record<string, AccessLevel> {
  const map: Record<string, AccessLevel> = {};
  for (const row of cachedProfile?.factory_access ?? []) {
    map[row.factory_id] = row.access_level as AccessLevel;
  }
  return map;
}

function isAdminFromProfile(): boolean {
  if (!cachedProfile) return false;
  return cachedProfile.roles.includes("admin") || cachedProfile.is_super_admin === true;
}

function isSuperAdminFromProfile(): boolean {
  return cachedProfile?.is_super_admin === true;
}

function isOperatorFromProfile(): boolean {
  if (!cachedProfile) return false;
  if (cachedProfile.roles.includes("operator")) return true;
  const access = factoryAccessMap();
  return Object.values(access).some((l) => l === "write" || l === "admin");
}

export function getEffectiveRole(): typeof ROLE_ADMIN | typeof ROLE_OPERATOR {
  if (typeof window !== "undefined" && process.env.NODE_ENV !== "production") {
    const override = localStorage.getItem(DEV_ROLE_OVERRIDE_KEY);
    if (override === ROLE_OPERATOR || override === ROLE_ADMIN) {
      return override;
    }
  }
  return isAdminFromProfile() ? ROLE_ADMIN : ROLE_OPERATOR;
}

export function isAdminUser(): boolean {
  return getEffectiveRole() === ROLE_ADMIN;
}

/** True admin role from server profile (ignores dev role override). */
export function isProfileAdmin(): boolean {
  return isAdminFromProfile();
}

/** Super admin (God Mode) — server profile only; never dev-overridable. */
export function isSuperAdminUser(): boolean {
  return isSuperAdminFromProfile();
}

export function isOperatorUser(): boolean {
  return getEffectiveRole() === ROLE_OPERATOR;
}

const WORKSPACE_PREFIXES = [
  "/documents",
  "/upload",
  "/feedback",
  "/admin",
  "/system-admin",
  "/machines",
];

const READ_ALLOWED_PREFIXES = ["/chat", "/documents", "/account"];

function pathnameOf(from: string): string {
  try {
    return new URL(from, "http://local").pathname;
  } catch {
    return from.split("?")[0].split("#")[0];
  }
}

/** Same-origin relative path suitable for post-login redirect (?from=). */
export function isSafePostLoginFrom(from: string | null | undefined): from is string {
  if (!from?.trim()) return false;
  let candidate = from.trim();
  try {
    candidate = decodeURIComponent(candidate);
  } catch {
    return false;
  }
  if (!candidate.startsWith("/") || candidate.startsWith("//") || candidate.includes("\\")) {
    return false;
  }
  const lower = candidate.toLowerCase();
  if (lower.includes("javascript:") || lower.includes("data:")) return false;
  return true;
}

function isAllowedPostLoginDestination(from: string): boolean {
  const path = pathnameOf(from);
  if (path === "/login" || path === "/signup" || path.startsWith("/auth/")) return false;
  if (
    (path.startsWith("/admin") || path.startsWith("/system-admin")) &&
    !isAdminUser()
  ) {
    return false;
  }
  if (
    READ_ALLOWED_PREFIXES.some(
      (prefix) => path === prefix || path.startsWith(`${prefix}/`)
    )
  ) {
    return true;
  }
  const isWorkspace = WORKSPACE_PREFIXES.some(
    (prefix) => path === prefix || path.startsWith(`${prefix}/`)
  );
  if (isWorkspace && !canWriteFactory(null)) return false;
  return true;
}

/** Default home after login, or validated deep-link target from ?from=. */
export function resolvePostLoginPath(from?: string | null): string {
  const fallback = "/chat";
  if (!isSafePostLoginFrom(from)) return fallback;
  let candidate = from.trim();
  try {
    candidate = decodeURIComponent(candidate);
  } catch {
    return fallback;
  }
  if (!isAllowedPostLoginDestination(candidate)) return fallback;
  return candidate;
}

export function getPostLoginPath(from?: string | null): string {
  return resolvePostLoginPath(from);
}

export function toggleDevRoleOverride(): typeof ROLE_ADMIN | typeof ROLE_OPERATOR {
  const next = isAdminUser() ? ROLE_OPERATOR : ROLE_ADMIN;
  if (typeof window !== "undefined") {
    localStorage.setItem(DEV_ROLE_OVERRIDE_KEY, next);
  }
  return next;
}

export function canWriteFactory(factoryId?: string | null): boolean {
  if (!cachedProfile) return false;
  if (cachedProfile.is_super_admin) return true;
  if (cachedProfile.roles.includes("admin")) return true;
  if (cachedProfile.roles.includes("operator")) return true;
  const access = factoryAccessMap();
  const order: Record<AccessLevel, number> = { read: 0, write: 1, admin: 2 };
  if (factoryId) {
    const grant = access[factoryId];
    return grant ? order[grant] >= order["write"] : false;
  }
  return Object.values(access).some((l) => order[l] >= order["write"]);
}

/** Document upload: admin, operator, or factory write grant (not read-only employees). */
export function canUploadDocuments(factoryId?: string | null): boolean {
  return canWriteFactory(factoryId);
}

export function canAccessFactory(
  factoryId?: string | null,
  level: AccessLevel = "read"
): boolean {
  if (!cachedProfile) return false;
  if (cachedProfile.is_super_admin) return true;
  if (cachedProfile.roles.includes("admin")) return true;
  const access = factoryAccessMap();
  const order: Record<AccessLevel, number> = { read: 0, write: 1, admin: 2 };
  if (factoryId) {
    const grant = access[factoryId];
    return grant ? order[grant] >= order[level] : false;
  }
  return Object.values(access).some((l) => order[l] >= order[level]);
}

export function getAccessibleFactoryIds(): string[] {
  if (!cachedProfile) return [];
  if (cachedProfile.is_super_admin) return [];
  if (cachedProfile.roles.includes("admin")) return [];
  return cachedProfile.factory_access.map((row) => row.factory_id);
}

export function getJobPositionIds(): string[] {
  return cachedProfile?.job_positions.map((p) => p.position_id) ?? [];
}

export function hasNoJobPositionAssigned(): boolean {
  return isAuthenticated() && !isAdminUser() && getJobPositionIds().length === 0;
}

export function roleDisplayLabel(role: string): string {
  switch (role) {
    case "admin":
      return "ผู้ดูแลระบบ";
    case "operator":
      return "Operator";
    case "employee":
      return "พนักงาน";
    default:
      return role;
  }
}

export function canAccessIngest(): boolean {
  return canUploadDocuments(null);
}
