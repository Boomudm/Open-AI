import type { LoginResponse } from "@/lib/api";
import { useUiStore } from "@/stores/uiStore";

const DEFAULT_FACTORY_ID = "F-01";

function parseRolesFromToken(token: string): string[] {
  try {
    const payload = token.split(".")[1];
    if (!payload) return [];
    const normalized = payload.replace(/-/g, "+").replace(/_/g, "/");
    const claims = JSON.parse(atob(normalized)) as { roles?: string[] };
    return claims.roles ?? [];
  } catch {
    return [];
  }
}

export function isAdminLogin(
  data: Pick<LoginResponse, "token" | "is_super_admin">,
): boolean {
  if (data.is_super_admin) return true;
  return parseRolesFromToken(data.token).includes("admin");
}

/** Non-admin users pick a factory after login (including single-site employees). */
export function shouldShowFactoryStep(data: LoginResponse): boolean {
  return data.factories.length > 0 && !isAdminLogin(data);
}

/** Factory to use when skipping the picker (admin, single-factory, or post-selection). */
export function resolveDefaultFactoryId(data: LoginResponse): string | null {
  if (data.factories.length === 0) return null;
  if (data.factories.length === 1) {
    return data.factories[0].factory_id;
  }

  const persisted = useUiStore.getState().selectedFactoryId;
  if (persisted && data.factories.some((f) => f.factory_id === persisted)) {
    return persisted;
  }

  const preferred = data.factories.find((f) => f.factory_id === DEFAULT_FACTORY_ID);
  if (preferred) return preferred.factory_id;

  return data.factories[0]?.factory_id ?? null;
}
