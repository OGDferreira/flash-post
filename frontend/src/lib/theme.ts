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
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", theme === "light" ? "#eef2fb" : "#010208");
  try {
    localStorage.setItem(KEY, theme);
  } catch {
    /* storage unavailable: the choice just won't persist */
  }
}
