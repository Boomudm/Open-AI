"use client";

import { FormFieldLabel } from "@/components/ingest/FormFieldLabel";
import { cn } from "@/lib/cn";
import { formatFileSize } from "@/lib/ingest";
import {
  acceptedExtensionsForDocumentType,
  fileFormatHintForDocumentType,
  isFileAcceptedForDocumentType,
} from "@/lib/ingest-upload";
import { FileText, Trash2, Upload } from "lucide-react";
import { useCallback, useEffect, useId, useMemo, useState, type DragEvent } from "react";

export const INGEST_MAX_FILE_BYTES = 50 * 1024 * 1024;

const DEFAULT_EXTENSIONS = [".pdf", ".xlsx", ".docx"] as const;

function extensionOf(name: string): string {
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export function validateIngestFile(
  file: File,
  documentType?: string
): string | null {
  const allowed = documentType
    ? [...acceptedExtensionsForDocumentType(documentType)]
    : [...DEFAULT_EXTENSIONS];
  const ext = extensionOf(file.name);
  if (!allowed.includes(ext)) {
    const hint = documentType
      ? fileFormatHintForDocumentType(documentType)
      : "PDF, Excel (.xlsx) และ Word (.docx)";
    return `ประเภทเอกสารนี้รองรับเฉพาะ ${hint}`;
  }
  if (file.size > INGEST_MAX_FILE_BYTES) {
    return "ไฟล์ใหญ่เกิน 50 MB";
  }
  return null;
}

type FileDropZoneProps = {
  file: File | null;
  onFileChange: (file: File | null) => void;
  onValidationError?: (message: string) => void;
  disabled?: boolean;
  className?: string;
  /** Fill grid cell height beside metadata fields */
  fillColumn?: boolean;
  documentType?: string;
  /** Accept PDF/XLSX/DOCX before document type is chosen (preflight-first flow). */
  acceptAnySupported?: boolean;
};

export function FileDropZone({
  file,
  onFileChange,
  onValidationError,
  disabled = false,
  className,
  fillColumn = false,
  documentType,
  acceptAnySupported = false,
}: FileDropZoneProps) {
  const generatedId = useId();
  const inputId = "ingest-file";
  const [dragOver, setDragOver] = useState(false);

  const acceptExtensions = useMemo(
    () =>
      acceptAnySupported || !documentType
        ? DEFAULT_EXTENSIONS
        : acceptedExtensionsForDocumentType(documentType),
    [acceptAnySupported, documentType]
  );
  const acceptAttr = acceptExtensions.join(",");
  const formatHint = acceptAnySupported || !documentType
    ? "PDF · XLSX · DOCX"
    : fileFormatHintForDocumentType(documentType);

  useEffect(() => {
    if (!file || !documentType || acceptAnySupported) return;
    if (!isFileAcceptedForDocumentType(file, documentType)) {
      onFileChange(null);
      onValidationError?.(validateIngestFile(file, documentType) ?? "");
    }
  }, [documentType, file, onFileChange, onValidationError, acceptAnySupported]);

  const applyFile = useCallback(
    (next: File | null) => {
      if (!next) {
        onFileChange(null);
        onValidationError?.("");
        return;
      }
      const validateType = acceptAnySupported ? undefined : documentType;
      const err = validateIngestFile(next, validateType);
      if (err) {
        onValidationError?.(err);
        return;
      }
      onValidationError?.("");
      onFileChange(next);
    },
    [onFileChange, onValidationError, documentType, acceptAnySupported]
  );

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (disabled) return;
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) applyFile(dropped);
  };

  return (
    <div className={cn("space-y-2", fillColumn && "h-full min-h-0 flex flex-col", className)}>
      <div className="shrink-0 space-y-0.5">
        <FormFieldLabel required>ไฟล์เอกสาร</FormFieldLabel>
        <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted">
          {formatHint} · สูงสุด 50 MB
        </p>
      </div>

      <input
        id={inputId}
        type="file"
        accept={acceptAttr}
        disabled={disabled}
        className="sr-only"
        aria-describedby={generatedId}
        onChange={(e) => {
          applyFile(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />

      <label
        htmlFor={inputId}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={onDrop}
        className={cn(
          "group relative block overflow-hidden rounded-xl cursor-pointer",
          "border-2 border-dashed border-gemini-border/80 bg-gemini-surface/40 dark:bg-gemini-dark-surface/40",
          fillColumn ? "flex-1 min-h-[10rem] md:min-h-0 aspect-square max-w-[220px]" : "min-h-[10rem]",
          dragOver && !disabled && "border-gemini-blue ring-2 ring-gemini-blue/30",
          disabled && "pointer-events-none opacity-60 cursor-not-allowed"
        )}
      >
        {file ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 px-4 text-center pointer-events-none">
            <FileText className="h-8 w-8 text-gemini-blue dark:text-gemini-dark-blue shrink-0" aria-hidden />
            <p className="text-xs font-medium text-gemini-text dark:text-gemini-dark-text line-clamp-3 break-all w-full">
              {file.name}
            </p>
            <p className="text-[10px] text-gemini-muted tabular-nums">{formatFileSize(file.size)}</p>
          </div>
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 px-4 text-center pointer-events-none">
            <Upload className="h-8 w-8 text-gemini-muted" aria-hidden />
            <span className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text">
              คลิกหรือลากไฟล์มาวาง
            </span>
            <span className="text-xs text-gemini-muted">{formatHint}</span>
          </div>
        )}
      </label>

      <div className="flex flex-wrap gap-2 shrink-0">
        <label
          htmlFor={inputId}
          className={cn(
            "inline-flex h-9 cursor-pointer items-center gap-1.5 rounded-lg border border-gemini-border px-3 text-sm font-medium",
            "hover:bg-gemini-surface dark:hover:bg-gemini-dark-surface",
            disabled && "pointer-events-none opacity-50"
          )}
        >
          <Upload className="h-4 w-4" />
          {file ? "เปลี่ยนไฟล์" : "เลือกไฟล์"}
        </label>
        {file && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => applyFile(null)}
            className="inline-flex h-9 items-center gap-1.5 rounded-lg border border-red-500/40 px-3 text-sm text-red-600 dark:text-red-400 hover:bg-red-500/10 disabled:opacity-50"
          >
            <Trash2 className="h-4 w-4" />
            ลบไฟล์
          </button>
        )}
      </div>
    </div>
  );
}
