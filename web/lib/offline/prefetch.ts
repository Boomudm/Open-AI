import { api } from "@/lib/api";
import type { IndexedDocument } from "@/lib/api";
import { DEFAULT_OFFLINE_PREFS } from "@/lib/offline/config";
import { putCachedDocument, listCachedDocuments } from "@/lib/offline/document-cache";
import { prefetchScore, shouldPrefetchDocument } from "@/lib/offline/lru";
import { getDocumentsForMachine, saveDocumentMeta } from "@/lib/offline/meta-cache";
import { canPrefetchInBackground, requestIdle } from "@/lib/offline/network";
import { getOfflinePrefs } from "@/lib/offline/prefs";

let prefetchToken = 0;

export async function prefetchMachineDocuments(
  factoryId: string,
  machineId: string
): Promise<void> {
  const prefs = await getOfflinePrefs();
  const wifiOnly = prefs.prefetchWifiOnly ?? DEFAULT_OFFLINE_PREFS.prefetchWifiOnly;
  if (!canPrefetchInBackground(wifiOnly)) return;

  const token = ++prefetchToken;

  requestIdle(async () => {
    if (token !== prefetchToken) return;

    let docs: IndexedDocument[] = [];
    try {
      docs = await api.fetchAllDocuments(
        { factory_id: factoryId, machine_id: machineId },
        { pageSize: 100, maxItems: 200 }
      );
      await saveDocumentMeta(factoryId, docs);
    } catch {
      docs = await getDocumentsForMachine(factoryId, machineId);
    }

    const cached = await listCachedDocuments();
    const accessMap = new Map(cached.map((r) => [r.doc_id, r.access_count]));

    const candidates = docs
      .filter(shouldPrefetchDocument)
      .map((d) => ({
        doc: d,
        score: prefetchScore(d, accessMap.get(d.doc_id) ?? 0),
      }))
      .sort((a, b) => b.score - a.score)
      .slice(0, DEFAULT_OFFLINE_PREFS.prefetchPerMachine);

    for (const { doc } of candidates) {
      if (token !== prefetchToken) return;
      const existing = cached.find((r) => r.doc_id === doc.doc_id);
      if (
        existing?.file_hash_sha256 &&
        doc.file_hash_sha256 &&
        existing.file_hash_sha256 === doc.file_hash_sha256
      ) {
        continue;
      }
      try {
        const blob = await api.getDocumentFile(doc.doc_id, "inline");
        await putCachedDocument({
          doc_id: doc.doc_id,
          blob,
          mime_type: blob.type || doc.mime_type || "application/pdf",
          file_hash_sha256: doc.file_hash_sha256,
          factory_id: doc.factory_id,
          machine_id: doc.machine_id,
        });
      } catch {
        /* skip failed prefetch */
      }
      await new Promise((r) => setTimeout(r, 300));
    }
  });
}

export function cancelPrefetch(): void {
  prefetchToken++;
}
