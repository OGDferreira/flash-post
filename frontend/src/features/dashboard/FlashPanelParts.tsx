import { useQuery } from "@tanstack/react-query";
import { UserRoundCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";

import { isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { apiRequest } from "@/services/api";

const count = (value: number) => new Intl.NumberFormat("pt-BR").format(value);
const brl = (value: number) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);

/** "Contas Conectadas": current connected/disconnected accounts, one list at a time. */
export function ConnectedAccountsCard({ summary }: { summary: InstagramAnalyticsSummary | undefined }) {
  const [view, setView] = useState<"connected" | "disconnected">("connected");
  const accounts = summary?.accounts ?? [];
  const connected = accounts.filter(({ status }) => status === "connected");
  const disconnected = accounts.filter(({ status }) => status !== "connected");
  const shown = view === "connected" ? connected : disconnected;
  return (
    <article className="dashboard-card flex h-full min-h-[280px] flex-col gap-3 rounded-xl p-4">
      <h2 className="flex items-center gap-2 text-base font-semibold text-fg">
        <UserRoundCheck aria-hidden="true" className="text-accent" size={18} /> Contas Conectadas
      </h2>
      <div aria-label="Exibir contas" className="grid grid-cols-2 gap-1 rounded-full bg-well p-1" role="tablist">
        {([
          ["connected", "Conectadas", connected.length],
          ["disconnected", "Desconectadas", disconnected.length],
        ] as const).map(([value, label, total]) => (
          <button
            aria-selected={view === value}
            className={`min-h-8 rounded-full px-3 text-xs font-medium ${view === value ? "bg-brand text-white" : "text-muted"}`}
            key={value}
            onClick={() => setView(value)}
            role="tab"
            type="button"
          >
            {label} ({total})
          </button>
        ))}
      </div>
      {/* The list scrolls inside the card, so the card follows the height of the cards beside it. */}
      <div className="relative min-h-[160px] flex-1">
        <ul className="absolute inset-0 space-y-1.5 overflow-y-auto pr-1">
          {shown.map((account) => (
            <li className="flex items-center gap-2 rounded-lg bg-surface-inset px-3 py-2 text-xs" key={account.account_id}>
              <span className={`size-2 shrink-0 rounded-full ${view === "connected" ? "bg-success" : "bg-danger"}`} />
              <span className="truncate text-fg">@{account.username}</span>
            </li>
          ))}
          {shown.length === 0 && (
            <li className="px-1 text-xs text-muted">
              {view === "connected" ? "Nenhuma conta conectada." : "Nenhuma conta desconectada."}
            </li>
          )}
        </ul>
      </div>
      <Link className="text-xs font-medium text-accent hover:underline" to="/feature/accounts">
        Ver e gerenciar contas →
      </Link>
    </article>
  );
}

type Totals = { views: number; sales: number; revenue: number };
type Performance = {
  comparison: { current: Totals; previous: Totals } | null;
  days: { day: string; views: number; revenue: number }[];
};

export function usePerformance(period: MetricsPeriod) {
  const params = new URLSearchParams(periodParams(period));
  return useQuery({
    queryKey: ["analytics", "performance", params.toString()],
    queryFn: () => apiRequest<Performance>(`/api/analytics/performance?${params}`),
    enabled: isPeriodReady(period),
    retry: false,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
}

/** "+12% vs. período anterior" (same length, just before). */
export function ComparisonBadge({ current, previous }: { current: number; previous: number }) {
  if (previous <= 0 && current <= 0) return null;
  const change = previous > 0 ? Math.round(((current - previous) / previous) * 100) : null;
  const up = change === null || change >= 0;
  return (
    <p className={`text-[11px] font-medium ${change === 0 ? "text-muted" : up ? "text-success" : "text-danger"}`}>
      {change === null ? "novo" : `${change > 0 ? "+" : ""}${change}%`}
      <span className="font-normal text-muted"> vs. período anterior</span>
    </p>
  );
}

const shortDay = (day: string) =>
  new Intl.DateTimeFormat("pt-BR", { day: "2-digit", month: "short", timeZone: "UTC" }).format(new Date(`${day}T00:00:00Z`));

/** Two lines over the same days: views and revenue, each on its own scale. */
export function PerformanceChart({ period }: { period: MetricsPeriod }) {
  const query = usePerformance(period);
  const [hover, setHover] = useState<number | null>(null);
  const days = query.data?.days ?? [];
  const hovered = hover !== null ? days[hover] : undefined;
  const totalViews = days.reduce((sum, { views }) => sum + views, 0);
  const totalRevenue = days.reduce((sum, { revenue }) => sum + revenue, 0);
  const line = (key: "views" | "revenue") => {
    const top = Math.max(...days.map((day) => day[key]), 1);
    return days
      .map((day, index) => `${days.length > 1 ? (index / (days.length - 1)) * 100 : 50},${40 - (day[key] / top) * 34}`)
      .join(" ");
  };
  const series = [
    { key: "views" as const, label: "Visualizações", total: count(totalViews), color: "#8295ff" },
    { key: "revenue" as const, label: "Faturamento", total: brl(totalRevenue), color: "#34d399" },
  ];

  return (
    <article className="dashboard-card flex h-full flex-col rounded-xl p-4">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-accent">Rendimento</p>
      <h2 className="mt-1 text-base font-semibold text-fg">Visualizações e faturamento por dia</h2>
      <ul className="mt-3 flex flex-wrap gap-4">
        {series.map(({ key, label, total, color }) => (
          <li className="flex items-center gap-2 text-xs text-muted" key={key}>
            <span className="h-0.5 w-4 rounded-full" style={{ background: color }} />
            {label} <strong className="text-fg tabular-nums">{total}</strong>
          </li>
        ))}
      </ul>
      {days.length ? (
        <div className="relative mt-4 flex flex-1 flex-col">
          {hovered && (
            <div className="pointer-events-none absolute right-0 top-0 z-10 rounded-lg border border-line-soft bg-surface px-3 py-2 text-[11px] shadow-lg">
              <p className="font-medium text-fg">{shortDay(hovered.day)}</p>
              <p className="text-muted">Visualizações <strong className="text-fg tabular-nums">{count(hovered.views)}</strong></p>
              <p className="text-muted">Faturamento <strong className="text-fg tabular-nums">{brl(hovered.revenue)}</strong></p>
            </div>
          )}
          <svg
            onPointerLeave={() => setHover(null)}
            onPointerMove={(event) => {
              const box = event.currentTarget.getBoundingClientRect();
              const ratio = Math.min(Math.max((event.clientX - box.left) / box.width, 0), 1);
              setHover(Math.round(ratio * (days.length - 1)));
            }}
            aria-label="Gráfico diário de visualizações e faturamento"
            className="min-h-40 w-full flex-1 overflow-visible"
            preserveAspectRatio="none"
            role="img"
            viewBox="0 0 100 44"
          >
            {[6, 23, 40].map((y) => (
              <line key={y} stroke="currentColor" strokeOpacity="0.08" vectorEffect="non-scaling-stroke" x1="0" x2="100" y1={y} y2={y} />
            ))}
            {hover !== null && days.length > 1 && (
              <line
                stroke="currentColor"
                strokeOpacity="0.25"
                vectorEffect="non-scaling-stroke"
                x1={(hover / (days.length - 1)) * 100}
                x2={(hover / (days.length - 1)) * 100}
                y1="2"
                y2="42"
              />
            )}
            {series.map(({ key, color }) => (
              <polyline
                fill="none"
                key={key}
                points={line(key)}
                stroke={color}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                vectorEffect="non-scaling-stroke"
              />
            ))}
          </svg>
          <div className="mt-1 flex justify-between text-[10px] text-muted">
            <span>{shortDay(days[0].day)}</span>
            <span>{shortDay(days[days.length - 1].day)}</span>
          </div>
        </div>
      ) : (
        <p className="mt-4 flex-1 text-sm text-muted">{query.isLoading ? "Carregando…" : "Sem dados no período."}</p>
      )}
    </article>
  );
}
