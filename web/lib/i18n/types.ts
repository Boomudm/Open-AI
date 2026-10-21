export type Locale = "th" | "en";

export const DEFAULT_LOCALE: Locale = "th";

export const LOCALE_STORAGE_KEY = "spark-locale";

export const LOCALE_LABELS: Record<Locale, string> = {
  th: "ไทย",
  en: "EN",
};
