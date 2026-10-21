"use client";

import { cn } from "@/lib/cn";

export type GeminiToggleProps = {
  checked: boolean;
  onChange: (checked: boolean) => void;
  disabled?: boolean;
  "aria-label": string;
};

export function GeminiToggle({
  checked,
  onChange,
  disabled,
  "aria-label": ariaLabel,
}: GeminiToggleProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cn(
        "relative shrink-0 w-11 h-6 rounded-full gemini-theme-transition gemini-focus-ring",
        "transition-colors duration-200 ease-in-out",
        checked
          ? "bg-gemini-blue dark:bg-gemini-dark-blue"
          : "bg-gemini-border dark:bg-gemini-dark-border",
        disabled && "opacity-50 cursor-not-allowed"
      )}
    >
      <span
        className={cn(
          "absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white shadow-sm",
          "transition-transform duration-200 ease-in-out",
          checked && "translate-x-5"
        )}
      />
    </button>
  );
}
