"use client";

import {
  applyThemePreference,
  getStoredThemePreference,
  resolveThemePreference,
  type ThemePreference,
} from "@/lib/theme";
import { useCallback, useEffect, useState } from "react";

export function useTheme() {
  const [preference, setPreferenceState] = useState<ThemePreference>("dark");
  const [theme, setTheme] = useState<"dark" | "light">("dark");

  useEffect(() => {
    const pref = getStoredThemePreference();
    setPreferenceState(pref);
    setTheme(resolveThemePreference(pref));

    const onTheme = (e: Event) => {
      const detail = (e as CustomEvent<{ theme: "dark" | "light" }>).detail;
      if (detail?.theme) setTheme(detail.theme);
    };
    const onPref = (e: Event) => {
      const detail = (e as CustomEvent<{ preference: ThemePreference; theme: "dark" | "light" }>)
        .detail;
      if (detail?.preference) setPreferenceState(detail.preference);
      if (detail?.theme) setTheme(detail.theme);
    };
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const onSystem = () => {
      const pref = getStoredThemePreference();
      if (pref === "system") {
        setTheme(resolveThemePreference("system"));
      }
    };

    window.addEventListener("spark-theme-change", onTheme);
    window.addEventListener("spark-theme-preference-change", onPref);
    mq.addEventListener("change", onSystem);
    return () => {
      window.removeEventListener("spark-theme-change", onTheme);
      window.removeEventListener("spark-theme-preference-change", onPref);
      mq.removeEventListener("change", onSystem);
    };
  }, []);

  const toggle = useCallback(() => {
    const nextPref: ThemePreference = theme === "dark" ? "light" : "dark";
    const resolved = applyThemePreference(nextPref);
    setPreferenceState(nextPref);
    setTheme(resolved);
  }, [theme]);

  const setPreference = useCallback((pref: ThemePreference) => {
    const resolved = applyThemePreference(pref);
    setPreferenceState(pref);
    setTheme(resolved);
  }, []);

  return { theme, preference, toggle, setPreference };
}
