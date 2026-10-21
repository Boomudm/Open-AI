"use client";

import { hasNoJobPositionAssigned } from "@/lib/auth";
import { cn } from "@/lib/cn";
import { Info } from "lucide-react";

export function NoJobPositionBanner({ className }: { className?: string }) {
  if (!hasNoJobPositionAssigned()) return null;

  return (
    <div
      className={cn(
        "flex gap-2 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2.5 text-sm text-amber-950 dark:text-amber-100",
        className
      )}
      role="status"
    >
      <Info className="h-4 w-4 shrink-0 mt-0.5" aria-hidden />
      <p>
        บัญชีของคุณยังไม่ได้เลือกตำแหน่งงาน — คุณจะเห็นได้เฉพาะเอกสารที่เปิดให้ทุกตำแหน่ง
        ออกจากระบบแล้วเข้าใหม่เพื่อเลือกตำแหน่ง หรือติดต่อผู้ดูแลระบบ
      </p>
    </div>
  );
}
