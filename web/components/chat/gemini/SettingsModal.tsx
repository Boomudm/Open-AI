"use client";

import { useTheme } from "@/hooks/useTheme";
import { cn } from "@/lib/cn";
import {
  RAG_SOURCE_DEFINITIONS,
  type ChatSettings,
  type LlmModelChoice,
} from "@/lib/chatSettings";
import type { ThemePreference } from "@/lib/theme";
import { OfflineSettingsSection } from "@/components/offline/OfflineSettingsSection";
import { PwaInstallSection } from "@/components/offline/PwaInstallSection";
import { ClientPortal } from "@/components/ui/ClientPortal";
import { Tooltip } from "@/components/ui/Tooltip";
import { Z_OVERLAY_BACKDROP, Z_OVERLAY_PANEL } from "@/lib/overlay-z-index";
import { BookOpen, Cpu, History, Monitor, Moon, Sun, X } from "lucide-react";
import { useEffect, type ReactNode } from "react";
import { GeminiToggle } from "./GeminiToggle";

export type SettingsModalProps = {
  open: boolean;
  onClose: () => void;
  settings: ChatSettings;
  onSettingsChange: (patch: Partial<ChatSettings>) => void;
  onRagSourceToggle: (id: string, enabled: boolean) => void;
  themePreference: ThemePreference;
  onThemePreferenceChange: (pref: ThemePreference) => void;
  serverModel?: string | null;
  serverProfile?: string | null;
  topKFast?: number | null;
  topKAdvanced?: number | null;
};

function modelOptions(topKFast = 6, topKAdvanced = 10): {
  id: LlmModelChoice;
  title: string;
  subtitle: string;
  detail: string;
}[] {
  return [
    {
      id: "fast",
      title: "ค้นหาเร็ว",
      subtitle: `top_k = ${topKFast}`,
      detail: "ดึงเอกสารอ้างอิงน้อยลง — ตอบเร็วขึ้น",
    },
    {
      id: "advanced",
      title: "ค้นหาละเอียด",
      subtitle: `top_k = ${topKAdvanced}`,
      detail: "ดึงเอกสารอ้างอิงมากขึ้น — เหมาะกับคำถามซับซ้อน",
    },
  ];
}

const THEME_OPTIONS: {
  id: ThemePreference;
  label: string;
  icon: ReactNode;
}[] = [
  { id: "light", label: "สว่าง", icon: <Sun className="h-4 w-4" /> },
  { id: "dark", label: "มืด", icon: <Moon className="h-4 w-4" /> },
  { id: "system", label: "ตามระบบ", icon: <Monitor className="h-4 w-4" /> },
];

