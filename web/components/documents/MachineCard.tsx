"use client";

import { MachineCoverImage } from "@/components/documents/MachineCoverImage";
import type { Machine } from "@/lib/api";
import { cn } from "@/lib/cn";

export type MachineCardProps = {
  machine: Machine;
  docCount: number;
  onClick: () => void;
  className?: string;
};

export function MachineCard({ machine, docCount, onClick, className }: MachineCardProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "group text-left w-full rounded-2xl overflow-hidden gemini-theme-transition",
        "border border-gemini-border/70 dark:border-gemini-dark-border/70",
        "bg-gemini-surface dark:bg-gemini-dark-surface",
        "hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-gemini-blue/40",
        className
      )}
    >
      <MachineCoverImage
        machineId={machine.machine_id}
        machineName={machine.machine_name}
        machineType={machine.machine_type}
        imageUpdatedAt={machine.image_updated_at}
        showUpload
        aspectClass="aspect-[4/3] w-full"
        className="rounded-none"
      />
      <div className="p-3">
        <p className="text-sm font-semibold text-gemini-text dark:text-gemini-dark-text font-mono">
          {machine.machine_id}
        </p>
        <p className="text-xs text-gemini-text dark:text-gemini-dark-text truncate mt-0.5">
          {machine.machine_name}
        </p>
        {machine.machine_type && (
          <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted truncate">
            {machine.machine_type}
          </p>
        )}
        <p className="text-[11px] text-gemini-blue dark:text-gemini-dark-blue mt-2 font-medium">
          {docCount > 0 ? `${docCount} เอกสาร` : "ยังไม่มีเอกสาร"}
        </p>
      </div>
    </button>
  );
}
