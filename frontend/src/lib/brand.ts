/** Flash: two tools (publishing on Instagram and funnels/sales on Telegram), one login and
 * one brand. Paths decide which tool a screen belongs to. */
export type AppId = "post" | "bot";

export const APPS: Record<AppId, { name: string; short: string; home: string; emblem: string; tagline: string }> = {
  post: {
    name: "Flash",
    short: "Post",
    home: "/dashboard",
    emblem: "/brand/flash-emblem.svg",
    tagline: "Contas, pastas, loops e métricas",
  },
  bot: {
    name: "Flash",
    short: "Bot",
    home: "/bot",
    emblem: "/brand/flash-emblem.svg",
    tagline: "Funis, vendas, gateways e comissões",
  },
};

const BOT_PREFIXES = ["/bot", "/carteira", "/feature/affiliates", "/feature/bots"];

export function appForPath(pathname: string): AppId {
  return BOT_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)) ? "bot" : "post";
}

const isAdminPath = (path: string) => path === "/admin" || path.startsWith("/admin/") || path.startsWith("/admin?");

export const otherApp = (app: AppId): AppId => (app === "bot" ? "post" : "bot");

const LAST_KEY = "falcon-last-path-";

/** Where the switcher sends you back to: the last screen you used in that tool. */
export function rememberPath(app: AppId, path: string) {
  if (isAdminPath(path)) return; // Flash Adm screens belong to neither tool
  try {
    sessionStorage.setItem(LAST_KEY + app, path);
  } catch {
    /* storage unavailable */
  }
}

export function lastPath(app: AppId): string {
  try {
    const saved = sessionStorage.getItem(LAST_KEY + app);
    if (saved && !isAdminPath(saved) && appForPath(saved) === app) return saved;
  } catch {
    /* storage unavailable */
  }
  return APPS[app].home;
}
