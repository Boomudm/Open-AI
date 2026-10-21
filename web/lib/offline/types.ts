import type { IndexedDocument, Machine } from "@/lib/api";
import type { FeedbackReportPayload } from "@/components/feedback/FeedbackReportModal";

export type CachedDocumentRecord = {
  doc_id: string;
  blob: Blob;
  mime_type: string;
  file_hash_sha256: string | null;
  file_size_bytes: number;
  factory_id: string | null;
  machine_id: string | null;
  cached_at: string;
  last_accessed_at: string;
  access_count: number;
};

export type DocumentMetaSnapshot = {
  factory_id: string;
  documents: IndexedDocument[];
  synced_at: string;
};

export type MachineMetaSnapshot = {
  factory_id: string;
  machines: Machine[];
  synced_at: string;
};

export type FeedbackOutboxRecord = {
  local_id: string;
  payload: FeedbackReportPayload;
  comment: string;
  issue_type?: string;
  photos: { blob: Blob; mime_type: string; name: string }[];
  created_at: string;
  retry_count: number;
  status: "pending" | "failed";
  last_error?: string;
};

export type SyncStatus = {
  online: boolean;
  syncing: boolean;
  pendingFeedback: number;
  cachedDocsCount: number;
  cachedBytes: number;
  cacheMaxBytes: number;
  lastSyncAt: string | null;
};
