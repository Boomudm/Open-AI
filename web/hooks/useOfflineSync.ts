"use client";

import {
  getSyncStatusSnapshot,
  startSyncManager,
  subscribeSyncStatus,
  syncOfflineData,
} from "@/lib/offline/sync-manager";
import type { SyncStatus } from "@/lib/offline/types";
import { useUiStore } from "@/stores/uiStore";
import { useCallback, useEffect, useState } from "react";

const EMPTY: SyncStatus = {
  online: true,
  syncing: false,
  pendingFeedback: 0,
  cachedDocsCount: 0,
  cachedBytes: 0,
  cacheMaxBytes: 157_286_400,
  lastSyncAt: null,
};

export function useOfflineSync() {
  const factoryId = useUiStore((s) => s.selectedFactoryId);
  const [status, setStatus] = useState<SyncStatus>(EMPTY);

  useEffect(() => {
    const unsub = subscribeSyncStatus((s) => setStatus((prev) => ({ ...prev, ...s })));
    void getSyncStatusSnapshot().then(setStatus);
    const stop = startSyncManager(factoryId);
    return () => {
      unsub();
      stop();
    };
  }, [factoryId]);

  const triggerSync = useCallback(() => {
    void syncOfflineData(factoryId);
  }, [factoryId]);

  return { status, triggerSync };
}
