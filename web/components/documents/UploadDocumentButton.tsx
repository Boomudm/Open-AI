"use client";

import { canUploadDocuments } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { useUiStore } from "@/stores/uiStore";
import { Upload } from "lucide-react";
import Link from "next/link";

export type UploadDocumentButtonProps = {
  defaultMachineId?: string;
  variant?: "primary" | "secondary" | "header";
  label?: string;
  className?: string;
};

export function UploadDocumentButton({
  defaultMachineId,
  variant = "primary",
  label = "อัปโหลดเอกสาร",
  className,
}: UploadDocumentButtonProps) {
  const selectedFactoryId = useUiStore((s) => s.selectedFactoryId);

  if (!canUploadDocuments(selectedFactoryId)) return null;

  const href = defaultMachineId
    ? `/upload?machine=${encodeURIComponent(defaultMachineId)}`
    : "/upload";

  const buttonClass = cn(
    "inline-flex items-center gap-1.5 gemini-theme-transition gemini-focus-ring shrink-0",
    variant === "primary" &&
      "px-4 py-2 rounded-full text-sm font-medium bg-gemini-blue dark:bg-gemini-dark-blue text-white hover:opacity-90",
    variant === "secondary" &&
      "px-3 py-1.5 rounded-full text-sm font-medium border border-gemini-border/70 dark:border-gemini-dark-border/70 text-gemini-text dark:text-gemini-dark-text hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
    variant === "header" &&
      "h-9 px-3 rounded-full text-xs font-medium bg-gemini-blue dark:bg-gemini-dark-blue text-white hover:opacity-90",
    className
  );

  return (
    <Link href={href} className={buttonClass}>
      <Upload className={variant === "header" ? "h-3.5 w-3.5" : "h-4 w-4"} aria-hidden />
      {label}
    </Link>
  );
}
