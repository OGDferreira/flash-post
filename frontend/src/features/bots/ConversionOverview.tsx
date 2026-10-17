import { useQuery } from "@tanstack/react-query";
import { Area, Bar, CartesianGrid, ComposedChart, LabelList, ResponsiveContainer, Tooltip, XAxis, YAxis, type LabelProps } from "recharts";
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
  const series = (stats.data?.series ?? []).map((day, index) => ({
    ...day,
    index,
    label: day.date.slice(8, 10) + "/" + day.date.slice(5, 7),
  }));
  // Value + sales over each bar when there is room; on long periods the numbers stay in the tooltip.
  const wide = typeof window !== "undefined" && window.matchMedia("(min-width: 1024px)").matches;
  const compact = series.length > 16;
  const showLabels = !compact || (wide && series.length <= 31);
  const DayLabel = (props: LabelProps) => {
    const day = series[Number(props.value)];
    if (!day || day.revenue <= 0) return null;
    const x = Number(props.x ?? 0) + Number(props.width ?? 0) / 2;
    const y = Number(props.y ?? 0);
    if (compact) {
      return (
        <text fill="var(--color-success)" fontSize={9} fontWeight={600} textAnchor="middle" x={x} y={y - 5}>
          R${Math.round(day.revenue)}
          <tspan fill="var(--color-muted)" fontWeight={400}> · {day.sales}</tspan>
        </text>
      );
    }
    return (
      <text fontSize={10} textAnchor="middle" x={x} y={y - 16}>
        <tspan fill="var(--color-success)" fontWeight={600} x={x}>{money(day.revenue).replace(/\s/g, "")}</tspan>
        <tspan dy={11} fill="var(--color-muted)" x={x}>{day.sales} {day.sales === 1 ? "venda" : "vendas"}</tspan>
      </text>
    );
  };
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
          <h3 className="text-sm font-semibold text-fg">Faturamento e vendas por dia</h3>
          <span className="flex flex-wrap items-center gap-3 text-[11px] text-muted">
            <span className="flex items-center gap-1"><i className="inline-block size-2.5 rounded-sm bg-success/70" /> Faturamento (R$)</span>
            <span className="flex items-center gap-1"><i className="inline-block h-0.5 w-3 bg-[var(--grad-a)]" /> Vendas</span>
            <span className="flex items-center gap-1"><i className="inline-block h-0 w-3 border-t border-dashed border-current" /> Leads</span>
            <span>{stats.data?.period_label}</span>
          </span>
        </div>
        <div className="h-56 sm:h-64">
          <ResponsiveContainer height="100%" width="100%">
            <ComposedChart data={series} margin={{ left: -12, right: 0, top: 30, bottom: 0 }}>
              <defs>
                <linearGradient id="convFill" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="var(--grad-a)" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="var(--grad-a)" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--color-line-soft)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="label" fontSize={10} stroke="var(--color-muted)" tickLine={false} axisLine={false} minTickGap={16} />
              <YAxis allowDecimals={false} fontSize={10} stroke="var(--color-muted)" tickLine={false} axisLine={false} yAxisId="count" />
              <YAxis
                axisLine={false}
                fontSize={10}
                orientation="right"
                stroke="var(--color-muted)"
                tickFormatter={(value: number) => (value >= 1000 ? `${Math.round(value / 100) / 10}k` : String(Math.round(value)))}
                tickLine={false}
                width={40}
                yAxisId="money"
              />
              <Tooltip
                contentStyle={{ background: "var(--nm-bg)", border: "1px solid var(--color-line)", borderRadius: 12, fontSize: 12 }}
                formatter={(value, name) =>
                  name === "revenue"
                    ? [money(Number(value ?? 0)), "Faturamento"]
                    : [String(value ?? 0), name === "sales" ? "Vendas" : "Leads"]
                }
                labelFormatter={(label) => `Dia ${label}`}
              />
              <Bar dataKey="revenue" fill="var(--color-success)" fillOpacity={0.55} maxBarSize={28} radius={[6, 6, 0, 0]} yAxisId="money">
                {showLabels && <LabelList content={DayLabel} dataKey="index" />}
              </Bar>
              <Area dataKey="leads" fill="none" stroke="var(--color-muted)" strokeDasharray="4 4" strokeWidth={1.5} type="monotone" yAxisId="count" />
              <Area dataKey="sales" fill="url(#convFill)" stroke="var(--grad-a)" strokeWidth={2.5} type="monotone" yAxisId="count" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
