"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

function isPrivateLanHost(host: string): boolean {
  if (host === "localhost" || host === "127.0.0.1") return true;
  // RFC1918 + link-local — typical phone-on-hotspot / LAN dev access
  if (/^10\./.test(host)) return true;
  if (/^192\.168\./.test(host)) return true;
  if (/^172\.(1[6-9]|2\d|3[01])\./.test(host)) return true;
  if (host.startsWith("169.254.")) return true;
  return false;
}

function isLocalDevHost(): boolean {
  if (typeof window === "undefined") return false;
  return isPrivateLanHost(window.location.hostname);
}

export function ServiceWorkerRegister() {
  const pathname = usePathname();

  useEffect(() => {
    if (typeof window === "undefined" || !("serviceWorker" in navigator)) return;
    if (pathname === "/") return;

    // Dev / LAN: unregister stale workers (installed PWA on hotspot must not cache broken shells).
    if (process.env.NODE_ENV === "development" || isLocalDevHost()) {
      void navigator.serviceWorker.getRegistrations().then((regs) => {
        regs.forEach((reg) => void reg.unregister());
      });
      return;
    }

    const cleanups: Array<() => void> = [];

    navigator.serviceWorker
      .register("/sw.js", { scope: "/" })
      .then((reg) => {
        const onUpdateFound = () => {
          const worker = reg.installing;
          if (!worker) return;
          const onStateChange = () => {
            if (worker.state === "installed" && navigator.serviceWorker.controller) {
              worker.postMessage("SKIP_WAITING");
            }
          };
          worker.addEventListener("statechange", onStateChange);
          cleanups.push(() => worker.removeEventListener("statechange", onStateChange));
        };
        reg.addEventListener("updatefound", onUpdateFound);
        cleanups.push(() => reg.removeEventListener("updatefound", onUpdateFound));
      })
      .catch(() => {
        /* optional PWA — ignore registration errors */
      });

    if ("storage" in navigator && "persist" in navigator.storage) {
      void navigator.storage.persist().catch(() => {});
    }

    return () => {
      cleanups.forEach((fn) => fn());
    };
  }, [pathname]);

  return null;
}
