import { api } from "@/lib/api";
import {
  clearDocumentCache,
  getCachedStorageStats,
} from "@/lib/offline/document-cache";
import {
  countPendingFeedback,
  feedbackToFormData,
  listPendingFeedback,
  markFeedbackFailed,
  markFeedbackSent,
} from "@/lib/offline/feedback-outbox";
import { saveDocumentMeta, saveMachineMeta } from "@/lib/offline/meta-cache";
import { isBrowserOnline } from "@/lib/offline/network";
import { getCacheMaxBytes } from "@/lib/offline/prefs";
import type { SyncStatus } from "@/lib/offline/types";

type SyncListener = (status: Partial<SyncStatus>) => void;

let syncing = false;
let lastSyncAt: string | null = null;
const listeners = new Set<SyncListener>();

export function subscribeSyncStatus(listener: SyncListener): () => void {
  listeners.add(listener);
  void emitStatus();
  return () => listeners.delete(listener);
}

async function emitStatus(extra?: Partial<SyncStatus>): Promise<void> {
  const stats = await getCachedStorageStats();
  const pending = await countPendingFeedback();
  const status: SyncStatus = {
    online: isBrowserOnline(),
    syncing,
    pendingFeedback: pending,
    cachedDocsCount: stats.count,
    cachedBytes: stats.bytes,
    cacheMaxBytes: await getCacheMaxBytes(),
    lastSyncAt,
    ...extra,
  };
  listeners.forEach((l) => l(status));
}

export async function syncOfflineData(factoryId: string | null): Promise<void> {
  if (!isBrowserOnline() || syncing || !factoryId) return;
  syncing = true;
  await emitStatus();

  try {
    await flushFeedbackOutbox();

    if (factoryId) {
      try {
        const docs = await api.fetchAllDocuments({ factory_id: factoryId }, { maxItems: 500 });
        await saveDocumentMeta(factoryId, docs);
      } catch {
        /* keep cached meta */
      }
      try {
        const machines = await api.machines({ factory_id: factoryId, page_size: 200 });
        await saveMachineMeta(factoryId, machines.items);
      } catch {
        /* keep cached meta */
      }
    }

    lastSyncAt = new Date().toISOString();
  } finally {
    syncing = false;
    await emitStatus();
  }
}

async function flushFeedbackOutbox(): Promise<number> {
  const pending = await listPendingFeedback();
  let sent = 0;
  for (const row of pending) {
    try {
      const form = feedbackToFormData(row);
      form.set("comment", row.comment);
      if (row.issue_type) form.set("issue_type", row.issue_type);
      await api.submitFeedback(form);
      await markFeedbackSent(row.local_id);
      sent++;
    } catch (e) {
      const msg = e instanceof Error ? e.message : "sync failed";
      await markFeedbackFailed(row.local_id, msg);
    }
  }
  return sent;
}

export async function clearAllOfflineCache(): Promise<void> {
  await clearDocumentCache();
  await emitStatus();
}

let syncInterval: ReturnType<typeof setInterval> | null = null;

export function startSyncManager(factoryId: string | null): () => void {
  if (typeof window === "undefined") return () => {};

  const onOnline = () => {
    void syncOfflineData(factoryId);
  };

  const onVisible = () => {
    if (document.visibilityState === "visible" && isBrowserOnline()) {
      void syncOfflineData(factoryId);
    }
  };

  window.addEventListener("online", onOnline);
  document.addEventListener("visibilitychange", onVisible);

  if (isBrowserOnline()) {
    void syncOfflineData(factoryId);
  }

  syncInterval = setInterval(() => {
    if (isBrowserOnline()) void syncOfflineData(factoryId);
  }, 60_000);

  return () => {
    window.removeEventListener("online", onOnline);
    document.removeEventListener("visibilitychange", onVisible);
    if (syncInterval) clearInterval(syncInterval);
    syncInterval = null;
  };
}

export async function getSyncStatusSnapshot(): Promise<SyncStatus> {
  const stats = await getCachedStorageStats();
  return {
    online: isBrowserOnline(),
    syncing,
    pendingFeedback: await countPendingFeedback(),
    cachedDocsCount: stats.count,
    cachedBytes: stats.bytes,
    cacheMaxBytes: await getCacheMaxBytes(),
    lastSyncAt,
  };
}
