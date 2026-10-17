import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { BadgePercent, CircleDollarSign, Receipt, ShoppingCart, Users } from "lucide-react";

import { PeriodFilter, isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";

export type StatLine = { leads: number; sales: number; buyers: number; revenue: number; conversion: number; ticket: number };
export type BotStats = {
  period_label: string;
  totals: StatLine;
  series: (StatLine & { date: string })[];
  flows: Record<string, StatLine>;
  bots: Record<string, StatLine>;
};

const money = (value: number) => value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

export function useBotStats(period: MetricsPeriod) {
  return useQuery({
    queryKey: ["bots", "stats", periodParams(period)],
    queryFn: () => apiRequest<BotStats>(`/api/bots/stats?${new URLSearchParams(periodParams(period))}`),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  });
}

/** Compact KPI cards + conversion chart (SharkBot-style) for the selected period. */
export function ConversionOverview({ period, onPeriod }: { period: MetricsPeriod; onPeriod: (value: MetricsPeriod) => void }) {
  const stats = useBotStats(period);
  const t = stats.data?.totals;
  const cards = [
    { label: "Leads", value: t ? t.leads.toLocaleString("pt-BR") : "—", Icon: Users },
    { label: "Vendas confirmadas", value: t ? t.sales.toLocaleString("pt-BR") : "—", Icon: ShoppingCart },
    { label: "Conversão", value: t ? `${t.conversion.toLocaleString("pt-BR")}%` : "—", Icon: BadgePercent, tone: "text-accent" },
    { label: "Ticket médio", value: t ? money(t.ticket) : "—", Icon: Receipt },
    { label: "Faturamento", value: t ? money(t.revenue) : "—", Icon: CircleDollarSign, tone: "text-success" },
  ];
  const series = (stats.data?.series ?? []).map((day) => ({ ...day, label: day.date.slice(8, 10) + "/" + day.date.slice(5, 7) }));
  return (
    <section className="space-y-3">
      <PeriodFilter onChange={onPeriod} value={period} />
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
        {cards.map(({ label, value, Icon, tone }) => (
          <div className="dashboard-card flex items-center gap-3 rounded-2xl px-3 py-2.5" key={label}>
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-inset text-accent"><Icon size={16} /></span>
            <span className="min-w-0">
              <span className="block truncate text-[11px] text-muted">{label}</span>
              <span className={`block truncate text-lg font-semibold ${tone ?? "text-fg"}`}>{value}</span>
            </span>
          </div>
        ))}
      </div>
      <div className="dashboard-card rounded-2xl p-3 sm:p-4">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-2">
          <h3 className="text-sm font-semibold text-fg">Evolução das conversões</h3>
          <span className="text-[11px] text-muted">
            {stats.data?.period_label} · conversão = leads que compraram ÷ leads
          </span>
        </div>
        <div className="h-48 sm:h-56">
          <ResponsiveContainer height="100%" width="100%">
            <AreaChart data={series} margin={{ left: -18, right: 6, top: 6, bottom: 0 }}>
              <defs>
                <linearGradient id="convFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--grad-a)" stopOpacity={0.45} />
                  <stop offset="100%" stopColor="var(--grad-a)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--color-line-soft)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" fontSize={10} stroke="var(--color-muted)" tickLine={false} axisLine={false} minTickGap={16} />
              <YAxis allowDecimals={false} fontSize={10} stroke="var(--color-muted)" tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ background: "var(--nm-bg)", border: "1px solid var(--color-line)", borderRadius: 12, fontSize: 12 }}
                formatter={(value, name) => [String(value ?? 0), name === "sales" ? "Vendas" : "Leads"]}
              />
              <Area dataKey="leads" fill="none" stroke="var(--color-muted)" strokeDasharray="4 4" strokeWidth={1.5} type="monotone" />
              <Area dataKey="sales" fill="url(#convFill)" stroke="var(--grad-a)" strokeWidth={2.5} type="monotone" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
