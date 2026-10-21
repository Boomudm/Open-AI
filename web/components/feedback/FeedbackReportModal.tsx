"use client";

import { Modal } from "@/components/ui/Modal";
import { useToast } from "@/components/ui/Toast";
import { api } from "@/lib/api";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { enqueueFeedback } from "@/lib/offline/feedback-outbox";
import { isBrowserOnline } from "@/lib/offline/network";
import { ImagePlus, Trash2 } from "lucide-react";
import { useCallback, useRef, useState } from "react";

export type FeedbackSourceType = "document" | "rag_answer" | "rag_source";

export type FeedbackReportPayload = {
  factoryId: string;
  sourceType: FeedbackSourceType;
  machineId?: string | null;
  docId?: string | null;
  page?: number | null;
  sessionId?: string | null;
  messageId?: string | null;
  contextLabel?: string;
  contextSnapshot?: Record<string, unknown>;
};

const ISSUE_OPTIONS: { value: string; label: string }[] = [
  { value: "", label: "ไม่ระบุ" },
  { value: "incorrect", label: "ข้อมูลไม่ถูกต้อง" },
  { value: "outdated", label: "ล้าสมัย" },
  { value: "missing_step", label: "ขาดขั้นตอน" },
  { value: "unclear", label: "ไม่ชัดเจน" },
  { value: "other", label: "อื่นๆ" },
];

const MAX_PHOTOS = 3;
const MAX_COMMENT = 500;

type PhotoPreview = { file: File; url: string };

type FeedbackReportModalProps = {
  open: boolean;
  onClose: () => void;
  payload: FeedbackReportPayload | null;
};

