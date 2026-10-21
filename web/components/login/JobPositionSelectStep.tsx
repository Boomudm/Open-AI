"use client";

import { cn } from "@/lib/cn";
import type { JobPositionBrief } from "@/lib/api";
import { Briefcase } from "lucide-react";

export type JobPositionSelectStepProps = {
  positions: JobPositionBrief[];
  value: string;
  onChange: (positionId: string) => void;
  onContinue: () => void;
  loading?: boolean;
};

export function JobPositionSelectStep({
  positions,
  value,
  onChange,
  onContinue,
  loading,
}: JobPositionSelectStepProps) {
  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-landing-border/80">
        <Briefcase className="h-4 w-4 text-landing-cta shrink-0" aria-hidden />
        <div>
          <p className="text-sm font-medium text-landing-text">เลือกตำแหน่งงานของคุณ</p>
          <p className="text-xs text-landing-muted mt-0.5">
            เลือกได้ครั้งเดียวตอนเข้าใช้งานครั้งแรก — ใช้กำหนดเอกสารที่คุณเห็น
          </p>
        </div>
      </div>

      <ul className="space-y-1.5 max-h-60 overflow-y-auto gemini-scrollbar" role="listbox">
        {positions.map((p) => {
          const id = String(p.position_id);
          const active = value === id;
          return (
            <li key={id}>
              <button
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => onChange(id)}
                className={cn(
                  "w-full text-left px-3 py-2.5 rounded-md gemini-focus-ring transition-colors",
                  "border text-sm",
                  active
                    ? "border-landing-cta/40 bg-landing-cta/10 text-landing-text"
                    : "border-landing-border bg-landing-bg text-landing-text hover:bg-landing-surface"
                )}
              >
                <span className="font-medium">{p.name_th}</span>
                <span className="block text-xs text-landing-muted mt-0.5 font-mono">
                  {p.position_code}
                </span>
                {p.description && (
                  <span className="block text-xs text-landing-muted mt-1 line-clamp-2">
                    {p.description}
                  </span>
                )}
              </button>
            </li>
          );
        })}
      </ul>

      {positions.length === 0 && (
        <p className="text-sm text-landing-muted text-center py-4">
          ยังไม่มีตำแหน่งงานในระบบ — ติดต่อผู้ดูแลระบบ
        </p>
      )}

      <button
        type="button"
        disabled={!value || loading || positions.length === 0}
        onClick={onContinue}
        className={cn(
          "w-full h-10 rounded-md text-sm font-semibold text-white gemini-focus-ring landing-btn-cta",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      >
        {loading ? "กำลังบันทึก…" : "เริ่มใช้งาน"}
      </button>
    </div>
  );
}
