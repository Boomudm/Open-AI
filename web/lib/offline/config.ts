/** Client-side offline cache defaults (PWA-friendly). */

export const OFFLINE_PREFS_KEY = "spark_offline_prefs";

export const DEFAULT_OFFLINE_PREFS = {
  cacheMaxBytesMobile: 157_286_400, // 150 MB
  cacheMaxBytesTablet: 314_572_800, // 300 MB
  prefetchPerMachine: 5,
  maxPrefetchFileBytes: 20_971_520, // 20 MB
  prefetchWifiOnly: true,
  metaMaxAgeHours: 168,
} as const;

export type OfflinePrefs = {
  cacheMaxBytes?: number;
  prefetchWifiOnly?: boolean;
  isTablet?: boolean;
};

export const PREFETCH_PRIORITY_TYPES = [
  "machine_manual",
  "sop",
  "training_note",
  "drawing",
  "datasheet",
] as const;

export function resolveCacheMaxBytes(prefs: OfflinePrefs): number {
  if (prefs.cacheMaxBytes && prefs.cacheMaxBytes > 0) return prefs.cacheMaxBytes;
  return prefs.isTablet
    ? DEFAULT_OFFLINE_PREFS.cacheMaxBytesTablet
    : DEFAULT_OFFLINE_PREFS.cacheMaxBytesMobile;
}
