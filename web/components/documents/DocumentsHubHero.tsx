"use client";

import { cn } from "@/lib/cn";
import { Factory, FileStack, ListChecks } from "lucide-react";

export type DocumentsHubHeroProps = {
  documentCount: number;
  machineCount: number;
  showIngestJobs?: boolean;
  onBrowseMachines: () => void;
  onBrowseAll: () => void;
  onIngestJobs?: () => void;
};

export function DocumentsHubHero({
  documentCount,
  machineCount,
  showIngestJobs,
  onBrowseMachines,
  onBrowseAll,
  onIngestJobs,
}: DocumentsHubHeroProps) {
  return (
    <section
      className={cn(
        "rounded-2xl border border-gemini-border/70 dark:border-gemini-dark-border/70",
        "bg-gemini-surface/60 dark:bg-gemini-dark-surface/60 p-4 sm:p-5"
      )}
    >
      <div className="min-w-0">
        <h1 className="text-lg font-semibold text-gemini-text dark:text-gemini-dark-text">
          คลังเอกสารโรงงาน
        </h1>
        <p className="text-sm text-gemini-muted dark:text-gemini-dark-muted mt-1">
          คู่มือเครื่องจักร · SOP · ใบรับรอง · รายงานตรวจสอบ — ค้นหาและอัปโหลดได้ที่นี่
        </p>
        <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mt-2">
          {machineCount} เครื่องจักร · {documentCount} เอกสารในระบบ
        </p>
      </div>

      <div className="flex flex-wrap gap-2 mt-4">
        <QuickLink icon={Factory} label="เครื่องจักร" onClick={onBrowseMachines} />
        <QuickLink icon={FileStack} label="เอกสารทั้งหมด" onClick={onBrowseAll} />
        {showIngestJobs && onIngestJobs && (
          <QuickLink icon={ListChecks} label="งานนำเข้า" onClick={onIngestJobs} />
        )}
      </div>
    </section>
  );
}

function QuickLink({
  icon: Icon,
  label,
  onClick,
}: {
  icon: typeof Factory;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium",
        "border border-gemini-border/60 dark:border-gemini-dark-border/60",
        "text-gemini-text dark:text-gemini-dark-text",
        "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover gemini-focus-ring"
      )}
    >
      <Icon className="h-3.5 w-3.5 text-gemini-muted" aria-hidden />
      {label}
    </button>
  );
}
