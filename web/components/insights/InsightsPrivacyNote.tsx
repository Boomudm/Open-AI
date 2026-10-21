"use client";

import { Shield } from "lucide-react";

type InsightsPrivacyNoteProps = {
  compact?: boolean;
};

export function InsightsPrivacyNote({ compact = false }: InsightsPrivacyNoteProps) {
  if (compact) {
    return (
      <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted flex items-start gap-1.5">
        <Shield className="h-3.5 w-3.5 shrink-0 mt-0.5" aria-hidden />
        <span>
          แสดงเฉพาะสรุปเทรนด์ — ไม่ระบุชื่อผู้ถาม; ดูข้อความดิบได้เฉพาะแอดมิน (write+) ผ่าน drill-down
        </span>
      </p>
    );
  }

  return (
    <div
      className="rounded-2xl border border-gemini-border/50 dark:border-gemini-dark-border/50 bg-gemini-surface/50 dark:bg-gemini-dark-surface/50 p-4"
      role="note"
    >
      <div className="flex items-center gap-2 mb-2">
        <Shield className="h-4 w-4 text-gemini-muted dark:text-gemini-dark-muted" />
        <h3 className="text-xs font-medium uppercase tracking-wide text-gemini-muted dark:text-gemini-dark-muted">
          ความเป็นส่วนตัว
        </h3>
      </div>
      <ul className="text-xs text-gemini-muted dark:text-gemini-dark-muted space-y-1 list-disc list-inside">
        <li>Problem Pulse และกราฟแสดงเฉพาะหัวข้อสรุปและตัวเลข — ไม่แสดงชื่อพนักงาน</li>
        <li>Drill-down คำถาม AI แสดงข้อความเต็ม + เครื่อง + เวลา (ไม่มี user_id / username)</li>
        <li>ข้อมูลจำกัดตาม factory RBAC — แอดมินเห็นเฉพาะโรงงานที่มีสิทธิ์ write+</li>
      </ul>
    </div>
  );
}
