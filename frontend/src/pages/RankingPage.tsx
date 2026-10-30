import { useMutation, useQueryClient } from "@tanstack/react-query";
import { CircleDollarSign, Eye } from "lucide-react";
import { useState } from "react";

import { PeriodFilter, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { useAuth } from "@/features/auth/AuthProvider";
import { RevenueRankingList, ViewsRankingList } from "@/features/rankings/RankingLists";
import { apiRequest, type User } from "@/services/api";

/** Each user decides whether their name shows in the platform rankings. */
function HideFromRankings() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const save = useMutation({
    mutationFn: (hide: boolean) =>
      apiRequest<User>("/api/profile/preferences", { method: "PATCH", body: { hide_from_rankings: hide } }),
    onSuccess: (updated) => {
      cache.setQueryData(["auth", "me"], updated);
      cache.setQueryData(["profile"], updated);
      void cache.invalidateQueries({ queryKey: ["rankings"] });
    },
  });
  return (
    <label className="flex items-center gap-2 text-xs text-muted">
      <input
        checked={Boolean(user?.hide_from_rankings)}
        className="size-4 accent-[var(--color-accent)]"
        disabled={save.isPending}
        onChange={(event) => save.mutate(event.target.checked)}
        type="checkbox"
      />
      Não aparecer nos rankings
    </label>
  );
}

type Tab = "views" | "revenue";

/** Two rankings only: views (everyone) and revenue (Super Admin). */
export function RankingPage() {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  const [tab, setTab] = useState<Tab>("views");
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  const tabs: { value: Tab; label: string; icon: typeof Eye }[] = [
    { value: "views", label: "Ranking de Visualizações", icon: Eye },
    ...(isSuperAdmin ? [{ value: "revenue" as const, label: "Ranking de Faturamento", icon: CircleDollarSign }] : []),
  ];
  const active = isSuperAdmin ? tab : "views";

  return (
    <div className="mx-auto max-w-[1320px] space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">Rankings</h1>
        <HideFromRankings />
      </header>

      {tabs.length > 1 && (
        <div aria-label="Tipo de ranking" className="inline-flex gap-1 rounded-full bg-well p-1" role="tablist">
          {tabs.map(({ value, label, icon: Icon }) => (
            <button
              aria-selected={active === value}
              className={`inline-flex min-h-9 items-center gap-2 rounded-full px-4 text-xs font-medium ${active === value ? "bg-brand text-white" : "text-muted"}`}
              key={value}
              onClick={() => setTab(value)}
              role="tab"
              type="button"
            >
              <Icon size={14} /> {label}
            </button>
          ))}
        </div>
      )}

      <PeriodFilter onChange={setPeriod} value={period} />

      <section className="dashboard-card rounded-xl p-4 sm:p-5">
        <h2 className="mb-4 font-semibold text-fg">
          {active === "views" ? "Usuários do Flash com mais visualizações" : "Usuários do Flash que mais faturaram"}
        </h2>
        {active === "views" ? <ViewsRankingList period={period} /> : <RevenueRankingList period={period} />}
      </section>
    </div>
  );
}
