/**
 * Instant screens: right after login the heavy data of the main screens is fetched in the
 * background (same query keys as the pages), so opening a tab shows it at once instead of
 * starting to load there. Metrics from the Meta API, the slowest, go first.
 */
import { useEffect } from "react";
import { useQueryClient, type QueryClient } from "@tanstack/react-query";

import { apiRequest } from "@/services/api";

type Accounts = { accounts: { id: string; status: string; token_expires_at: string }[] };

const idle = (fn: () => void) => {
  const w = window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => number };
  if (w.requestIdleCallback) w.requestIdleCallback(fn, { timeout: 2500 });
  else window.setTimeout(fn, 800);
};

async function warm(client: QueryClient, app: "post" | "bot") {
  const get = <T,>(url: string) => () => apiRequest<T>(url);
  const prefetch = (queryKey: unknown[], url: string, staleTime = 60_000) =>
    client.prefetchQuery({ queryKey, queryFn: get(url), staleTime }).catch(() => undefined);

  // Falcon Post: the dashboard numbers, the accounts and the Meta metrics of each tab.
  const post = async () => {
    await prefetch(["analytics", "summary", "fast", "today", null, null], "/api/analytics/summary?period=today");
    void prefetch(["analytics", "summary", "meta", "today", null, null], "/api/analytics/summary?period=today&include_meta_insights=true", 5 * 60_000);
    void prefetch(["loops"], "/api/loops?include_accounts=false");
    await prefetch(["instagram", "accounts"], "/api/instagram/accounts");
    const accounts = client.getQueryData<Accounts>(["instagram", "accounts"])?.accounts ?? [];
    const first = accounts.find((a) => a.status === "connected" && Date.parse(a.token_expires_at) > Date.now());
    if (first) {
      // Métricas opens on the first connected account, last 7 days.
      void prefetch(
        ["analytics", "account", first.id, { period: "7d" }],
        `/api/analytics/summary?period=7d&account_ids=${first.id}&include_meta_insights=true`,
      );
    }
  };
  // Falcon Bot: today's panel, the 30-day chart and the wallet.
  const bot = async () => {
    void prefetch(["bots", "stats", { period: "today" }], "/api/bots/stats?period=today", 30_000);
    void prefetch(["bots", "stats", { period: "30d" }], "/api/bots/stats?period=30d", 30_000);
    void prefetch(["wallet", "full"], "/api/wallet");
    void prefetch(["bots"], "/api/bots");
  };
  // The tool on screen first, then the other one.
  if (app === "bot") {
    await bot();
    await post();
  } else {
    await post();
    await bot();
  }
}

/** Starts once per login, when the browser is idle. */
export function useWarmup(enabled: boolean, app: "post" | "bot") {
  const client = useQueryClient();
  useEffect(() => {
    if (!enabled) return;
    idle(() => void warm(client, app));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled]);
}
