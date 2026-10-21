"use client";

import { Modal } from "@/components/ui/Modal";
import { cn } from "@/lib/cn";
import { LABEL_CANCEL, LABEL_CONFIRM } from "@/lib/messages.th";

type ConfirmDialogProps = {
  open: boolean;
  onClose: () => void;
  onConfirm: () => void;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  loading?: boolean;
};

export function ConfirmDialog({
  open,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel = LABEL_CONFIRM,
  cancelLabel = LABEL_CANCEL,
  destructive = false,
  loading = false,
}: ConfirmDialogProps) {
  return (
    <Modal open={open} onClose={loading ? () => {} : onClose} title={title}>
      <p className="text-sm text-spark-text-secondary mb-5">{message}</p>
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          disabled={loading}
          className="h-9 px-3 rounded-sm text-sm font-medium border border-spark-border text-spark-text-secondary hover:bg-spark-hover spark-focus-ring disabled:opacity-50"
        >
          {cancelLabel}
        </button>
        <button
          type="button"
          onClick={onConfirm}
          disabled={loading}
          className={cn(
            "h-9 px-3 rounded-sm text-sm font-medium text-white spark-focus-ring disabled:opacity-50",
            destructive ? "bg-red-600 hover:bg-red-700" : "bg-spark-accent hover:bg-spark-accent/90"
          )}
        >
          {loading ? "…" : confirmLabel}
        </button>
      </div>
    </Modal>
  );
}
