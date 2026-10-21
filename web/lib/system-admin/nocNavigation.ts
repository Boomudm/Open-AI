const RETURN_PATH_KEY = "spark_system_admin_return";

/** Remember where the user came from before opening the control room. */
export function rememberSystemAdminReturnPath(path?: string | null): void {
  if (typeof window === "undefined") return;
  const candidate = (path || window.location.pathname + window.location.search).trim();
  if (!candidate.startsWith("/") || candidate.startsWith("/system-admin")) return;
  try {
    sessionStorage.setItem(RETURN_PATH_KEY, candidate);
  } catch {
    /* ignore quota / private mode */
  }
}

export function getSystemAdminReturnPath(fallback = "/chat"): string {
  if (typeof window === "undefined") return fallback;
  try {
    const stored = sessionStorage.getItem(RETURN_PATH_KEY);
    if (stored?.startsWith("/") && !stored.startsWith("/system-admin")) {
      return stored;
    }
  } catch {
    /* ignore */
  }
  return fallback;
}

export function clearSystemAdminReturnPath(): void {
  if (typeof window === "undefined") return;
  try {
    sessionStorage.removeItem(RETURN_PATH_KEY);
  } catch {
    /* ignore */
  }
}
