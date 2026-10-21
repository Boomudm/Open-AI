"use client";

import { ClientPortal } from "@/components/ui/ClientPortal";
import { Tooltip } from "@/components/ui/Tooltip";
import { cn } from "@/lib/cn";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import { X } from "lucide-react";
import { useEffect, useId, type ReactNode } from "react";

type ModalProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  className?: string;
};

export function Modal({ open, onClose, title, children, className }: ModalProps) {
  const titleId = useId();

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  if (!open) return null;

  return (
    <ClientPortal>
    <div className="fixed inset-0 flex items-center justify-center p-4" style={{ zIndex: Z_OVERLAY_PANEL }}>
      <button
        type="button"
        className="absolute inset-0 bg-spark-bg/70 backdrop-blur-sm"
        style={{ zIndex: Z_OVERLAY_BACKDROP }}
        aria-label="ปิดหน้าต่าง"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        className={cn(
          "relative w-full max-w-md spark-glass border border-spark-border rounded-sm shadow-xl",
          className
        )}
        style={{ zIndex: Z_OVERLAY_PANEL }}
      >
        <div className="flex items-center justify-between gap-3 px-4 py-3 border-b border-spark-border">
          <h2
            id={titleId}
            className="font-mono text-sm font-semibold text-spark-text-primary tracking-tight"
          >
            {title}
          </h2>
          <Tooltip content="ปิดหน้าต่าง">
            <button
              type="button"
              onClick={onClose}
              className="touch-target p-2 rounded-sm text-spark-text-secondary hover:text-spark-text-primary hover:bg-spark-hover spark-focus-ring"
              aria-label="ปิด"
            >
              <X className="h-4 w-4" />
            </button>
          </Tooltip>
        </div>
        <div className="p-4">{children}</div>
      </div>
    </div>
    </ClientPortal>
  );
}
