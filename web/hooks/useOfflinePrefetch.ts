"use client";

import { cancelPrefetch, prefetchMachineDocuments } from "@/lib/offline/prefetch";
import { useUiStore } from "@/stores/uiStore";
import { useEffect } from "react";

/** Auto-prefetch documents when machine selection changes (Wi-Fi only by default). */
export function useOfflinePrefetch(
  machineId: string | null | undefined,
  options?: { enabled?: boolean }
) {
  const factoryId = useUiStore((s) => s.selectedFactoryId);
  const enabled = options?.enabled ?? true;

  useEffect(() => {
    if (!enabled || !factoryId || !machineId) {
      cancelPrefetch();
      return;
    }
    void prefetchMachineDocuments(factoryId, machineId);
    return () => cancelPrefetch();
  }, [enabled, factoryId, machineId]);
}
