import { pickEvictionCandidates } from "@/lib/offline/lru";
import { idbDelete, idbGet, idbGetAll, idbPut } from "@/lib/offline/idb";
import { getCacheMaxBytes } from "@/lib/offline/prefs";
import type { CachedDocumentRecord } from "@/lib/offline/types";

export async function getCachedDocument(
  docId: string
): Promise<CachedDocumentRecord | undefined> {
  try {
    const row = await idbGet<CachedDocumentRecord>("document_blobs", docId);
    if (!row?.blob) return undefined;
    const now = new Date().toISOString();
    const updated: CachedDocumentRecord = {
      ...row,
      last_accessed_at: now,
      access_count: (row.access_count ?? 0) + 1,
    };
    await idbPut("document_blobs", updated);
    return updated;
  } catch {
    return undefined;
  }
}

export async function hasCachedDocument(docId: string): Promise<boolean> {
  try {
    const row = await idbGet<CachedDocumentRecord>("document_blobs", docId);
    return Boolean(row?.blob);
  } catch {
    return false;
  }
}

export async function putCachedDocument(input: {
  doc_id: string;
  blob: Blob;
  mime_type: string;
  file_hash_sha256?: string | null;
  factory_id?: string | null;
  machine_id?: string | null;
}): Promise<void> {
  const records = await listCachedDocuments();
  const maxBytes = await getCacheMaxBytes();
  const existing = records.find((r) => r.doc_id === input.doc_id);
  const fileSize = input.blob.size;
  const currentTotal = records.reduce((sum, r) => sum + r.file_size_bytes, 0);
  const adjustedTotal = existing
    ? currentTotal - existing.file_size_bytes
    : currentTotal;

  const evictIds = pickEvictionCandidates(
    records.filter((r) => r.doc_id !== input.doc_id),
    adjustedTotal,
    maxBytes,
    fileSize
  );
  for (const id of evictIds) {
    await idbDelete("document_blobs", id);
  }

  const now = new Date().toISOString();
  const record: CachedDocumentRecord = {
    doc_id: input.doc_id,
    blob: input.blob,
    mime_type: input.mime_type || input.blob.type || "application/octet-stream",
    file_hash_sha256: input.file_hash_sha256 ?? null,
    file_size_bytes: fileSize,
    factory_id: input.factory_id ?? null,
    machine_id: input.machine_id ?? null,
    cached_at: existing?.cached_at ?? now,
    last_accessed_at: now,
    access_count: (existing?.access_count ?? 0) + 1,
  };
  await idbPut("document_blobs", record);
}

export async function listCachedDocuments(): Promise<CachedDocumentRecord[]> {
  try {
    return await idbGetAll<CachedDocumentRecord>("document_blobs");
  } catch {
    return [];
  }
}

export async function getCachedStorageStats(): Promise<{
  count: number;
  bytes: number;
}> {
  const rows = await listCachedDocuments();
  return {
    count: rows.length,
    bytes: rows.reduce((sum, r) => sum + r.file_size_bytes, 0),
  };
}

export async function isCachedDocumentStale(
  docId: string,
  serverHash: string | null | undefined
): Promise<boolean> {
  if (!serverHash) return false;
  try {
    const row = await idbGet<CachedDocumentRecord>("document_blobs", docId);
    if (!row) return false;
    return row.file_hash_sha256 !== serverHash;
  } catch {
    return false;
  }
}

export async function removeCachedDocument(docId: string): Promise<void> {
  try {
    await idbDelete("document_blobs", docId);
  } catch {
    /* ignore */
  }
}

export async function clearDocumentCache(): Promise<void> {
  const rows = await listCachedDocuments();
  await Promise.all(rows.map((r) => idbDelete("document_blobs", r.doc_id)));
}
