import { useMemo, useState, type ReactNode } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  ArrowDownRight,
  ArrowUpRight,
  Bot,
  CalendarClock,
  CalendarDays,
  Clock3,
  CreditCard,
  Filter,
  Megaphone,
  Package,
  Radio,
  Repeat,
  ShoppingCart,
  Sparkles,
  TrendingDown,
  TrendingUp,
  Trophy,
  Users,
  Workflow,
  X,
} from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";
import { FlashFunnelPanel } from "@/features/bots/FlashFunnelPanel";
import { formatNumber, formatPercent, isPeriodReady, moneyFormat, PeriodFilter, periodParams, type MetricsPeriod } from "@/features/analytics/period";

type Row = {
  id: string;
  name: string;
  leads: number;
  generated: number;
  sales: number;
  revenue: number;
  buyers: number;
  approval: number;
  conversion: number;
  ticket: number;
};
type Summary = {
  leads: number;
  generated: number;
  generated_value: number;
  sales: number;
  revenue: number;
  ticket: number;
  approval: number;
  buyers: number;
  lead_conversion: number;
  leads_with_pix: number;
};
type Full = {
  period_label: string;
  summary: Summary;
  previous: Summary;
  series: { date: string; sales: number; revenue: number; generated: number }[];
  hours: { hour: number; sales: number; revenue: number }[];
  weekdays: { day: string; sales: number; revenue: number }[];
  bots: Row[];
  flows: Row[];
  plans: Row[];
  sources: Row[];
  offer_types: { kind: "plan" | "upsell" | "downsell" | "remarketing"; generated: number; sales: number; revenue: number; approval: number }[];
  order_bump: { sales: number; revenue: number; rate: number };
  customers: {
    buyers: number;
    recurring: number;
    upsellers: number;
    downsellers: number;
    remarketing: number;
    bump_buyers: number;
    vips_active: number;
    ltv: number;
    purchases_per_buyer: number;
    avg_seconds_to_pay: number | null;
    avg_seconds_between_purchases: number | null;
    blocked: number;
    blocked_rate: number;
    abandoned_pix: number;
    abandoned_value: number;
  };
  gateways: { gateway: string; sales: number; revenue: number }[];
  options: { bots: { id: string; name: string }[]; flows: { id: string; name: string }[]; plans: string[] };
};

type Filters = { bot: string; flow: string; plan: string };
type RankTab = "plans" | "flows" | "bots" | "sources";
type SortBy = "revenue" | "sales" | "approval" | "conversion";

const money = (value: number) => moneyFormat.format(value || 0);
const KIND_LABEL = { plan: "Planos", upsell: "Upsell", downsell: "Downsell", remarketing: "Remarketing" } as const;
const KIND_ICON = { plan: Package, remarketing: Megaphone, downsell: TrendingDown, upsell: Repeat } as const;
/** The order Guilherme reads them in: entrada, resgate, oferta menor, oferta maior. */
const KIND_ORDER = ["plan", "remarketing", "downsell", "upsell"] as const;
const GATEWAY_LABEL: Record<string, string> = { smokepay: "SmokePay", snakepay: "SnakePay", atenaspay: "Athenas Pay" };
const RANK_TABS: { id: RankTab; label: string; icon: typeof Bot }[] = [
  { id: "plans", label: "Planos", icon: Package },
  { id: "flows", label: "Fluxos", icon: Workflow },
  { id: "bots", label: "Bots", icon: Bot },
  { id: "sources", label: "Fontes", icon: Radio },
];
const SORTS: { id: SortBy; label: string }[] = [
  { id: "revenue", label: "Faturou" },
  { id: "sales", label: "Vendas" },
  { id: "approval", label: "Aprovação" },
  { id: "conversion", label: "Conversão" },
];

