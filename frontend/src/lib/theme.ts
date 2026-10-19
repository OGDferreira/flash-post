import { applyAccent, getAccent } from "@/lib/appearance";

export type Theme = "dark" | "light";
const KEY = "flashpost-theme";

export function getTheme(): Theme {
  return document.documentElement.dataset.theme === "light" ? "light" : "dark";
}

export function applyTheme(theme: Theme, animate = false) {
  const root = document.documentElement;
  if (animate) {
    root.classList.add("theme-switching");
    window.setTimeout(() => root.classList.remove("theme-switching"), 260);
  }
  root.dataset.theme = theme;
  applyAccent(getAccent(), theme);
  // Other screens (e.g. Aparência turning on the galaxy theme) may switch it; the header follows.
  window.dispatchEvent(new CustomEvent("flashpost:theme", { detail: theme }));
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "light" ? "#e9eefc" : "#05070f");
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* storage unavailable: the cookie below still remembers it */
  }
  // Cookie backup: survives cleared site data on some browsers and PWAs.
  document.cookie = `${KEY}=${theme}; max-age=31536000; path=/; SameSite=Lax`;
}

/** Saved choice (localStorage first, cookie second); null if the user never chose. */
export function getStoredTheme(): Theme | null {
  try {
    const value = localStorage.getItem(KEY);
    if (value === "light" || value === "dark") return value;
  } catch {
    /* ignore */
  }
  const match = document.cookie.match(new RegExp(`(?:^|; )${KEY}=(light|dark)`));
  return match ? (match[1] as Theme) : null;
}
