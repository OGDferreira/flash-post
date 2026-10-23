import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, CalendarDays, CircleDollarSign, Handshake, Receipt, TrendingUp, Zap } from "lucide-react";
import type { ReactNode } from "react";

import { PeriodFilter, isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";
import { ActivityLog, NextAward, PartnersRanking } from "./HomePanels";

export type StatLine = { leads: number; sales: number; buyers: number; revenue: number; conversion: number; ticket: number };
export type BotStats = {
  period_label: string;
  totals: StatLine & { pix_generated: number; pix_paid: number; commission?: number };
  time_zone: string;
  series: (StatLine & { date: string; commission?: number })[];
  flows: Record<string, StatLine>;
  bots: Record<string, StatLine>;
};

const COMMISSION_COLOR = "#34d399";
const money = (value: number) => value.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const count = (value: number) => value.toLocaleString("pt-BR");
const weekday = (iso: string) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString("pt-BR", { weekday: "short" }).replace(".", "");

export function useBotStats(period: MetricsPeriod) {
  return useQuery({
    queryKey: ["bots", "stats", periodParams(period)],
    queryFn: () => apiRequest<BotStats>(`/api/bots/stats?${new URLSearchParams(periodParams(period))}`),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
    refetchOnMount: "always",
    refetchInterval: 60_000,
  });
}

type PartnerRow = { bot_revenue: string; bot_sales: number; commission_received: string };

/** Falcon Bot sales of the user's partners and the commission they paid, in the chosen period. */
function usePartnerTotals(period: MetricsPeriod) {
  return useQuery({
    queryKey: ["affiliates", "flashbot-totals", periodParams(period)],
    queryFn: () => apiRequest<{ rows: PartnerRow[] }>(`/api/affiliates?${new URLSearchParams(periodParams(period))}&user_calendar=true`),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
    retry: false, // collaborators cannot see partners: just hide the cards
  });
}

function StatCard({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="dashboard-card flex min-h-[150px] flex-col rounded-2xl p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-inset text-accent">{icon}</span>
        <h3 className="text-sm font-semibold text-fg">{title}</h3>
      </div>
      {children}
    </div>
  );
}

function Bar({ percent }: { percent: number }) {
  return (
    <div className="h-1 overflow-hidden rounded-full bg-well">
      <div className="h-full rounded-full bg-accent transition-[width] duration-700" style={{ width: `${Math.min(100, Math.max(0, percent))}%` }} />
    </div>
  );
}

/** Half-circle meter for the conversion rate. */
function Gauge({ percent }: { percent: number }) {
  const value = Math.min(100, Math.max(0, percent));
  const arc = Math.PI * 40;
  return (
    <div className="relative mx-auto w-36">
      <svg aria-hidden="true" className="w-full" viewBox="0 0 100 56">
        <path d="M10 50 A40 40 0 0 1 90 50" fill="none" stroke="var(--color-well)" strokeLinecap="round" strokeWidth="9" />
        <path
          d="M10 50 A40 40 0 0 1 90 50"
          fill="none"
          stroke="var(--grad-a)"
          strokeDasharray={`${(arc * value) / 100} ${arc}`}
          strokeLinecap="round"
          strokeWidth="9"
          style={{ transition: "stroke-dasharray 700ms ease" }}
        />
      </svg>
      <span className="absolute inset-x-0 bottom-0 text-center text-xl font-bold text-fg">
        {percent.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%
      </span>
    </div>
  );
}

/** Falcon Bot home: SharkBot-style KPI cards, daily revenue chart, lead log, next award and the partners' ranking. */
export function ConversionOverview({ period, onPeriod }: { period: MetricsPeriod; onPeriod: (value: MetricsPeriod) => void }) {
  const stats = useBotStats(period);
  const chart = useBotStats({ period: "30d", start: "", end: "" });
  const partners = usePartnerTotals(period);
  const partnerRows = partners.data?.rows ?? [];
  const partnerRevenue = partnerRows.reduce((sum, row) => sum + Number(row.bot_revenue), 0);
  const partnerSales = partnerRows.reduce((sum, row) => sum + row.bot_sales, 0);
  const commission = partnerRows.reduce((sum, row) => sum + Number(row.commission_received), 0);
  const t = stats.data?.totals;
  const pix = t?.pix_generated ?? 0;
  const paidShare = t?.conversion ?? 0;
  const series = (chart.data?.series ?? []).map((day) => ({
    ...day,
    label: (chart.data?.series.length ?? 0) <= 7 ? weekday(day.date) : `${day.date.slice(8, 10)}/${day.date.slice(5, 7)}`,
  }));
  // The mini chart always shows the last 7 days (like SharkBot), whatever the period above.
  const recent = (chart.data?.series ?? []).slice(-7);
  const showCommission = (chart.data?.totals.commission ?? 0) > 0;
  const peak = Math.max(1, ...recent.map((day) => day.leads));

  return (
    <section className="space-y-3">
      <div className="dashboard-card flex flex-wrap items-center justify-between gap-2 rounded-2xl px-4 py-3">
        <span className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
          <CalendarDays size={14} /> Período
        </span>
        <PeriodFilter onChange={onPeriod} value={period} />
      </div>

      <div className="grid gap-3 xl:grid-cols-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:col-span-2">
          <StatCard icon={<CircleDollarSign size={16} />} title="Vendas aprovadas">
            <p className="text-2xl font-bold text-fg">{t ? money(t.revenue) : "—"}</p>
            <div className="mt-auto space-y-1 pt-3">
              <Bar percent={paidShare} />
              <p className="text-right text-[10px] text-muted">
                {t ? `${count(t.sales)} vendas · ${paidShare.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}% aprov.` : ""}
              </p>
            </div>
          </StatCard>

          <StatCard icon={<TrendingUp size={16} />} title="Taxa de conversão">
            <Gauge percent={t?.conversion ?? 0} />
            <p className="mt-2 text-center text-[10px] text-muted">{t ? `${count(t.pix_paid)} PIX pagos / ${count(pix)} PIX gerados` : ""}</p>
          </StatCard>

          <StatCard icon={<Zap size={16} />} title="Total de starts">
            <p className="text-2xl font-bold text-fg">{t ? count(t.leads) : "—"}</p>
            <p className="text-[10px] text-muted">leads iniciaram conversa</p>
            <p className="mt-1 text-[10px] text-muted">
              <span className="font-semibold text-fg">{t && t.sales ? count(Math.round(t.leads / t.sales)) : "—"}</span> starts por venda
            </p>
            <div className="mt-auto flex h-14 items-end gap-1.5 pt-3" aria-label="Starts dos últimos 7 dias" role="img">
              {recent.map((day, index) => (
                <span
                  className={`flex-1 rounded-t-[4px] transition-[height] duration-500 ${
                    index === recent.length - 1 ? "bg-gradient-to-t from-accent/70 to-accent" : "bg-accent/30"
                  }`}
                  key={day.date}
                  style={{ height: `${Math.max(10, (100 * day.leads) / peak)}%` }}
                  title={`${weekday(day.date)}: ${count(day.leads)} starts`}
                />
              ))}
            </div>
          </StatCard>

          <StatCard icon={<Receipt size={16} />} title="Ticket médio">
            <p className="text-2xl font-bold text-fg">{t ? money(t.ticket) : "—"}</p>
            <p className="text-[10px] text-muted">
              Vendas: <span className="font-semibold text-fg">{t ? money(t.revenue) : "—"}</span>
            </p>
            <div className="mt-auto space-y-1 pt-3">
              <p className="flex justify-between text-[10px] text-muted">
                <span>Pix pagos</span>
                <span className="font-semibold text-fg">{t ? count(t.sales) : "—"}</span>
              </p>
              <Bar percent={paidShare} />
              <p className="text-right text-[10px] text-muted">de {count(pix)} Pix gerados</p>
            </div>
          </StatCard>
        </div>

        <div className="dashboard-card flex flex-col rounded-2xl p-4 xl:col-span-3">
          <div className="mb-2 flex items-center gap-2">
            <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-inset text-accent"><Activity size={16} /></span>
            <div>
              <h3 className="text-sm font-semibold text-fg">Seu desempenho</h3>
              <p className="text-[10px] uppercase tracking-[0.14em] text-muted">Últimos 30 dias · {chart.data?.period_label ?? ""}</p>
            </div>
          </div>
          <p className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted">
            <span className="flex items-center gap-1.5"><span className="size-2 rounded-full bg-accent" /> Faturamento por dia</span>
            {showCommission && (
              <span className="flex items-center gap-1.5">
                <span className="h-0.5 w-3 rounded-full" style={{ background: COMMISSION_COLOR }} /> Comissão dos sócios
              </span>
            )}
          </p>
          <div className="min-h-[240px] flex-1">
            <ResponsiveContainer height="100%" minHeight={240} width="100%">
              <AreaChart data={series} margin={{ left: 4, right: 8, top: 10, bottom: 0 }}>
                <defs>
                  <linearGradient id="revenueFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--grad-a)" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="var(--grad-a)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--color-line-soft)" strokeDasharray="3 3" vertical={false} />
                <XAxis axisLine={false} dataKey="label" fontSize={10} minTickGap={16} stroke="var(--color-muted)" tickLine={false} />
                <YAxis
                  axisLine={false}
                  fontSize={10}
                  stroke="var(--color-muted)"
                  tickFormatter={(value: number) => value.toLocaleString("pt-BR", { notation: "compact", maximumFractionDigits: 1 })}
                  tickLine={false}
                  width={44}
                />
                <Tooltip
                  contentStyle={{ background: "var(--nm-bg)", border: "1px solid var(--color-line)", borderRadius: 12, fontSize: 12 }}
                  formatter={(value, name, item) => {
                    if (name === "commission") return [money(Number(value ?? 0)), "Comissão"];
                    const sales = Number(item?.payload?.sales ?? 0);
                    return [`${money(Number(value ?? 0))} · ${count(sales)} ${sales === 1 ? "venda" : "vendas"}`, "Faturamento"];
                  }}
                  labelFormatter={(_, payload) => {
                    const date = payload?.[0]?.payload?.date as string | undefined;
                    return date ? `${date.slice(8, 10)}/${date.slice(5, 7)}` : "";
                  }}
                />
                <Area dataKey="revenue" fill="url(#revenueFill)" stroke="var(--grad-a)" strokeWidth={2.5} type="monotone" />
                {showCommission && (
                  <Area dataKey="commission" fill="none" stroke={COMMISSION_COLOR} strokeDasharray="5 4" strokeWidth={2} type="monotone" />
                )}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {partnerRows.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2">
          <StatCard icon={<Handshake size={16} />} title="Vendas dos sócios">
            <p className="text-2xl font-bold text-fg">{money(partnerRevenue)}</p>
            <p className="mt-auto pt-3 text-[10px] text-muted">
              {count(partnerSales)} {partnerSales === 1 ? "venda" : "vendas"} no Falcon Bot de {count(partnerRows.length)}{" "}
              {partnerRows.length === 1 ? "sócio" : "sócios"} · {stats.data?.period_label ?? ""}
            </p>
          </StatCard>
          <StatCard icon={<CircleDollarSign size={16} />} title="Comissão">
            <p className="text-2xl font-bold text-success">{money(commission)}</p>
            <p className="mt-auto pt-3 text-[10px] text-muted">
              Recebida das vendas dos sócios{partnerRevenue > 0 ? ` · ${((100 * commission) / partnerRevenue).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}% do faturamento deles` : ""}
            </p>
          </StatCard>
        </div>
      )}

      <div className="grid gap-3 lg:grid-cols-2 xl:grid-cols-3">
        <ActivityLog />
        <NextAward />
        <PartnersRanking period={period} />
      </div>
    </section>
  );
}