/** "29 s", "4 min", "2 h 10 min", "3,5 dias". */
function duration(seconds: number | null) {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds} s`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.round((seconds % 3600) / 60);
    return minutes ? `${hours} h ${minutes} min` : `${hours} h`;
  }
  return `${(seconds / 86400).toLocaleString("pt-BR", { maximumFractionDigits: 1 })} dias`;
}

/** Análises: everything about the operation's Flash sales, filtered by period, bot, funnel and plan.
 *  Hierarchy, top to bottom: filtros → KPIs → funil por bot → conversão por tipo → detalhe. */
export function AnalyticsPanel({ period, onPeriod }: { period: MetricsPeriod; onPeriod: (next: MetricsPeriod) => void }) {
  const [filters, setFilters] = useState<Filters>({ bot: "", flow: "", plan: "" });
  const params = useMemo(() => {
    const out: Record<string, string> = { ...periodParams(period) };
    if (filters.bot) out.bot_id = filters.bot;
    if (filters.flow) out.flow_id = filters.flow;
    if (filters.plan) out.plan = filters.plan;
    return out;
  }, [period, filters]);
  const query = useQuery({
    queryKey: ["bots", "analytics-full", params],
    queryFn: () => apiRequest<Full>(`/api/bots/analytics/full?${new URLSearchParams(params)}`),
    enabled: isPeriodReady(period),
    placeholderData: keepPreviousData,
  });

  const options = query.data?.options;

  return (
    <div className="space-y-4">
      <FiltersBar
        filters={filters}
        onChange={setFilters}
        onPeriod={onPeriod}
        options={options}
        period={period}
      />
      {query.isLoading ? (
        <LoadingState label="Carregando análises" />
      ) : query.error || !query.data ? (
        <ErrorState message="Não foi possível carregar as análises." onRetry={() => void query.refetch()} />
      ) : (
        <div className={`space-y-4 transition-opacity ${query.isFetching ? "opacity-70" : ""}`}>
          <p className="px-1 text-xs text-muted">
            {query.data.period_label}
            {filters.bot || filters.flow || filters.plan ? " · com filtros" : " · toda a operação"} · comparado ao período anterior de mesmo tamanho
          </p>
          <Kpis data={query.data} />
          <RankingHighlights data={query.data} />
          {/* Plan filter doesn't scope the per-step upsell funnel, so only bot/funnel flow into it. */}
          <FlashFunnelPanel botId={filters.bot || undefined} flowId={filters.flow || undefined} period={period} />
          <ConversionByType data={query.data} />
          <WhenItSells data={query.data} />
          <WhatSells data={query.data} />
          <Customers data={query.data} />
          <LtvPanel botId={filters.bot || undefined} flowId={filters.flow || undefined} period={period} />
          <Gateways rows={query.data.gateways} />
        </div>
      )}
    </div>
  );
}

function FiltersBar({ filters, onChange, onPeriod, options, period }: {
  filters: Filters;
  onChange: (next: Filters) => void;
  onPeriod: (next: MetricsPeriod) => void;
  options?: Full["options"];
  period: MetricsPeriod;
}) {
  const set = (patch: Partial<Filters>) => onChange({ ...filters, ...patch });
  const active = Boolean(filters.bot || filters.flow || filters.plan);
  return (
    <div className="dashboard-card space-y-3 rounded-2xl p-3 sm:p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
          <CalendarDays size={14} /> Período
        </span>
        <PeriodFilter onChange={onPeriod} value={period} />
      </div>
      <div className="border-t border-line-soft pt-3">
        <div className="mb-2 flex items-center justify-between gap-2">
          <span className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
            <Filter size={14} /> Filtros
          </span>
          {active && (
            <button
              className="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs text-muted hover:bg-well hover:text-fg"
              onClick={() => onChange({ bot: "", flow: "", plan: "" })}
              type="button"
            >
              <X size={13} /> Limpar
            </button>
          )}
        </div>
        <div className="grid gap-2 sm:grid-cols-3">
          <select aria-label="Bot" className="field" onChange={(event) => set({ bot: event.target.value })} value={filters.bot}>
            <option value="">Todos os bots</option>
            {(options?.bots ?? []).map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
          <select aria-label="Fluxo" className="field" onChange={(event) => set({ flow: event.target.value })} value={filters.flow}>
            <option value="">Todos os fluxos</option>
            {(options?.flows ?? []).map((item) => (
              <option key={item.id} value={item.id}>{item.name}</option>
            ))}
          </select>
          <select aria-label="Plano" className="field" onChange={(event) => set({ plan: event.target.value })} value={filters.plan}>
            <option value="">Todos os planos</option>
            {(options?.plans ?? []).map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
}

function Delta({ now, before, points = false }: { now: number; before: number; points?: boolean }) {
  if (points) {
    const diff = Math.round((now - before) * 10) / 10;
    if (!diff) return <span className="text-[11px] text-muted">= anterior</span>;
    const up = diff > 0;
    return (
      <span className={`inline-flex items-center gap-0.5 text-[11px] font-semibold ${up ? "text-success" : "text-danger"}`}>
        {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
        {up ? "+" : ""}
        {diff.toLocaleString("pt-BR")} p.p.
      </span>
    );
  }
  if (!before) return <span className="text-[11px] text-muted">{now ? "novo no período" : "sem dados antes"}</span>;
  const change = ((now - before) / before) * 100;
  if (Math.abs(change) < 0.05) return <span className="text-[11px] text-muted">= anterior</span>;
  const up = change > 0;
  return (
    <span className={`inline-flex items-center gap-0.5 text-[11px] font-semibold ${up ? "text-success" : "text-danger"}`}>
      {up ? <ArrowUpRight size={12} /> : <ArrowDownRight size={12} />}
      {up ? "+" : ""}
      {change.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%
    </span>
  );
}

function Kpis({ data }: { data: Full }) {
  const s = data.summary;
  const p = data.previous;
  const cards: { label: string; value: string; hint: string; delta: ReactNode; strong?: boolean }[] = [
    { label: "Faturamento", value: money(s.revenue), hint: `${formatNumber(s.sales)} ${s.sales === 1 ? "venda paga" : "vendas pagas"}`, delta: <Delta before={p.revenue} now={s.revenue} />, strong: true },
    { label: "Vendas", value: formatNumber(s.sales), hint: `${formatNumber(s.buyers)} compradores`, delta: <Delta before={p.sales} now={s.sales} /> },
    { label: "Starts", value: formatNumber(s.leads), hint: "leads que entraram", delta: <Delta before={p.leads} now={s.leads} /> },
    { label: "Pix gerados", value: formatNumber(s.generated), hint: `${money(s.generated_value)} gerados`, delta: <Delta before={p.generated} now={s.generated} /> },
    { label: "Aprovação", value: formatPercent(s.approval), hint: "Pix pagos ÷ gerados", delta: <Delta before={p.approval} now={s.approval} points /> },
    { label: "Conversão", value: formatPercent(s.lead_conversion), hint: "leads que compraram", delta: <Delta before={p.lead_conversion} now={s.lead_conversion} points /> },
    { label: "Ticket médio", value: money(s.ticket), hint: "por venda", delta: <Delta before={p.ticket} now={s.ticket} /> },
    { label: "Receita gerada", value: money(s.generated_value), hint: "soma dos Pix gerados", delta: <Delta before={p.generated_value} now={s.generated_value} /> },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {cards.map((card) => (
        <div className="dashboard-card min-w-0 rounded-2xl p-3.5 sm:p-4" key={card.label}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-muted">{card.label}</p>
          <p className={`mt-1 truncate text-xl font-bold sm:text-2xl ${card.strong ? "text-success" : "text-fg"}`}>{card.value}</p>
          <p className="truncate text-[11px] text-muted">{card.hint}</p>
          <div className="mt-1">{card.delta}</div>
        </div>
      ))}
    </div>
  );
}

function Section({ icon, title, subtitle, children, right }: { icon: ReactNode; title: string; subtitle?: string; children: ReactNode; right?: ReactNode }) {
  return (
    <section className="dashboard-card rounded-2xl p-4 sm:p-5">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-brand/12 text-accent">{icon}</span>
          <div className="min-w-0">
            <h2 className="truncate text-base font-semibold text-fg">{title}</h2>
            {subtitle && <p className="text-[11px] uppercase tracking-[0.12em] text-muted">{subtitle}</p>}
          </div>
        </div>
        {right}
      </div>
      {children}
    </section>
  );
}

/** A compact top-5 list (bots by faturamento, funis by conversão) for the selected period. */
function RankList({ title, icon, rows, metric, width, sub, empty }: {
  title: string;
  icon: ReactNode;
  rows: Row[];
  metric: (row: Row) => string;
  width: (row: Row) => number;
  sub?: (row: Row) => string;
  empty: string;
}) {
  return (
    <div className="min-w-0">
      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-[0.12em] text-muted">
        <span className="text-accent">{icon}</span>
        {title}
      </p>
      {rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line px-3 py-6 text-center text-xs text-muted">{empty}</p>
      ) : (
        <ol className="space-y-1.5">
          {rows.map((row, index) => (
            <li className="rounded-xl border border-line-soft bg-surface-inset p-2.5" key={row.id}>
              <div className="flex items-center gap-2">
                <span className="grid size-5 shrink-0 place-items-center rounded-full bg-brand/15 text-[11px] font-bold text-accent">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate text-sm font-medium text-fg">{row.name}</span>
                <span className="shrink-0 text-sm font-semibold text-fg tabular-nums">{metric(row)}</span>
              </div>
              <div className="mt-1.5 h-1 overflow-hidden rounded-full bg-well">
                <div className="h-full rounded-full bg-accent/70" style={{ width: `${Math.max(3, width(row))}%` }} />
              </div>
              {sub && <p className="mt-1 truncate text-[10px] text-muted">{sub(row)}</p>}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}

function RankingHighlights({ data }: { data: Full }) {
  const topBots = [...data.bots].sort((a, b) => b.revenue - a.revenue || b.sales - a.sales).filter((row) => row.revenue > 0 || row.sales > 0).slice(0, 5);
  const topFlows = [...data.flows].sort((a, b) => b.conversion - a.conversion || b.revenue - a.revenue).filter((row) => row.leads > 0 || row.sales > 0).slice(0, 5);
  if (!topBots.length && !topFlows.length) return null;
  const botMax = Math.max(1, ...topBots.map((row) => row.revenue));
  const flowMax = Math.max(1, ...topFlows.map((row) => row.conversion));
  return (
    <Section icon={<Trophy size={17} />} subtitle="No período selecionado" title="Ranking">
      <div className="grid gap-4 lg:grid-cols-2">
        <RankList
          empty="Nenhum bot faturou no período."
          icon={<Bot size={13} />}
          metric={(row) => money(row.revenue)}
          rows={topBots}
          sub={(row) => `${formatNumber(row.sales)} ${row.sales === 1 ? "venda" : "vendas"} · ${formatNumber(row.leads)} leads`}
          title="Bots por faturamento"
          width={(row) => (row.revenue / botMax) * 100}
        />
        <RankList
          empty="Nenhum funil com leads no período."
          icon={<Workflow size={13} />}
          metric={(row) => formatPercent(row.conversion)}
          rows={topFlows}
          sub={(row) => `${formatNumber(row.sales)} ${row.sales === 1 ? "venda" : "vendas"} · ${money(row.revenue)}`}
          title="Funis por conversão (lead → venda)"
          width={(row) => (row.conversion / flowMax) * 100}
        />
      </div>
    </Section>
  );
}

/** One card per offer type (planos, remarketing, downsell, upsell): what converts and what doesn't. */
function ConversionByType({ data }: { data: Full }) {
  const byKind = new Map(data.offer_types.map((offer) => [offer.kind, offer]));
  const bump = data.order_bump;
  return (
    <Section icon={<ShoppingCart size={17} />} subtitle="O que converte em cada oferta" title="Conversão por tipo">
      <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
        {KIND_ORDER.map((kind) => {
          const offer = byKind.get(kind) ?? { kind, generated: 0, sales: 0, revenue: 0, approval: 0 };
          const Icon = KIND_ICON[kind];
          const idle = offer.generated === 0 && offer.sales === 0;
          return (
            <div className={`rounded-2xl border p-3.5 ${idle ? "border-line bg-surface-inset" : "border-line-soft bg-surface"}`} key={kind}>
              <p className="flex items-center gap-1.5 text-xs font-semibold text-fg-2">
                <span className="grid size-6 shrink-0 place-items-center rounded-lg bg-brand/12 text-accent"><Icon size={13} /></span>
                {KIND_LABEL[kind]}
              </p>
              <p className="mt-2 text-lg font-bold text-fg">{money(offer.revenue)}</p>
              <p className="text-[11px] text-muted">
                {formatNumber(offer.sales)} {offer.sales === 1 ? "venda" : "vendas"} · {formatNumber(offer.generated)} Pix
              </p>
              <div className="mt-2.5 flex items-center justify-between text-[11px]">
                <span className="text-muted">Conversão do Pix</span>
                <span className={`font-semibold ${offer.approval > 0 ? "text-success" : "text-muted"}`}>{formatPercent(offer.approval)}</span>
              </div>
              <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-well">
                <div className="h-full rounded-full bg-success/80" style={{ width: `${Math.min(100, offer.approval)}%` }} />
              </div>
            </div>
          );
        })}
      </div>
      <div className="mt-2.5 rounded-2xl border border-line-soft bg-surface-inset p-3.5">
        <p className="flex items-center gap-1.5 text-xs font-semibold text-fg-2"><Sparkles size={13} className="text-accent" /> Order bump</p>
        <p className="mt-1 text-[11px] text-muted">
          <span className="text-base font-bold text-fg">{formatPercent(bump.rate)}</span> aceitaram ·
          {" "}{formatNumber(bump.sales)} vendas com adicional ({money(bump.revenue)} no total)
        </p>
      </div>
    </Section>
  );
}

const tooltipStyle = { background: "var(--nm-bg)", border: "1px solid var(--color-line)", borderRadius: 12, fontSize: 12 };

function WhenItSells({ data }: { data: Full }) {
  const series = data.series.map((point) => ({ ...point, label: `${point.date.slice(8, 10)}/${point.date.slice(5, 7)}` }));
  const bestHour = data.hours.reduce((best, hour) => (hour.revenue > best.revenue ? hour : best), data.hours[0]);
  const bestDay = data.weekdays.reduce((best, day) => (day.revenue > best.revenue ? day : best), data.weekdays[0]);
  const many = series.length > 1;
  return (
    <div className="grid gap-4 xl:grid-cols-2">
      {many && (
        <div className="xl:col-span-2">
        <Section icon={<CalendarClock size={17} />} subtitle="Faturamento por dia" title="Vendas no período">
          <div className="h-[220px]">
            <ResponsiveContainer height="100%" width="100%">
              <AreaChart data={series} margin={{ left: 0, right: 8, top: 8, bottom: 0 }}>
                <defs>
                  <linearGradient id="analyticsFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="var(--grad-a)" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="var(--grad-a)" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="var(--color-line-soft)" strokeDasharray="3 3" vertical={false} />
                <XAxis axisLine={false} dataKey="label" fontSize={10} minTickGap={16} stroke="var(--color-muted)" tickLine={false} />
                <YAxis axisLine={false} fontSize={10} stroke="var(--color-muted)" tickFormatter={(v: number) => v.toLocaleString("pt-BR", { notation: "compact" })} tickLine={false} width={40} />
                <Tooltip
                  contentStyle={tooltipStyle}
                  formatter={(value, _name, item) => [`${money(Number(value ?? 0))} · ${formatNumber(Number(item?.payload?.sales ?? 0))} vendas · ${formatNumber(Number(item?.payload?.generated ?? 0))} Pix`, "Dia"]}
                />
                <Area dataKey="revenue" fill="url(#analyticsFill)" stroke="var(--grad-a)" strokeWidth={2.5} type="monotone" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Section>
        </div>
      )}
      <Section
        icon={<Clock3 size={17} />}
        right={bestHour.revenue > 0 ? <span className="rounded-full bg-success/12 px-2.5 py-1 text-xs font-semibold text-success">Pico: {bestHour.hour}h</span> : undefined}
        subtitle="Em que hora vende mais"
        title="Vendas por hora"
      >
        <SmallBars data={data.hours.map((h) => ({ label: `${h.hour}h`, sales: h.sales, revenue: h.revenue }))} highlight={bestHour.revenue > 0 ? `${bestHour.hour}h` : null} />
      </Section>
      <Section
        icon={<CalendarClock size={17} />}
        right={bestDay.revenue > 0 ? <span className="rounded-full bg-success/12 px-2.5 py-1 text-xs font-semibold text-success">Melhor: {bestDay.day}</span> : undefined}
        subtitle="Em que dia vende mais"
        title="Vendas por dia da semana"
      >
        <SmallBars data={data.weekdays.map((d) => ({ label: d.day, sales: d.sales, revenue: d.revenue }))} highlight={bestDay.revenue > 0 ? bestDay.day : null} />
      </Section>
    </div>
  );
}

function SmallBars({ data, highlight }: { data: { label: string; sales: number; revenue: number }[]; highlight: string | null }) {
  return (
    <div className="h-[180px]">
      <ResponsiveContainer height="100%" width="100%">
        <BarChart data={data} margin={{ left: 0, right: 4, top: 8, bottom: 0 }}>
          <CartesianGrid stroke="var(--color-line-soft)" strokeDasharray="3 3" vertical={false} />
          <XAxis axisLine={false} dataKey="label" fontSize={10} interval="preserveStartEnd" minTickGap={4} stroke="var(--color-muted)" tickLine={false} />
          <YAxis allowDecimals={false} axisLine={false} fontSize={10} stroke="var(--color-muted)" tickLine={false} width={28} />
          <Tooltip
            contentStyle={tooltipStyle}
            cursor={{ fill: "var(--color-well)" }}
            formatter={(value, _name, item) => [`${formatNumber(Number(value ?? 0))} vendas · ${money(Number(item?.payload?.revenue ?? 0))}`, item?.payload?.label]}
          />
          <Bar dataKey="sales" radius={[6, 6, 0, 0]}>
            {data.map((row) => (
              <Cell fill={row.label === highlight ? "var(--color-success)" : "var(--grad-a)"} fillOpacity={row.label === highlight ? 1 : 0.75} key={row.label} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function WhatSells({ data }: { data: Full }) {
  const [tab, setTab] = useState<RankTab>("plans");
  const [sort, setSort] = useState<SortBy>("revenue");
  const rows = useMemo(() => [...data[tab]].sort((a, b) => b[sort] - a[sort] || b.revenue - a.revenue || b.generated - a.generated), [data, tab, sort]);
  const selling = rows.filter((row) => row.sales > 0);
  const notSelling = rows.filter((row) => row.sales === 0);
  const max = Math.max(1, ...rows.map((row) => row.revenue));
  return (
    <Section
      icon={<Sparkles size={17} />}
      subtitle={`${formatNumber(selling.length)} vendendo · ${formatNumber(notSelling.length)} sem vendas`}
      title="O que vende e o que não vende"
    >
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="inline-flex flex-wrap gap-1 rounded-full bg-well p-1" role="tablist">
          {RANK_TABS.map(({ id, label, icon: Icon }) => (
            <button
              aria-selected={tab === id}
              className={`inline-flex min-h-8 items-center gap-1.5 rounded-full px-3 text-xs font-medium ${tab === id ? "bg-brand text-white" : "text-muted hover:text-fg"}`}
              key={id}
              onClick={() => setTab(id)}
              role="tab"
              type="button"
            >
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>
        <select aria-label="Ordenar por" className="field !h-9 !w-auto !py-0 text-xs" onChange={(event) => setSort(event.target.value as SortBy)} value={sort}>
          {SORTS.map((option) => (
            <option key={option.id} value={option.id}>Ordenar: {option.label}</option>
          ))}
        </select>
      </div>
      {rows.length === 0 ? (
        <p className="rounded-xl border border-dashed border-line px-4 py-8 text-center text-sm text-muted">Nada no período com estes filtros.</p>
      ) : (
        <ul className="space-y-2">
          {rows.map((row, index) => (
            <li className={`rounded-xl border p-3 ${row.sales ? "border-line-soft bg-surface-inset" : "border-warning/30 bg-warning/5"}`} key={`${tab}-${row.id}`}>
              <div className="flex items-center gap-2">
                <span className="grid size-6 shrink-0 place-items-center rounded-full bg-brand/15 text-xs font-bold text-accent">{index + 1}</span>
                <span className="min-w-0 flex-1 truncate font-medium text-fg">{row.name}</span>
                {row.sales === 0 ? (
                  <span className="shrink-0 rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-semibold uppercase text-warning">Sem vendas</span>
                ) : (
                  <span className="shrink-0 text-sm font-semibold text-success">{money(row.revenue)}</span>
                )}
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-well">
                <div className="h-full rounded-full bg-accent/70" style={{ width: `${Math.round((row.revenue / max) * 100)}%` }} />
              </div>
              <dl className="mt-2 grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
                {(
                  [
                    ["Starts", tab === "plans" ? "—" : formatNumber(row.leads)],
                    ["Pix", formatNumber(row.generated)],
                    ["Vendas", formatNumber(row.sales)],
                    ["Aprovação", formatPercent(row.approval)],
                    ["Conversão", tab === "plans" ? "—" : formatPercent(row.conversion)],
                    ["Ticket", money(row.ticket)],
                  ] as [string, string][]
                ).map(([label, value]) => (
                  <div className="min-w-0" key={label}>
                    <dt className="text-[10px] uppercase tracking-wide text-muted">{label}</dt>
                    <dd className="truncate text-sm font-semibold text-fg">{value}</dd>
                  </div>
                ))}
              </dl>
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

function Customers({ data }: { data: Full }) {
  const c = data.customers;
  const items: [string, string, string?][] = [
    ["Compradores", formatNumber(c.buyers)],
    ["Recorrentes", formatNumber(c.recurring), "compraram 2+ vezes"],
    ["VIPs ativos", formatNumber(c.vips_active), "assinaturas ativas hoje"],
    ["LTV médio", money(c.ltv), "gasto médio por cliente"],
    ["Compras por cliente", `${c.purchases_per_buyer.toLocaleString("pt-BR")}×`],
    ["Tempo até pagar", duration(c.avg_seconds_to_pay), "do start ao 1º pagamento"],
    ["Tempo de recompra", duration(c.avg_seconds_between_purchases), "entre compras"],
    ["Compraram upsell", formatNumber(c.upsellers)],
    ["Compraram downsell", formatNumber(c.downsellers)],
    ["Compraram no remarketing", formatNumber(c.remarketing)],
    ["Levaram o order bump", formatNumber(c.bump_buyers)],
    ["Pix abandonados", formatNumber(c.abandoned_pix), `${money(c.abandoned_value)} não pagos`],
    ["Bloquearam o bot", formatNumber(c.blocked), `${formatPercent(c.blocked_rate)} dos starts`],
  ];
  return (
    <Section icon={<Users size={17} />} subtitle="Quem compra e como" title="Clientes">
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-4">
        {items.map(([label, value, hint]) => (
          <div className="rounded-xl border border-line-soft bg-surface-inset p-3" key={label}>
            <p className="text-[11px] text-muted">{label}</p>
            <p className="text-lg font-bold text-fg">{value}</p>
            {hint && <p className="truncate text-[10px] text-muted">{hint}</p>}
          </div>
        ))}
      </div>
    </Section>
  );
}

function Gateways({ rows }: { rows: Full["gateways"] }) {
  if (!rows.length) return null;
  const total = rows.reduce((sum, row) => sum + row.revenue, 0) || 1;
  return (
    <Section icon={<CreditCard size={17} />} subtitle="Por onde entrou o dinheiro" title="Gateways">
      <ul className="space-y-2.5">
        {rows.map((row) => (
          <li key={row.gateway}>
            <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
              <span className="text-fg-2">{GATEWAY_LABEL[row.gateway] ?? row.gateway}</span>
              <span className="font-semibold text-fg">
                {money(row.revenue)} <span className="text-xs font-medium text-muted">· {formatNumber(row.sales)} vendas</span>
              </span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-well">
              <div className="h-full rounded-full bg-accent/70" style={{ width: `${(100 * row.revenue) / total}%` }} />
            </div>
          </li>
        ))}
      </ul>
    </Section>
  );
}

type Ltv = {
  period_label: string;
  summary: {
    cohort: number;
    buyers: number;
    conversion: number;
    total_ltv: number;
    avg_ltv: number;
    avg_first_sale: number;
    avg_ltv_per_lead: number;
    uplift: number;
    expansion_revenue: number;
    orders: number;
  };
  by_kind: { kind: "plan" | "upsell" | "downsell" | "remarketing"; sales: number; revenue: number }[];
  top_leads: { name: string; ltv: number; first_sale: number; first_at: string | null; orders: number; kinds: string[] }[];
};

/** LTV do lead: a safra de leads do período somada ao longo da vida inteira — além da 1ª venda,
 *  quanto o lead ainda rende (upsell, remarketing, recompra). Usa os mesmos filtros de bot/funil. */
function LtvPanel({ botId, flowId, period }: { botId?: string; flowId?: string; period: MetricsPeriod }) {
  const params = useMemo(() => {
    const out: Record<string, string> = { ...periodParams(period) };
    if (botId) out.bot_id = botId;
    if (flowId) out.flow_id = flowId;
    return out;
  }, [period, botId, flowId]);
  const query = useQuery({
    queryKey: ["bots", "analytics-ltv", params],
    queryFn: () => apiRequest<Ltv>(`/api/bots/analytics/ltv?${new URLSearchParams(params)}`),
    enabled: isPeriodReady(period),
    placeholderData: keepPreviousData,
  });

  if (query.isLoading) {
    return (
      <Section icon={<TrendingUp size={17} />} subtitle="Quanto o lead rende na vida toda" title="LTV do lead">
        <LoadingState label="Calculando LTV" />
      </Section>
    );
  }
  if (query.error || !query.data) {
    return (
      <Section icon={<TrendingUp size={17} />} subtitle="Quanto o lead rende na vida toda" title="LTV do lead">
        <ErrorState message="Não foi possível calcular o LTV." onRetry={() => void query.refetch()} />
      </Section>
    );
  }

  const s = query.data.summary;
  const byKind = query.data.by_kind;
  const kindTotal = byKind.reduce((sum, row) => sum + row.revenue, 0) || 1;
  const cards: { label: string; value: string; hint: string; strong?: boolean }[] = [
    { label: "LTV médio", value: money(s.avg_ltv), hint: "por comprador, vida toda", strong: true },
    { label: "1ª venda média", value: money(s.avg_first_sale), hint: "ticket de entrada" },
    { label: "Multiplicador", value: s.uplift ? `${s.uplift.toLocaleString("pt-BR")}×` : "—", hint: "LTV ÷ 1ª venda" },
    { label: "Expansão", value: money(s.expansion_revenue), hint: "receita após a 1ª venda" },
    { label: "LTV por lead", value: money(s.avg_ltv_per_lead), hint: "inclui quem não comprou" },
    { label: "Compradores", value: formatNumber(s.buyers), hint: `${formatPercent(s.conversion)} da safra` },
  ];
  return (
    <Section
      icon={<TrendingUp size={17} />}
      right={<span className="text-[11px] text-muted">{formatNumber(s.cohort)} leads na safra · {money(s.total_ltv)} no total</span>}
      subtitle="Quanto o lead rende na vida toda"
      title="LTV do lead"
    >
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        {cards.map((card) => (
          <div className="rounded-xl border border-line-soft bg-surface-inset p-3" key={card.label}>
            <p className="text-[11px] text-muted">{card.label}</p>
            <p className={`text-lg font-bold ${card.strong ? "text-success" : "text-fg"}`}>{card.value}</p>
            <p className="truncate text-[10px] text-muted">{card.hint}</p>
          </div>
        ))}
      </div>

      <div className="mt-4">
        <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted">De onde vem o LTV</p>
        <ul className="space-y-2.5">
          {byKind.filter((row) => row.revenue > 0 || row.sales > 0).map((row) => (
            <li key={row.kind}>
              <div className="mb-1 flex items-baseline justify-between gap-2 text-sm">
                <span className="flex items-center gap-1.5 text-fg-2">
                  {(() => {
                    const Icon = KIND_ICON[row.kind];
                    return <Icon size={13} className="text-muted" />;
                  })()}
                  {KIND_LABEL[row.kind]}
                </span>
                <span className="font-semibold text-fg">
                  {money(row.revenue)} <span className="text-xs font-medium text-muted">· {formatNumber(row.sales)} vendas</span>
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-well">
                <div className="h-full rounded-full bg-accent/70" style={{ width: `${(100 * row.revenue) / kindTotal}%` }} />
              </div>
            </li>
          ))}
          {byKind.every((row) => row.revenue === 0 && row.sales === 0) && (
            <li className="text-sm text-muted">Nenhuma venda paga nessa safra ainda.</li>
          )}
        </ul>
      </div>

      {query.data.top_leads.length > 0 && (
        <div className="mt-4">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-muted">Leads que mais renderam</p>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[460px] text-sm">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-[0.1em] text-muted">
                  <th className="pb-2 pr-3 font-medium">Lead</th>
                  <th className="pb-2 pr-3 text-right font-medium">1ª venda</th>
                  <th className="pb-2 pr-3 text-right font-medium">LTV</th>
                  <th className="pb-2 text-right font-medium">Compras</th>
                </tr>
              </thead>
              <tbody>
                {query.data.top_leads.map((lead, index) => (
                  <tr className="border-t border-line-soft" key={`${lead.name}-${index}`}>
                    <td className="py-2 pr-3">
                      <span className="block truncate font-medium text-fg">{lead.name}</span>
                      {lead.first_at && <span className="text-[10px] text-muted">desde {lead.first_at}</span>}
                    </td>
                    <td className="py-2 pr-3 text-right text-muted">{money(lead.first_sale)}</td>
                    <td className="py-2 pr-3 text-right font-semibold text-fg">{money(lead.ltv)}</td>
                    <td className="py-2 text-right text-muted">{formatNumber(lead.orders)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Section>
  );
}
