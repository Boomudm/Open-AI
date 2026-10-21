import {
  DEFAULT_OFFLINE_PREFS,
  OFFLINE_PREFS_KEY,
  type OfflinePrefs,
  resolveCacheMaxBytes,
} from "@/lib/offline/config";
import { idbGet, idbPut } from "@/lib/offline/idb";

const IDB_PREFS_KEY = "user_prefs";

export function loadOfflinePrefsFromLocalStorage(): OfflinePrefs {
  if (typeof window === "undefined") return {};
  try {
    const raw = localStorage.getItem(OFFLINE_PREFS_KEY);
    if (!raw) return {};
    return JSON.parse(raw) as OfflinePrefs;
  } catch {
    return {};
  }
}

export function saveOfflinePrefsToLocalStorage(prefs: OfflinePrefs): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(OFFLINE_PREFS_KEY, JSON.stringify(prefs));
}

export async function getOfflinePrefs(): Promise<OfflinePrefs> {
  const local = loadOfflinePrefsFromLocalStorage();
  try {
    const idb = await idbGet<OfflinePrefs & { key: string }>("offline_prefs", IDB_PREFS_KEY);
    return { ...local, ...idb };
  } catch {
    return local;
  }
}

export async function setOfflinePrefs(patch: Partial<OfflinePrefs>): Promise<OfflinePrefs> {
  const current = await getOfflinePrefs();
  const next = { ...current, ...patch };
  saveOfflinePrefsToLocalStorage(next);
  try {
    await idbPut("offline_prefs", { key: IDB_PREFS_KEY, ...next });
  } catch {
    /* localStorage is enough */
  }
  return next;
}

export async function getCacheMaxBytes(): Promise<number> {
  const prefs = await getOfflinePrefs();
  return resolveCacheMaxBytes(prefs);
}

export function getDefaultPrefetchWifiOnly(): boolean {
  return DEFAULT_OFFLINE_PREFS.prefetchWifiOnly;
}
