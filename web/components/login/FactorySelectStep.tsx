"use client";

import { cn } from "@/lib/cn";
import type { FactoryBrief } from "@/lib/api";
import { Building2, Check } from "lucide-react";

export type FactorySelectStepProps = {
  factories: FactoryBrief[];
  value: string[];
  onChange: (factoryIds: string[]) => void;
  onContinue: () => void;
  loading?: boolean;
};

export function FactorySelectStep({
  factories,
  value,
  onChange,
  onContinue,
  loading,
}: FactorySelectStepProps) {
  const selectedCount = value.length;

  function toggleFactory(factoryId: string) {
    onChange(
      value.includes(factoryId)
        ? value.filter((id) => id !== factoryId)
        : [...value, factoryId]
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 pb-2 border-b border-landing-border/80">
        <Building2 className="h-4 w-4 text-landing-cta shrink-0" aria-hidden />
        <div>
          <p className="text-sm font-medium text-landing-text">Select factories</p>
          <p className="text-xs text-landing-muted mt-0.5">
            เลือกได้หลายโรงงาน · {factories.length} sites available
          </p>
        </div>
      </div>

      <ul className="space-y-1.5 max-h-52 overflow-y-auto" role="listbox" aria-multiselectable>
        {factories.map((f) => {
          const active = value.includes(f.factory_id);
          return (
            <li key={f.factory_id}>
              <button
                type="button"
                role="option"
                aria-selected={active}
                onClick={() => toggleFactory(f.factory_id)}
                className={cn(
                  "w-full text-left px-3 py-2.5 rounded-md transition-colors gemini-focus-ring",
                  "border text-sm flex items-start gap-3",
                  active
                    ? "border-landing-cta/40 bg-landing-cta/10 text-landing-text"
                    : "border-landing-border bg-landing-bg text-landing-text hover:bg-landing-surface"
                )}
              >
                <span
                  className={cn(
                    "mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                    active
                      ? "border-landing-cta bg-landing-cta text-white"
                      : "border-landing-border bg-landing-bg"
                  )}
                  aria-hidden
                >
                  {active && <Check className="h-3 w-3" strokeWidth={3} />}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="font-medium tabular-nums">{f.factory_id}</span>
                  <span className="block text-xs text-landing-muted mt-0.5 truncate">
                    {f.factory_name}
                  </span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>

      <p className="text-xs text-landing-muted">
        {selectedCount > 0
          ? `เลือกแล้ว ${selectedCount} โรงงาน`
          : "เลือกอย่างน้อย 1 โรงงานเพื่อดำเนินการต่อ"}
      </p>

      <button
        type="button"
        disabled={selectedCount === 0 || loading}
        onClick={onContinue}
        className={cn(
          "w-full h-10 rounded-md text-sm font-semibold text-white transition-colors gemini-focus-ring landing-btn-cta",
          "disabled:opacity-50 disabled:cursor-not-allowed"
        )}
      >
        {loading ? "Please wait…" : "Continue"}
      </button>
    </div>
  );
}