export function FeedbackReportModal({ open, onClose, payload }: FeedbackReportModalProps) {
  const { showToast } = useToast();
  const [comment, setComment] = useState("");
  const [issueType, setIssueType] = useState("");
  const [photos, setPhotos] = useState<PhotoPreview[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  const reset = useCallback(() => {
    setComment("");
    setIssueType("");
    setPhotos((prev) => {
      prev.forEach((p) => URL.revokeObjectURL(p.url));
      return [];
    });
    setError("");
    setSubmitting(false);
  }, []);

  const handleClose = useCallback(() => {
    reset();
    onClose();
  }, [onClose, reset]);

  const addPhotos = (files: FileList | null) => {
    if (!files?.length) return;
    const next: PhotoPreview[] = [];
    for (let i = 0; i < files.length && photos.length + next.length < MAX_PHOTOS; i++) {
      const file = files[i];
      if (!file.type.startsWith("image/")) continue;
      next.push({ file, url: URL.createObjectURL(file) });
    }
    if (next.length) setPhotos((prev) => [...prev, ...next]);
    if (fileRef.current) fileRef.current.value = "";
  };

  const removePhoto = (index: number) => {
    setPhotos((prev) => {
      const copy = [...prev];
      URL.revokeObjectURL(copy[index].url);
      copy.splice(index, 1);
      return copy;
    });
  };

  const handleSubmit = async () => {
    if (!payload?.factoryId) {
      setError("ไม่พบโรงงาน — เลือกโรงงานก่อนส่ง");
      return;
    }
    const trimmed = comment.trim();
    if (!trimmed) {
      setError("กรุณาระบุข้อความ");
      return;
    }
    setSubmitting(true);
    setError("");
    try {
      const form = new FormData();
      form.append("factory_id", payload.factoryId);
      form.append("source_type", payload.sourceType);
      form.append("comment", trimmed);
      if (payload.machineId) form.append("machine_id", payload.machineId);
      if (payload.docId) form.append("doc_id", payload.docId);
      if (payload.page != null) form.append("page", String(payload.page));
      if (payload.sessionId) form.append("session_id", payload.sessionId);
      if (payload.messageId) form.append("message_id", payload.messageId);
      if (issueType) form.append("issue_type", issueType);
      const ctx = {
        ...payload.contextSnapshot,
        submitted_from: payload.sourceType === "document" ? "document_viewer" : "chat",
      };
      form.append("context", JSON.stringify(ctx));
      photos.forEach((p) => form.append("photos", p.file));

      if (!isBrowserOnline()) {
        await enqueueFeedback(payload, trimmed, photos.map((p) => p.file), issueType || undefined);
        showToast("บันทึกไว้ในเครื่อง จะส่งเมื่อมีเน็ต");
        handleClose();
        return;
      }

      try {
        const created = await api.submitFeedback(form);
        showToast(`ส่งแล้ว (รหัส ${created.feedback_id.slice(0, 8)}…) — ขอบคุณที่ช่วยปรับปรุงคู่มือ`);
        handleClose();
      } catch (networkErr) {
        const msg = parseApiError(networkErr);
        if (msg.includes("fetch") || msg.includes("network") || msg.includes("Failed")) {
          await enqueueFeedback(payload, trimmed, photos.map((p) => p.file), issueType || undefined);
          showToast("บันทึกไว้ในเครื่อง จะส่งเมื่อมีเน็ต");
          handleClose();
          return;
        }
        throw networkErr;
      }
    } catch (e) {
      setError(parseApiError(e));
      setSubmitting(false);
    }
  };

  return (
    <Modal
      open={open && Boolean(payload)}
      onClose={handleClose}
      title="เสนอแนะการแก้ไข"
      className="max-w-lg"
    >
      {payload?.contextLabel && (
        <p className="text-xs text-spark-text-secondary mb-3 line-clamp-3 bg-spark-hover/40 rounded-sm px-3 py-2">
          {payload.contextLabel}
        </p>
      )}

      <label className="block text-xs font-medium text-spark-text-secondary mb-1">
        วิธีซ่อมจริงหน้างานต่างจากคู่มืออย่างไร?
      </label>
      <textarea
        value={comment}
        onChange={(e) => setComment(e.target.value.slice(0, MAX_COMMENT))}
        rows={4}
        placeholder="อธิบายสั้นๆ ว่าคู่มือผิดหรือขาดอะไร…"
        className={cn(
          "w-full rounded-sm border border-spark-border bg-transparent px-3 py-2 text-sm",
          "text-spark-text-primary placeholder:text-spark-text-secondary",
          "focus:outline-none focus:ring-1 focus:ring-spark-accent"
        )}
      />
      <p className="text-[10px] text-spark-text-secondary text-right mt-0.5">
        {comment.length}/{MAX_COMMENT}
      </p>

      <label className="block text-xs font-medium text-spark-text-secondary mt-3 mb-1">
        ประเภทปัญหา (ไม่บังคับ)
      </label>
      <select
        value={issueType}
        onChange={(e) => setIssueType(e.target.value)}
        className="w-full rounded-sm border border-spark-border bg-transparent px-3 py-2 text-sm text-spark-text-primary"
      >
        {ISSUE_OPTIONS.map((o) => (
          <option key={o.value || "none"} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>

      <div className="mt-4">
        <p className="text-xs font-medium text-spark-text-secondary mb-2">
          รูปหน้างาน (สูงสุด {MAX_PHOTOS} ใบ)
        </p>
        <div className="flex flex-wrap gap-2">
          {photos.map((p, i) => (
            <div key={p.url} className="relative h-16 w-16 rounded-sm overflow-hidden border border-spark-border">
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={p.url} alt="" className="h-full w-full object-cover" />
              <button
                type="button"
                onClick={() => removePhoto(i)}
                className="absolute top-0.5 right-0.5 p-0.5 rounded-full bg-black/50 text-white"
                aria-label={`ลบรูปที่ ${i + 1}`}
              >
                <Trash2 className="h-3 w-3" />
              </button>
            </div>
          ))}
          {photos.length < MAX_PHOTOS && (
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="h-16 w-16 flex flex-col items-center justify-center gap-1 rounded-sm border border-dashed border-spark-border text-spark-text-secondary hover:bg-spark-hover/50 text-[10px]"
            >
              <ImagePlus className="h-4 w-4" />
              เพิ่มรูป
            </button>
          )}
        </div>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          capture="environment"
          multiple
          className="hidden"
          onChange={(e) => addPhotos(e.target.files)}
        />
      </div>

      {error && (
        <p className="mt-3 text-sm text-red-600 dark:text-red-400" role="alert">
          {error}
        </p>
      )}

      <div className="flex justify-end gap-2 mt-4">
        <button
          type="button"
          onClick={handleClose}
          disabled={submitting}
          className="px-4 py-2 text-sm rounded-sm border border-spark-border hover:bg-spark-hover"
        >
          ยกเลิก
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={submitting || !comment.trim()}
          className={cn(
            "px-4 py-2 text-sm rounded-sm text-white",
            submitting || !comment.trim()
              ? "bg-spark-text-secondary/40 cursor-not-allowed"
              : "bg-spark-accent hover:opacity-90"
          )}
        >
          {submitting ? "กำลังส่ง…" : "ส่ง"}
        </button>
      </div>
    </Modal>
  );
}
