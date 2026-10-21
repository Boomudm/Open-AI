import type { FeedbackReportPayload } from "@/components/feedback/FeedbackReportModal";
import { idbDelete, idbGetAll, idbPut } from "@/lib/offline/idb";
import type { FeedbackOutboxRecord } from "@/lib/offline/types";

export async function enqueueFeedback(
  payload: FeedbackReportPayload,
  comment: string,
  photos: File[],
  issueType?: string
): Promise<string> {
  const local_id = crypto.randomUUID();
  const record: FeedbackOutboxRecord = {
    local_id,
    payload,
    comment: comment.trim(),
    issue_type: issueType || undefined,
    photos: photos.map((f) => ({
      blob: f,
      mime_type: f.type || "image/jpeg",
      name: f.name || "photo.jpg",
    })),
    created_at: new Date().toISOString(),
    retry_count: 0,
    status: "pending",
  };
  await idbPut("feedback_outbox", record);
  return local_id;
}

export async function listPendingFeedback(): Promise<FeedbackOutboxRecord[]> {
  try {
    const rows = await idbGetAll<FeedbackOutboxRecord>("feedback_outbox");
    return rows.filter((r) => r.status === "pending");
  } catch {
    return [];
  }
}

export async function countPendingFeedback(): Promise<number> {
  const rows = await listPendingFeedback();
  return rows.length;
}

export async function markFeedbackSent(localId: string): Promise<void> {
  await idbDelete("feedback_outbox", localId);
}

export async function markFeedbackFailed(localId: string, error: string): Promise<void> {
  const rows = await idbGetAll<FeedbackOutboxRecord>("feedback_outbox");
  const row = rows.find((r) => r.local_id === localId);
  if (!row) return;
  await idbPut("feedback_outbox", {
    ...row,
    retry_count: row.retry_count + 1,
    status: row.retry_count >= 5 ? "failed" : "pending",
    last_error: error,
  });
}

export function feedbackToFormData(record: FeedbackOutboxRecord): FormData {
  const { payload } = record;
  const form = new FormData();
  form.append("factory_id", payload.factoryId);
  form.append("source_type", payload.sourceType);
  form.append("comment", record.comment);
  if (record.issue_type) form.append("issue_type", record.issue_type);
  if (payload.machineId) form.append("machine_id", payload.machineId);
  if (payload.docId) form.append("doc_id", payload.docId);
  if (payload.page != null) form.append("page", String(payload.page));
  if (payload.sessionId) form.append("session_id", payload.sessionId);
  if (payload.messageId) form.append("message_id", payload.messageId);
  const ctx = {
    ...payload.contextSnapshot,
    queued_offline: true,
    queued_at: record.created_at,
  };
  form.append("context", JSON.stringify(ctx));
  for (const photo of record.photos) {
    form.append("photos", photo.blob, photo.name);
  }
  return form;
}
