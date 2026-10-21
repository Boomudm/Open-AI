"use client";

import { cn } from "@/lib/cn";
import { LOCALE_LABELS, type Locale } from "@/lib/i18n/types";
import { useLocale } from "@/providers/LocaleProvider";

const LOCALES: Locale[] = ["th", "en"];

type LanguageSwitcherProps = {
  className?: string;
  ariaLabel?: string;
};

export function LanguageSwitcher({ className, ariaLabel }: LanguageSwitcherProps) {
  const { locale, setLocale } = useLocale();

  return (
    <div
      className={cn(
        "inline-flex min-h-12 items-stretch rounded-md border border-landing-border p-1",
        className
      )}
      role="group"
      aria-label={ariaLabel ?? "Change language"}
    >
      {LOCALES.map((code) => (
        <button
          key={code}
          type="button"
          onClick={() => setLocale(code)}
          aria-pressed={locale === code}
          className={cn(
            "landing-lang-btn rounded-[5px] font-semibold transition-colors",
            locale === code
              ? "bg-landing-cta text-white shadow-sm"
              : "text-landing-muted hover:text-landing-text hover:bg-landing-surface"
          )}
        >
          {LOCALE_LABELS[code]}
        </button>
      ))}
    </div>
  );
}
