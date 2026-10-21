"use client";

import { useMachineImage } from "@/hooks/useMachineImage";
import { api } from "@/lib/api";
import { canWriteFactory } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { parseApiError } from "@/lib/errors";
import { queryKeys } from "@/lib/query-keys";
import { useUiStore } from "@/stores/uiStore";
import { useQueryClient } from "@tanstack/react-query";
import { machinePlaceholderSrc } from "@/lib/machine-placeholders";
import { Camera, ImagePlus, Loader2, Trash2, Upload } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";

export type MachineCoverImageProps = {
  machineId: string;
  machineName?: string;
  machineType?: string | null;
  imageUpdatedAt?: string | null;
  aspectClass?: string;
  showUpload?: boolean;
  /** card = compact hover upload; editor = prominent upload in edit forms */
  variant?: "card" | "editor";
  className?: string;
  onImageChange?: () => void;
};

const ACCEPT = "image/jpeg,image/png,image/webp";
const MAX_MB = 2;

/** Pick a cover image before the machine row exists; uploads after create. */
export function MachineCoverDraftPicker({
  machineType,
  file,
  onFileChange,
  aspectClass = "aspect-square max-w-[220px]",
  className,
}: {
  machineType?: string | null;
  file: File | null;
  onFileChange: (file: File | null) => void;
  aspectClass?: string;
  className?: string;
}) {
  const inputId = useId();
  const [pickError, setPickError] = useState("");
  const previewUrl = useMemo(
    () => (file ? URL.createObjectURL(file) : null),
    [file]
  );

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  const placeholderSrc = useMemo(
    () => machinePlaceholderSrc("NEW", machineType),
    [machineType]
  );

  function validateAndSet(next: File | null) {
    if (!next) {
      setPickError("");
      onFileChange(null);
      return;
    }
    if (!next.type.match(/^image\/(jpeg|png|webp)$/i)) {
      setPickError("รองรับเฉพาะ JPEG, PNG หรือ WebP");
      return;
    }
    if (next.size > MAX_MB * 1024 * 1024) {
      setPickError(`ไฟล์ใหญ่เกิน ${MAX_MB} MB`);
      return;
    }
    setPickError("");
    onFileChange(next);
  }

  return (
    <div className={cn("space-y-2", className)}>
      <div>
        <p className="text-sm font-medium">รูปปกเครื่องจักร</p>
        <p className="text-xs text-gemini-muted mt-0.5">
          เลือกรูปได้เลย — ระบบจะอัปโหลดหลังกดบันทึกข้อมูล
        </p>
      </div>
      <input
        id={inputId}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        onChange={(e) => {
          validateAndSet(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
      <label
        htmlFor={inputId}
        className={cn(
          "group relative block overflow-hidden rounded-xl cursor-pointer",
          "border-2 border-dashed border-gemini-border/80 bg-gemini-surface/40 dark:bg-gemini-dark-surface/40",
          aspectClass
        )}
      >
        {previewUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={previewUrl} alt="" className="absolute inset-0 h-full w-full object-cover" />
        ) : (
          <>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={placeholderSrc}
              alt=""
              className="absolute inset-0 h-full w-full object-contain opacity-30 p-4 pointer-events-none"
            />
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 px-4 text-center pointer-events-none">
              <ImagePlus className="h-8 w-8 text-gemini-muted" aria-hidden />
              <span className="text-sm font-medium text-gemini-text">คลิกเลือกรูป</span>
            </div>
          </>
        )}
      </label>
      <div className="flex flex-wrap gap-2">
        <label
          htmlFor={inputId}
          className="inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-gemini-border px-3 text-sm font-medium hover:bg-gemini-surface dark:hover:bg-gemini-dark-surface"
        >
          <Upload className="h-4 w-4" />
          {file ? "เปลี่ยนรูป" : "เลือกรูป"}
        </label>
        {file && (
          <button
            type="button"
            onClick={() => {
              setPickError("");
              onFileChange(null);
            }}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-500/40 px-3 text-sm text-red-600 dark:text-red-400 hover:bg-red-500/10"
          >
            <Trash2 className="h-4 w-4" />
            ลบรูป
          </button>
        )}
      </div>
      {pickError && (
        <p className="text-xs text-red-600 dark:text-red-400">{pickError}</p>
      )}
    </div>
  );
}

/** Placeholder cover slot while creating a machine (matches editor layout). */
export function MachineCoverPlaceholder({
  machineType,
  aspectClass = "aspect-square max-w-[220px]",
  className,
}: {
  machineType?: string | null;
  aspectClass?: string;
  className?: string;
}) {
  const placeholderSrc = useMemo(
    () => machinePlaceholderSrc("NEW", machineType),
    [machineType]
  );

  return (
    <div className={cn("space-y-2", className)}>
      <div>
        <p className="text-sm font-medium">รูปปกเครื่องจักร</p>
        <p className="text-xs text-gemini-muted mt-0.5">
          แสดงในรายการเครื่องและหน้าเอกสาร · JPEG, PNG, WebP · สูงสุด {MAX_MB} MB
        </p>
      </div>
      <div
        className={cn(
          "relative overflow-hidden rounded-xl border-2 border-dashed border-gemini-border/80",
          "bg-gemini-surface/40 dark:bg-gemini-dark-surface/40",
          aspectClass
        )}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={placeholderSrc}
          alt=""
          className="absolute inset-0 h-full w-full object-contain opacity-30 p-4"
        />
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 px-4 text-center">
          <ImagePlus className="h-8 w-8 text-gemini-muted/70" aria-hidden />
          <span className="text-xs text-gemini-muted">บันทึกข้อมูลก่อน แล้วอัปโหลดรูปได้</span>
        </div>
      </div>
    </div>
  );
}

export function MachineCoverImage({
  machineId,
  machineName,
  machineType,
  imageUpdatedAt,
  aspectClass = "aspect-[4/3]",
  showUpload = false,
  variant = "card",
  className,
  onImageChange,
}: MachineCoverImageProps) {
  const inputId = useId();
  const queryClient = useQueryClient();
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);
  const canWrite = canWriteFactory(selectedFactoryId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [uploading, setUploading] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [dragOver, setDragOver] = useState(false);

  const { imageUrl, loading, hasImage } = useMachineImage(machineId, imageUpdatedAt);
  const placeholderSrc = useMemo(
    () => machinePlaceholderSrc(machineId, machineType),
    [machineId, machineType]
  );

  const isEditor = variant === "editor";
  const canEdit = showUpload && canWrite;

  async function refreshImage() {
    await queryClient.invalidateQueries({ queryKey: ["machineImage", machineId] });
    await queryClient.invalidateQueries({ queryKey: queryKeys.machines() });
    onImageChange?.();
  }

  const handleUpload = async (file: File) => {
    if (!file.type.match(/^image\/(jpeg|png|webp)$/i)) {
      setUploadError("รองรับเฉพาะ JPEG, PNG หรือ WebP");
      return;
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      setUploadError(`ไฟล์ใหญ่เกิน ${MAX_MB} MB`);
      return;
    }
    setUploading(true);
    setUploadError("");
    try {
      await api.uploadMachineImage(machineId, file);
      await refreshImage();
    } catch (e) {
      setUploadError(parseApiError(e));
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async () => {
    setDeleting(true);
    setUploadError("");
    try {
      await api.deleteMachineImage(machineId);
      await refreshImage();
    } catch (e) {
      setUploadError(parseApiError(e));
    } finally {
      setDeleting(false);
    }
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (!canEdit || uploading) return;
    const file = e.dataTransfer.files?.[0];
    if (file) void handleUpload(file);
  };

  return (
    <div className={cn("space-y-2", isEditor && className)}>
      {isEditor && (
        <div>
          <p className="text-sm font-medium">รูปปกเครื่องจักร</p>
          <p className="text-xs text-gemini-muted mt-0.5">
            แสดงในรายการเครื่องและหน้าเอกสาร · JPEG, PNG, WebP · สูงสุด {MAX_MB} MB
          </p>
        </div>
      )}

      {canEdit && (
        <input
          id={inputId}
          ref={fileRef}
          type="file"
          accept={ACCEPT}
          className="sr-only"
          disabled={uploading || deleting}
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) void handleUpload(f);
            e.target.value = "";
          }}
        />
      )}

      {showUpload && !canWrite && (
        <p className="text-xs text-amber-700 dark:text-amber-400">
          ไม่มีสิทธิ์อัปโหลดรูปในโรงงานนี้
        </p>
      )}

      {canEdit && isEditor ? (
        <label
          htmlFor={inputId}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          className={cn(
            "group relative block overflow-hidden rounded-xl cursor-pointer",
            "border-2 border-dashed border-gemini-border/80 bg-gemini-surface/40 dark:bg-gemini-dark-surface/40",
            aspectClass,
            className,
            dragOver && "border-gemini-blue ring-2 ring-gemini-blue/30",
            uploading && "pointer-events-none opacity-70"
          )}
        >
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
              <Loader2 className="h-6 w-6 animate-spin text-gemini-muted" />
            </div>
          )}
          {!loading && hasImage && imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl}
              alt={machineName ?? machineId}
              className="absolute inset-0 h-full w-full object-cover pointer-events-none"
            />
          )}
          {!loading && !hasImage && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={placeholderSrc}
              alt={machineName ?? machineId}
              className="absolute inset-0 h-full w-full object-contain opacity-40 p-4 pointer-events-none"
            />
          )}
          {!loading && (
            <div
              className={cn(
                "absolute inset-0 flex flex-col items-center justify-center gap-2 px-4 text-center pointer-events-none",
                hasImage ? "bg-black/0 group-hover:bg-black/40 transition-colors" : "bg-transparent"
              )}
            >
              <div
                className={cn(
                  "flex flex-col items-center gap-1.5 rounded-lg px-4 py-3",
                  hasImage ? "opacity-0 group-hover:opacity-100 transition-opacity" : "opacity-100"
                )}
              >
                {uploading ? (
                  <Loader2 className="h-8 w-8 animate-spin text-gemini-blue" />
                ) : (
                  <ImagePlus className="h-8 w-8 text-gemini-muted" />
                )}
                <span className="text-sm font-medium text-gemini-text">
                  {uploading ? "กำลังอัปโหลด…" : "คลิกหรือลากรูปมาวาง"}
                </span>
              </div>
            </div>
          )}
        </label>
      ) : (
        <div
          className={cn(
            "group relative overflow-hidden rounded-xl",
            "bg-gradient-to-br from-gemini-blue/20 to-gemini-blue/5 dark:from-gemini-dark-blue/30 dark:to-gemini-dark-blue/10",
            aspectClass,
            className
          )}
        >
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center">
              <Loader2 className="h-6 w-6 animate-spin text-gemini-muted" />
            </div>
          )}
          {!loading && hasImage && imageUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={imageUrl}
              alt={machineName ?? machineId}
              className="absolute inset-0 h-full w-full object-cover"
            />
          )}
          {!loading && !hasImage && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={placeholderSrc}
              alt={machineName ?? machineId}
              className="absolute inset-0 h-full w-full object-contain bg-white p-2"
            />
          )}

          {canEdit && (
            <label
              htmlFor={inputId}
              className={cn(
                "absolute bottom-2 right-2 h-8 px-2 rounded-full text-xs font-medium z-10 cursor-pointer",
                "bg-black/50 text-white hover:bg-black/65 flex items-center gap-1",
                "opacity-90 sm:opacity-0 sm:group-hover:opacity-100 focus-within:opacity-100 transition-opacity",
                uploading && "pointer-events-none opacity-50"
              )}
              aria-label="เปลี่ยนรูปเครื่องจักร"
            >
              {uploading ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Camera className="h-3.5 w-3.5" />
              )}
              เปลี่ยนรูป
            </label>
          )}

          {uploadError && (
            <p className="absolute bottom-0 left-0 right-0 text-[10px] bg-red-600/90 text-white px-2 py-1 truncate">
              {uploadError}
            </p>
          )}
        </div>
      )}

      {canEdit && isEditor && (
        <>
          <div className="flex flex-wrap gap-2">
            <label
              htmlFor={inputId}
              className={cn(
                "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-gemini-border px-3 text-sm font-medium hover:bg-gemini-surface dark:hover:bg-gemini-dark-surface",
                (uploading || deleting) && "pointer-events-none opacity-50"
              )}
            >
              {uploading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Upload className="h-4 w-4" />
              )}
              {hasImage ? "เปลี่ยนรูป" : "อัปโหลดรูป"}
            </label>
            {hasImage && (
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={uploading || deleting}
                className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-500/40 px-3 text-sm text-red-600 dark:text-red-400 hover:bg-red-500/10"
              >
                {deleting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Trash2 className="h-4 w-4" />
                )}
                ลบรูป
              </button>
            )}
          </div>
          {uploadError && (
            <p className="text-xs text-red-600 dark:text-red-400">{uploadError}</p>
          )}
        </>
      )}
    </div>
  );
}
