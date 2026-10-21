"use client";

import { getStoredLocale } from "@/lib/i18n/locale";
import { useEffect } from "react";

export function HtmlLangSync() {
  useEffect(() => {
    document.documentElement.lang = getStoredLocale();

    const onLocale = (e: Event) => {
      const detail = (e as CustomEvent<{ locale: string }>).detail;
      if (detail?.locale) document.documentElement.lang = detail.locale;
    };
    window.addEventListener("spark-locale-change", onLocale);
    return () => window.removeEventListener("spark-locale-change", onLocale);
  }, []);

  return null;
}
