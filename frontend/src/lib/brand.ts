/** Falcon Post (accounts and publishing) and Falcon Bot (funnels, sales and money): two tools,
 * one login. Paths decide which tool a screen belongs to. */
export type AppId = "post" | "bot";

export const APPS: Record<AppId, { name: string; short: string; home: string; emblem: string; tagline: string }> = {
  post: {
    name: "Falcon Post",
    short: "Post",
    home: "/dashboard",
    emblem: "/brand/falconpost-emblem-256.webp",
    tagline: "Contas, pastas, loops e métricas",
  },
  bot: {
    name: "Falcon Bot",
    short: "Bot",
    home: "/bot",
    emblem: "/brand/falconbot-emblem-256.webp",
    tagline: "Funis, vendas, gateways e comissões",
  },
};

const BOT_PREFIXES = ["/bot", "/carteira", "/feature/affiliates", "/feature/bots"];

export function appForPath(pathname: string): AppId {
  return BOT_PREFIXES.some((prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)) ? "bot" : "post";
}

export const otherApp = (app: AppId): AppId => (app === "bot" ? "post" : "bot");

const LAST_KEY = "falcon-last-path-";

/** Where the switcher sends you back to: the last screen you used in that tool. */
export function rememberPath(app: AppId, path: string) {
  try {
    sessionStorage.setItem(LAST_KEY + app, path);
  } catch {
    /* storage unavailable */
  }
}

export function lastPath(app: AppId): string {
  try {
    const saved = sessionStorage.getItem(LAST_KEY + app);
    if (saved && appForPath(saved) === app) return saved;
  } catch {
    /* storage unavailable */
  }
  return APPS[app].home;
}
