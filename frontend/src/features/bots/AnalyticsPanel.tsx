import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3, TrendingUp } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";
import { formatNumber, formatPercent, isPeriodReady, moneyFormat, periodParams, type MetricsPeriod } from "@/features/analytics/period";

type FlowRow = { id: string; name: string; leads: number; sales: number; buyers: number; revenue: number; conversion: number; ticket: number };
type PlanRow = { name: string; sales: number; revenue: number; generated: number; conversion: number };
type Analytics = { period_label: string; funis: FlowRow[]; planos: PlanRow[] };

type SortBy = "sales" | "conversion" | "revenue";
const SORTS: { id: SortBy; label: string }[] = [
  { id: "sales", label: "Mais vendas" },
  { id: "conversion", label: "Melhor conversão" },
  { id: "revenue", label: "Mais faturou" },
];

const key = (sort: SortBy) => (sort === "revenue" ? "revenue" : sort === "conversion" ? "conversion" : "sales");

/** Análises: ranking of the operation's funnels and plans by sales, conversion or revenue. */
export function AnalyticsPanel({ period }: { period: MetricsPeriod }) {
  const [sort, setSort] = useState<SortBy>("sales");
  const analytics = useQuery({
    queryKey: ["bots", "analytics", periodParams(period)],
    queryFn: () => apiRequest<Analytics>(`/api/bots/analytics?${new URLSearchParams(periodParams(period))}`),
    enabled: isPeriodReady(period),
  });

  if (analytics.isLoading) return <LoadingState label="Carregando análises" />;
  if (analytics.error) return <ErrorState message="Não foi possível carregar as análises." onRetry={() => void analytics.refetch()} />;
  const data = analytics.data!;
  const sortRows = <T extends { sales: number; revenue: number; conversion?: number }>(rows: T[]) =>
    [...rows].sort((a, b) => (Number(b[key(sort) as keyof T] ?? 0) as number) - (Number(a[key(sort) as keyof T] ?? 0) as number));
  const funis = sortRows(data.funis);
  const planos = sortRows(data.planos);
  const best = (rows: { revenue: number }[]) => Math.max(1, ...rows.map((r) => r.revenue));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm text-muted">Período: {data.period_label}</p>
        <div className="inline-flex rounded-xl border border-line-soft bg-surface-inset p-0.5 text-xs">
          {SORTS.map((option) => (
            <button
              key={option.id}
              className={`rounded-lg px-2.5 py-1.5 font-medium transition ${sort === option.id ? "bg-brand/15 text-accent" : "text-muted hover:text-fg"}`}
              onClick={() => setSort(option.id)}
              type="button"
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <Ranking
        icon={<BarChart3 size={16} />}
        title="Funis que mais venderam"
        empty="Nenhuma venda no período."
        rows={funis.map((flow) => ({
          id: flow.id,
          name: flow.name,
          revenue: flow.revenue,
          stats: [
            ["Vendas", formatNumber(flow.sales)],
            ["Conversão", formatPercent(flow.conversion)],
            ["Faturou", moneyFormat.format(flow.revenue)],
            ["Ticket", moneyFormat.format(flow.ticket)],
          ],
        }))}
        max={best(funis)}
      />

      <Ranking
        icon={<TrendingUp size={16} />}
        title="Planos que mais venderam"
        empty="Nenhum plano vendido no período."
        rows={planos.map((plan) => ({
          id: plan.name,
          name: plan.name,
          revenue: plan.revenue,
          stats: [
            ["Vendas", formatNumber(plan.sales)],
            ["Conversão", formatPercent(plan.conversion)],
            ["Faturou", moneyFormat.format(plan.revenue)],
          ],
        }))}
        max={best(planos)}
      />
    </div>
  );
}

type RankRow = { id: string; name: string; revenue: number; stats: [string, string][] };

function Ranking({ icon, title, rows, empty, max }: { icon: React.ReactNode; title: string; rows: RankRow[]; empty: string; max: number }) {
  return (
    <div className="dashboard-card space-y-3 p-4 sm:p-5">
      <h2 className="flex items-center gap-2 text-base font-semibold text-fg">{icon} {title}</h2>
      {rows.length === 0 ? (
        <p className="text-sm text-muted">{empty}</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row, index) => (
            <li key={row.id} className="rounded-xl border border-line-soft bg-surface-inset p-3">
              <div className="flex items-center gap-2">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand/15 text-xs font-bold text-accent">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate font-medium text-fg">{row.name}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-surface-raised">
                <div className="h-full rounded-full bg-accent/70" style={{ width: `${Math.round((row.revenue / max) * 100)}%` }} />
              </div>
              <dl className="mt-2 flex flex-wrap gap-2 text-center">
                {row.stats.map(([label, value]) => (
                  <div className="min-w-[64px] flex-1" key={label}>
                    <dt className="text-[10px] uppercase tracking-wide text-muted">{label}</dt>
                    <dd className="text-sm font-semibold text-fg">{value}</dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
