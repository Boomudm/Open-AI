"use client";

import { getStoredLocale, setStoredLocale } from "@/lib/i18n/locale";
import { getLandingMessages, type LandingMessages } from "@/lib/i18n/landing";
import { DEFAULT_LOCALE, type Locale } from "@/lib/i18n/types";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

type LocaleContextValue = {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  landing: LandingMessages;
};

const LocaleContext = createContext<LocaleContextValue | null>(null);

export function LocaleProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE);

  useEffect(() => {
    const stored = getStoredLocale();
    setLocaleState(stored);
    document.documentElement.lang = stored;
  }, []);

  useEffect(() => {
    const onLocale = (e: Event) => {
      const detail = (e as CustomEvent<{ locale: Locale }>).detail;
      if (detail?.locale) setLocaleState(detail.locale);
    };
    window.addEventListener("spark-locale-change", onLocale);
    return () => window.removeEventListener("spark-locale-change", onLocale);
  }, []);

  const setLocale = useCallback((next: Locale) => {
    setStoredLocale(next);
    setLocaleState(next);
  }, []);

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      landing: getLandingMessages(locale),
    }),
    [locale, setLocale]
  );

  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useLocale must be used within LocaleProvider");
  return ctx;
}

export function useLandingMessages() {
  return useLocale().landing;
}
