import type { CachedDocumentRecord } from "@/lib/offline/types";

/** Pure LRU eviction — returns doc_ids to delete until under quota. */
export function pickEvictionCandidates(
  records: Pick<CachedDocumentRecord, "doc_id" | "file_size_bytes" | "last_accessed_at" | "access_count">[],
  currentTotalBytes: number,
  maxBytes: number,
  incomingBytes = 0
): string[] {
  if (currentTotalBytes + incomingBytes <= maxBytes) return [];

  const sorted = [...records].sort((a, b) => {
    if (a.access_count !== b.access_count) return a.access_count - b.access_count;
    return new Date(a.last_accessed_at).getTime() - new Date(b.last_accessed_at).getTime();
  });

  const toEvict: string[] = [];
  let total = currentTotalBytes + incomingBytes;

  for (const row of sorted) {
    if (total <= maxBytes) break;
    toEvict.push(row.doc_id);
    total -= row.file_size_bytes;
  }

  return toEvict;
}

export function shouldPrefetchDocument(meta: {
  ingest_status: string;
  file_size_bytes?: number | null;
  document_type: string;
}): boolean {
  if (meta.ingest_status !== "completed") return false;
  if (meta.file_size_bytes != null && meta.file_size_bytes > 20_971_520) return false;
  return true;
}

export function prefetchScore(
  doc: { document_type: string; file_size_bytes?: number | null },
  accessCount: number
): number {
  let score = accessCount * 100;
  const typeIdx = ["machine_manual", "sop", "training_note", "drawing", "datasheet"].indexOf(
    doc.document_type
  );
  if (typeIdx >= 0) score += (5 - typeIdx) * 10;
  if (doc.file_size_bytes != null) score -= Math.floor(doc.file_size_bytes / 1_048_576);
  return score;
}
