"use client";

import { useJobPositions } from "@/hooks/useJobPositions";
import { FormFieldLabel } from "@/components/ingest/FormFieldLabel";
import { cn } from "@/lib/cn";

type JobPositionPickerProps = {
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  disabled?: boolean;
  className?: string;
};

export function JobPositionPicker({
  selectedIds,
  onChange,
  disabled = false,
  className,
}: JobPositionPickerProps) {
  const { data: jobPositions = [], isLoading } = useJobPositions();

  function togglePosition(id: string) {
    if (disabled) return;
    onChange(
      selectedIds.includes(id)
        ? selectedIds.filter((x) => x !== id)
        : [...selectedIds, id]
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg border border-gemini-border/60 dark:border-gemini-dark-border/60",
        "bg-gemini-bg/50 dark:bg-gemini-dark-bg/50 px-3 py-2 space-y-2",
        className
      )}
    >
      <FormFieldLabel required={false}>ตำแหน่งที่เห็นเอกสารได้</FormFieldLabel>
      <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted -mt-1">
        ไม่เลือก = ทุกตำแหน่งในโรงงาน
      </p>
      {isLoading ? (
        <p className="text-xs text-gemini-muted">กำลังโหลดตำแหน่ง…</p>
      ) : jobPositions.length === 0 ? (
        <p className="text-xs text-gemini-muted">
          ยังไม่มีตำแหน่งในระบบ — เอกสารจะมองเห็นได้ทุกตำแหน่ง
        </p>
      ) : (
        <div className="flex flex-wrap gap-2 max-h-32 overflow-y-auto">
          {jobPositions.map((pos) => {
            const checked = selectedIds.includes(pos.position_id);
            return (
              <button
                key={pos.position_id}
                type="button"
                disabled={disabled}
                onClick={() => togglePosition(pos.position_id)}
                className={cn(
                  "inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1.5 text-xs transition-colors",
                  "disabled:opacity-50 disabled:cursor-not-allowed",
                  checked
                    ? "border-gemini-blue/60 bg-gemini-blue/10 text-gemini-text dark:border-gemini-dark-blue/60 dark:bg-gemini-dark-blue/15"
                    : "border-gemini-border dark:border-gemini-dark-border hover:bg-gemini-surface/60 dark:hover:bg-gemini-dark-surface/60"
                )}
                aria-pressed={checked}
              >
                {pos.name_th}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
