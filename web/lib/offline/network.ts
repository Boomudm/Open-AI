export function isBrowserOnline(): boolean {
  if (typeof navigator === "undefined") return true;
  return navigator.onLine;
}

type NetworkInformation = {
  saveData?: boolean;
  effectiveType?: string;
  type?: string;
};

export function getNetworkInfo(): NetworkInformation | null {
  if (typeof navigator === "undefined") return null;
  return (navigator as Navigator & { connection?: NetworkInformation }).connection ?? null;
}

export function isSaveDataEnabled(): boolean {
  return getNetworkInfo()?.saveData === true;
}

export function isWifiConnection(): boolean {
  const conn = getNetworkInfo();
  if (!conn) return true;
  if (conn.type === "wifi" || conn.type === "ethernet") return true;
  if (conn.type === "cellular" || conn.type === "wimax") return false;
  return conn.effectiveType !== "slow-2g" && conn.effectiveType !== "2g";
}

export function canPrefetchInBackground(prefetchWifiOnly: boolean): boolean {
  if (!isBrowserOnline()) return false;
  if (isSaveDataEnabled()) return false;
  if (prefetchWifiOnly && !isWifiConnection()) return false;
  return true;
}

export function requestIdle(cb: () => void): void {
  if (typeof window === "undefined") {
    cb();
    return;
  }
  if ("requestIdleCallback" in window) {
    window.requestIdleCallback(() => cb(), { timeout: 5000 });
  } else {
    setTimeout(cb, 200);
  }
}
