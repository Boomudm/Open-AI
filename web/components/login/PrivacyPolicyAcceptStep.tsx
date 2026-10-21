"use client";

import { PrivacyPolicyContent } from "@/components/privacy/PrivacyPolicyContent";
import { cn } from "@/lib/cn";
import { PRIVACY_POLICY_VERSION } from "@/lib/privacy-policy";
import { Shield } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

export type PrivacyPolicyAcceptStepProps = {
  onAccept: () => void;
  onDecline: () => void;
  loading?: boolean;
};

export function PrivacyPolicyAcceptStep({
  onAccept,
  onDecline,
  loading,
}: PrivacyPolicyAcceptStepProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [scrolledToEnd, setScrolledToEnd] = useState(false);
  const [checked, setChecked] = useState(false);

  const markScrollComplete = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const noOverflow = el.scrollHeight <= el.clientHeight + 12;
    const atEnd = el.scrollTop + el.clientHeight >= el.scrollHeight - 12;
    if (noOverflow || atEnd) setScrolledToEnd(true);
  }, []);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    markScrollComplete();
    const observer = new ResizeObserver(() => markScrollComplete());
    observer.observe(el);
    return () => observer.disconnect();
  }, [markScrollComplete]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-landing-border/80">
        <Shield className="h-4 w-4 text-landing-cta shrink-0" aria-hidden />
        <div>
          <p className="text-sm font-medium text-landing-text">นโยบายความเป็นส่วนตัว</p>
          <p className="text-xs text-landing-muted mt-0.5">
            อ่านจนจบก่อนยอมรับ · v{PRIVACY_POLICY_VERSION}
          </p>
        </div>
      </div>

      <div
        ref={scrollRef}
        onScroll={markScrollComplete}
        className={cn(
          "max-h-[280px] overflow-y-auto gemini-scrollbar rounded-md",
          "border border-landing-border",
          "bg-landing-bg px-4 py-3"
        )}
      >
        <PrivacyPolicyContent showHeader={false} />
      </div>

      <label
        className={cn(
          "flex items-start gap-2.5 text-sm cursor-pointer select-none",
          !scrolledToEnd && "opacity-50 cursor-not-allowed"
        )}
      >
        <input
          type="checkbox"
          className="mt-0.5 rounded border-landing-border"
          disabled={!scrolledToEnd || loading}
          checked={checked}
          onChange={(e) => setChecked(e.target.checked)}
        />
        <span className="text-landing-text">
          ข้าพเจ้าได้อ่านและยอมรับนโยบายความเป็นส่วนตัวฉบับนี้
        </span>
      </label>

      <button
        type="button"
        disabled={!checked || loading}
        onClick={onAccept}
        className={cn(
          "w-full h-10 rounded-md text-sm font-semibold text-white gemini-focus-ring landing-btn-cta",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      >
        {loading ? "กำลังบันทึก…" : "ยอมรับและดำเนินการต่อ"}
      </button>

      <button
        type="button"
        disabled={loading}
        onClick={onDecline}
        className={cn(
          "w-full h-10 rounded-md text-sm font-medium gemini-focus-ring landing-btn-outline",
          "text-landing-muted",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      >
        ไม่ยอมรับ
      </button>
    </div>
  );
}