export function SettingsModal({
  open,
  onClose,
  settings,
  onSettingsChange,
  onRagSourceToggle,
  themePreference,
  onThemePreferenceChange,
  serverModel,
  serverProfile,
  topKFast,
  topKAdvanced,
}: SettingsModalProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <ClientPortal>
    <div
      className="fixed inset-0 flex items-center justify-center p-4"
      style={{ zIndex: Z_OVERLAY_PANEL }}
    >
      <button
        type="button"
        aria-label="ปิดการตั้งค่า"
        className="absolute inset-0 bg-black/40 backdrop-blur-sm gemini-theme-transition"
        style={{ zIndex: Z_OVERLAY_BACKDROP }}
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="gemini-settings-title"
        className={cn(
          "relative w-full max-w-lg max-h-[min(90vh,720px)] flex flex-col gemini-theme-transition",
          "rounded-3xl overflow-hidden shadow-gemini-input-dark",
          "bg-gemini-bg dark:bg-gemini-dark-bg",
          "border border-gemini-border/70 dark:border-gemini-dark-border/70"
        )}
        style={{ zIndex: Z_OVERLAY_PANEL }}
      >
        <header className="shrink-0 flex items-center justify-between px-5 py-4 border-b border-gemini-border/60 dark:border-gemini-dark-border/60">
          <h2
            id="gemini-settings-title"
            className="text-base font-medium text-gemini-text dark:text-gemini-dark-text"
          >
            ตั้งค่า
          </h2>
          <Tooltip content="ปิดการตั้งค่า">
            <button
              type="button"
              onClick={onClose}
              className="h-9 w-9 flex items-center justify-center rounded-full gemini-theme-transition gemini-focus-ring text-gemini-muted dark:text-gemini-dark-muted hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
              aria-label="ปิด"
            >
              <X className="h-4 w-4" />
            </button>
          </Tooltip>
        </header>

        <div className="flex-1 min-h-0 overflow-y-auto gemini-scrollbar px-5 py-4 space-y-6">
          <SettingsSection title="เลือกโมเดล" icon={<Cpu className="h-4 w-4" />}>
            {(serverModel || serverProfile) && (
              <p className="text-xs text-gemini-muted dark:text-gemini-dark-muted mb-2">
                Model บนเซิร์ฟเวอร์:{" "}
                <span className="text-gemini-text dark:text-gemini-dark-text">
                  {serverModel ?? "—"}
                </span>
                {serverProfile ? ` (${serverProfile})` : ""}
              </p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {modelOptions(topKFast ?? 6, topKAdvanced ?? 10).map((opt) => {
                const active = settings.model === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => onSettingsChange({ model: opt.id })}
                    className={cn(
                      "text-left p-3 rounded-2xl gemini-theme-transition gemini-focus-ring",
                      "border transition-all duration-200",
                      active
                        ? "border-gemini-blue/50 dark:border-gemini-dark-blue/50 bg-gemini-active dark:bg-gemini-dark-active"
                        : "border-gemini-border/70 dark:border-gemini-dark-border/70 bg-gemini-surface dark:bg-gemini-dark-surface hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
                    )}
                  >
                    <p className="text-sm font-medium text-gemini-text dark:text-gemini-dark-text">
                      {opt.title}
                    </p>
                    <p className="text-xs text-gemini-blue dark:text-gemini-dark-blue mt-0.5">
                      {opt.subtitle}
                    </p>
                    <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-1.5 leading-snug">
                      {opt.detail}
                    </p>
                  </button>
                );
              })}
            </div>
          </SettingsSection>

          <SettingsSection title="ส่วนขยาย RAG" icon={<BookOpen className="h-4 w-4" />}>
            <ul className="space-y-2">
              {RAG_SOURCE_DEFINITIONS.map((source) => (
                <li
                  key={source.id}
                  className={cn(
                    "flex items-center gap-3 p-3 rounded-2xl gemini-theme-transition",
                    "bg-gemini-surface dark:bg-gemini-dark-surface",
                    "border border-gemini-border/60 dark:border-gemini-dark-border/60"
                  )}
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
                      {source.label}
                    </p>
                    <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
                      {source.description}
                    </p>
                  </div>
                  <GeminiToggle
                    checked={settings.ragSources[source.id] !== false}
                    onChange={(v) => onRagSourceToggle(source.id, v)}
                    aria-label={`เปิด/ปิด ${source.label}`}
                  />
                </li>
              ))}
            </ul>
          </SettingsSection>

          <SettingsSection title="กิจกรรมแชท" icon={<History className="h-4 w-4" />}>
            <div
              className={cn(
                "flex items-center justify-between gap-3 p-3 rounded-2xl gemini-theme-transition",
                "bg-gemini-surface dark:bg-gemini-dark-surface",
                "border border-gemini-border/60 dark:border-gemini-dark-border/60"
              )}
            >
              <div>
                <p className="text-sm text-gemini-text dark:text-gemini-dark-text">
                  บันทึกประวัติแชท
                </p>
                <p className="text-[11px] text-gemini-muted dark:text-gemini-dark-muted mt-0.5">
                  เก็บบทสนทนาไว้ในแถบด้านข้างเพื่อกลับมาดูภายหลัง
                </p>
              </div>
              <GeminiToggle
                checked={settings.saveChatHistory}
                onChange={(v) => onSettingsChange({ saveChatHistory: v })}
                aria-label="บันทึกประวัติแชท"
              />
            </div>
          </SettingsSection>

          <OfflineSettingsSection />

          <PwaInstallSection />

          <SettingsSection title="ธีม" icon={<Sun className="h-4 w-4" />}>
            <div className="grid grid-cols-3 gap-2">
              {THEME_OPTIONS.map((opt) => {
                const active = themePreference === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => onThemePreferenceChange(opt.id)}
                    className={cn(
                      "flex flex-col items-center gap-1.5 py-3 px-2 rounded-2xl gemini-theme-transition gemini-focus-ring",
                      "border text-xs font-medium transition-all duration-200",
                      active
                        ? "border-gemini-blue/50 dark:border-gemini-dark-blue/50 bg-gemini-active dark:bg-gemini-dark-active text-gemini-text dark:text-gemini-dark-text"
                        : "border-gemini-border/70 dark:border-gemini-dark-border/70 bg-gemini-surface dark:bg-gemini-dark-surface text-gemini-muted dark:text-gemini-dark-muted hover:bg-gemini-hover dark:hover:bg-gemini-dark-hover"
                    )}
                  >
                    {opt.icon}
                    {opt.label}
                  </button>
                );
              })}
            </div>
          </SettingsSection>
        </div>
      </div>
    </div>
    </ClientPortal>
  );
}

function SettingsSection({
  title,
  icon,
  children,
}: {
  title: string;
  icon: ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section>
      <div className="flex items-center gap-2 mb-3">
        <span className="text-gemini-muted dark:text-gemini-dark-muted">{icon}</span>
        <h3 className="text-xs font-medium uppercase tracking-wide text-gemini-muted dark:text-gemini-dark-muted">
          {title}
        </h3>
      </div>
      {children}
    </section>
  );
}
