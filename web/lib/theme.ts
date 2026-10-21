export type Theme = "dark" | "light";
export type ThemePreference = "light" | "dark" | "system";

export const THEME_STORAGE_KEY = "spark_theme";
export const THEME_PREFERENCE_KEY = "spark_theme_preference";

export function resolveThemePreference(pref: ThemePreference): Theme {
  if (typeof window === "undefined") return pref === "light" ? "light" : "dark";
  if (pref === "system") {
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }
  return pref;
}

export function getStoredThemePreference(): ThemePreference {
  if (typeof window === "undefined") return "dark";
  const stored = localStorage.getItem(THEME_PREFERENCE_KEY);
  if (stored === "light" || stored === "dark" || stored === "system") return stored;
  const legacy = localStorage.getItem(THEME_STORAGE_KEY);
  return legacy === "light" ? "light" : "dark";
}

export function getStoredTheme(): Theme {
  return resolveThemePreference(getStoredThemePreference());
}

export function applyTheme(theme: Theme): void {
  document.documentElement.setAttribute("data-theme", theme);
  document.documentElement.style.colorScheme = theme;
  document.documentElement.classList.toggle("dark", theme === "dark");
  localStorage.setItem(THEME_STORAGE_KEY, theme);
  window.dispatchEvent(new CustomEvent("spark-theme-change", { detail: { theme } }));
}

export function applyThemePreference(pref: ThemePreference): Theme {
  const resolved = resolveThemePreference(pref);
  localStorage.setItem(THEME_PREFERENCE_KEY, pref);
  applyTheme(resolved);
  window.dispatchEvent(
    new CustomEvent("spark-theme-preference-change", { detail: { preference: pref, theme: resolved } })
  );
  return resolved;
}

export function toggleTheme(current: Theme): Theme {
  const next: Theme = current === "dark" ? "light" : "dark";
  applyThemePreference(next);
  return next;
}

export const themeInitScript = `(function(){try{var p=localStorage.getItem('${THEME_PREFERENCE_KEY}');if(!p){p=localStorage.getItem('${THEME_STORAGE_KEY}')==='light'?'light':'dark';}var t=p==='system'?(window.matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'):(p==='light'?'light':'dark');document.documentElement.setAttribute('data-theme',t);document.documentElement.style.colorScheme=t;document.documentElement.classList.toggle('dark',t==='dark');}catch(e){}})();`;
