"use client";

import { GeminiToggle } from "@/components/chat/gemini/GeminiToggle";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useOfflineSync } from "@/hooks/useOfflineSync";
import { clearAllOfflineCache } from "@/lib/offline/sync-manager";
import { DEFAULT_OFFLINE_PREFS, type OfflinePrefs } from "@/lib/offline/config";
import { getOfflinePrefs, setOfflinePrefs } from "@/lib/offline/prefs";
import { cn } from "@/lib/cn";
import { HardDrive, Trash2 } from "lucide-react";
import { useCallback, useEffect, useState } from "react";

function formatMb(bytes: number): string {
  return (bytes / (1024 * 1024)).toFixed(1);
}

export function OfflineSettingsSection() {
  const { status, triggerSync } = useOfflineSync();
  const [prefs, setPrefs] = useState<OfflinePrefs>({});
  const [clearing, setClearing] = useState(false);
  const [clearConfirmOpen, setClearConfirmOpen] = useState(false);

  useEffect(() => {
    void getOfflinePrefs().then(setPrefs);
  }, []);

  const wifiOnly = prefs.prefetchWifiOnly ?? DEFAULT_OFFLINE_PREFS.prefetchWifiOnly;

  const updatePrefs = useCallback(async (patch: Partial<OfflinePrefs>) => {
    const next = await setOfflinePrefs(patch);
    setPrefs(next);
  }, []);

  const handleClear = async () => {
    setClearing(true);
    try {
      await clearAllOfflineCache();
      triggerSync();
    } finally {
      setClearing(false);
      setClearConfirmOpen(false);
    }
  };

  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <HardDrive className="h-4 w-4 text-gemini-muted dark:text-gemini-dark-muted" />
        <h3 className="text-xs font-medium uppercase tracking-wide text-gemini-muted dark:text-gemini-dark-muted">
          Offline storage
        </h3>
      </div>
      <div className="space-y-2">
        <div
          className={cn(
            "p-3 rounded-2xl gemini-theme-transition",
            "bg-gemini-surface dark:bg-gemini-dark-surface",
            "border border-gemini-border/60 dark:border-gemini-dark-border/60"
          )}
        >
          <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
            {status.cachedDocsCount} ไฟล์ · {formatMb(status.cachedBytes)} / {formatMb(status.cacheMaxBytes)} MB
          </p>
          <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-1">
            เอกสารที่เปิดหรือ prefetch ไว้สำหรับใช้ออฟไลน์
          </p>
        </div>

        <div
          className={cn(
            "flex items-center justify-between gap-3 p-3 rounded-2xl gemini-theme-transition",
            "bg-gemini-surface dark:bg-gemini-dark-surface",
            "border border-gemini-border/60 dark:border-gemini-dark-border/60"
          )}
        >
          <div>
            <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
              Prefetch เฉพาะ Wi‑Fi
            </p>
            <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
              ดาวน์โหลดล่วงหน้าเฉพาะเมื่อเชื่อม Wi‑Fi
            </p>
          </div>
          <GeminiToggle
            checked={wifiOnly}
            onChange={(v) => updatePrefs({ prefetchWifiOnly: v })}
            aria-label="Prefetch Wi-Fi only"
          />
        </div>

        <button
          type="button"
          onClick={() => setClearConfirmOpen(true)}
          disabled={clearing || status.cachedDocsCount === 0}
          className={cn(
            "w-full flex items-center justify-center gap-2 p-3 rounded-2xl text-sm gemini-theme-transition",
            "border border-gemini-border/60 dark:border-gemini-dark-border/60",
            "text-red-600 dark:text-red-400 hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover",
            "disabled:opacity-50 disabled:cursor-not-allowed"
          )}
        >
          <Trash2 className="h-4 w-4" />
          {clearing ? "กำลังล้าง…" : "ล้าง cache ออฟไลน์"}
        </button>
      </div>

      <ConfirmDialog
        open={clearConfirmOpen}
        onClose={() => setClearConfirmOpen(false)}
        onConfirm={() => void handleClear()}
        title="ล้าง cache ออฟไลน์?"
        message="ล้างเอกสารที่บันทึกไว้ในเครื่องทั้งหมด?"
        confirmLabel="ล้างทั้งหมด"
        cancelLabel="ยกเลิก"
        destructive
        loading={clearing}
      />
    </section>
  );
}
