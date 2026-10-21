"use client";

import { usePwaInstall } from "@/hooks/usePwaInstall";
import { cn } from "@/lib/cn";
import { Download, Smartphone } from "lucide-react";

export function PwaInstallSection() {
  const { canInstall, isInstalled, isIos, installing, install } = usePwaInstall();

  if (isInstalled) {
    return (
      <section>
        <div className="flex items-center gap-2 mb-3">
          <Smartphone className="h-4 w-4 text-gemini-muted dark:text-gemini-dark-muted" />
          <h3 className="text-xs font-medium uppercase tracking-wide text-gemini-muted dark:text-gemini-dark-muted">
            Install app
          </h3>
        </div>
        <div
          className={cn(
            "p-3 rounded-2xl gemini-theme-transition",
            "bg-gemini-surface dark:bg-gemini-dark-surface",
            "border border-gemini-border/60 dark:border-gemini-dark-border/60"
          )}
        >
          <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
            ติดตั้งแอปแล้ว — เปิดจากไอคอนบนหน้าจอหลักได้
          </p>
        </div>
      </section>
    );
  }

  if (!canInstall) return null;

  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <Smartphone className="h-4 w-4 text-gemini-muted dark:text-gemini-dark-muted" />
        <h3 className="text-xs font-medium uppercase tracking-wide text-gemini-muted dark:text-gemini-dark-muted">
          Install app
        </h3>
      </div>
      <div
        className={cn(
          "p-3 rounded-2xl gemini-theme-transition space-y-2",
          "bg-gemini-surface dark:bg-gemini-dark-surface",
          "border border-gemini-border/60 dark:border-gemini-dark-border/60"
        )}
      >
        {isIos ? (
          <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
            Safari: แตะ <strong>Share</strong> → <strong>Add to Home Screen</strong> เพื่อติดตั้ง Neo Chat บนหน้าจอหลัก
          </p>
        ) : (
          <>
            <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
              ติดตั้ง Neo Chat เป็นแอปบนแท็บเล็ตหรือมือถือ — ใช้งานหน้างานได้สะดวกขึ้น
            </p>
            <button
              type="button"
              onClick={() => void install()}
              disabled={installing || !canInstall}
              className={cn(
                "inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium",
                "bg-gemini-blue dark:bg-gemini-dark-blue text-white",
                "hover:opacity-90 disabled:opacity-50 gemini-focus-ring"
              )}
            >
              <Download className="h-4 w-4" />
              {installing ? "กำลังติดตั้ง…" : "ติดตั้งแอป"}
            </button>
          </>
        )}
      </div>
    </section>
  );
}
