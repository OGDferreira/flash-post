/** User appearance: main color and motion. Stored per browser, applied on <html>. */
const ACCENT_KEY = "flashpost-accent";
const MOTION_KEY = "flashpost-motion";
const GALAXY_KEY = "flashpost-galaxy";
const LOGO_KEY = "flashpost-flashbot-logo";

export const accentPresets = [
  { name: "Azul", hex: "#1e9cfd" },
  { name: "Roxo", hex: "#8b5cf6" },
  { name: "Rosa", hex: "#ec4899" },
  { name: "Vermelho", hex: "#ef4444" },
  { name: "Laranja", hex: "#f97316" },
  { name: "Verde", hex: "#16a34a" },
  { name: "Ciano", hex: "#06b6d4" },
] as const;
export const DEFAULT_ACCENT = "#1e9cfd";

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}
function write(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: the choice just won't persist */
  }
}

function hexToHue(hex: string): number {
  const n = parseInt(hex.slice(1), 16);
  const r = ((n >> 16) & 255) / 255;
  const g = ((n >> 8) & 255) / 255;
  const b = (n & 255) / 255;
  const max = Math.max(r, g, b);
  const d = max - Math.min(r, g, b);
  if (d === 0) return 220;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return Math.round((h * 60 + 360) % 360);
}

function hsl(h: number, s: number, l: number): string {
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  const f = (n: number) => {
    const k = (n + h / 30) % 12;
    const c = l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
    return Math.round(255 * c)
      .toString(16)
      .padStart(2, "0");
  };
  return `#${f(0)}${f(8)}${f(4)}`;
}

function rgbTriplet(hex: string): string {
  const n = parseInt(hex.slice(1), 16);
  return `${(n >> 16) & 255} ${(n >> 8) & 255} ${n & 255}`;
}

const VARS = ["--brand-c", "--brand-strong-c", "--grad-a", "--grad-b", "--brand-rgb", "--accent", "--tx-accent"];

/** Derives the whole palette from one hue; keeps contrast for bright hues. */
export function applyAccent(hex: string | null, theme: "dark" | "light") {
  const style = document.documentElement.style;
  // The galaxy theme brings its own neon palette (see index.css); a custom color would fight it.
  if (!hex || hex.toLowerCase() === DEFAULT_ACCENT || document.documentElement.dataset.galaxy !== undefined) {
    VARS.forEach((name) => style.removeProperty(name));
    return;
  }
  const h = hexToHue(hex);
  const bright = h >= 45 && h <= 170; // yellow-green hues need darker fills for white text
  const base = hsl(h, 95, bright ? 36 : 62);
  const gradA = hsl(h, 85, bright ? 38 : 60);
  const gradB = hsl(h, 72, bright ? 30 : 52);
  const accent = theme === "light" ? hsl(h, 70, bright ? 28 : 44) : hsl(h, 100, 80);
  style.setProperty("--brand-c", base);
  style.setProperty("--brand-strong-c", hsl(h, 95, bright ? 40 : 68));
  style.setProperty("--grad-a", gradA);
  style.setProperty("--grad-b", gradB);
  style.setProperty("--brand-rgb", rgbTriplet(base));
  style.setProperty("--accent", accent);
  style.setProperty("--tx-accent", accent);
}

export function getAccent(): string {
  return read(ACCENT_KEY) ?? DEFAULT_ACCENT;
}
export function setAccent(hex: string, theme: "dark" | "light") {
  write(ACCENT_KEY, hex.toLowerCase() === DEFAULT_ACCENT ? null : hex);
  applyAccent(hex, theme);
}

export function getMotionOff(): boolean {
  return read(MOTION_KEY) === "off";
}
export function setMotionOff(off: boolean) {
  write(MOTION_KEY, off ? "off" : null);
  if (off) document.documentElement.dataset.motion = "off";
  else delete document.documentElement.dataset.motion;
}

// ------------------------------------------------------------------ galaxy theme + Flash logo
export type FlashBotLogoStyle = "clean" | "galaxy";
const listeners = new Set<() => void>();
const notify = () => listeners.forEach((listener) => listener());
/** For useSyncExternalStore: re-render logos and the appearance card when a choice changes. */
export function subscribeAppearance(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

export function getGalaxy(): boolean {
  return read(GALAXY_KEY) === "on";
}
/** Deep-space dark theme (neon cyan/violet/magenta). Only shows on the dark theme. */
export function setGalaxy(on: boolean, theme: "dark" | "light") {
  write(GALAXY_KEY, on ? "on" : null);
  if (on) document.documentElement.dataset.galaxy = "";
  else delete document.documentElement.dataset.galaxy;
  applyAccent(read(ACCENT_KEY), theme);
  notify();
}

export function getFlashBotLogo(): FlashBotLogoStyle {
  return read(LOGO_KEY) === "galaxy" ? "galaxy" : "clean";
}
export function setFlashBotLogo(style: FlashBotLogoStyle) {
  write(LOGO_KEY, style === "galaxy" ? "galaxy" : null);
  notify();
}

/** Run once before the first render. */
export function initAppearance() {
  if (getMotionOff()) document.documentElement.dataset.motion = "off";
  if (getGalaxy()) document.documentElement.dataset.galaxy = "";
  const theme = document.documentElement.dataset.theme === "light" ? "light" : "dark";
  applyAccent(read(ACCENT_KEY), theme);
}
