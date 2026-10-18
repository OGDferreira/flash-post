import { useQuery } from "@tanstack/react-query";
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Activity, CalendarDays, CircleDollarSign, Crown, Receipt, TrendingUp, Zap } from "lucide-react";
import type { ReactNode } from "react";

import { Avatar } from "@/components/Avatar";
import { PeriodFilter, isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";

export type StatLine = { leads: number; sales: number; buyers: number; revenue: number; conversion: number; ticket: number };
export type BotStats = {
  period_label: string;
  totals: StatLine & { pix_generated?: number };
  series: (StatLine & { date: string })[];
  flows: Record<string, StatLine>;
  bots: Record<string, StatLine>;
};

type RankingMember = {
  position: number;
  name: string;
  nickname: string;
  avatar_url: string | null;
  is_chief: boolean;
  is_me: boolean;
  has_sales: boolean;
};

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
  });
}

function usePartnersRanking(period: MetricsPeriod) {
  return useQuery({
    queryKey: ["bots", "partners-ranking", periodParams(period)],
    queryFn: () =>
      apiRequest<{ period_label: string; members: RankingMember[] }>(
        `/api/bots/partners-ranking?${new URLSearchParams(periodParams(period))}`,
      ),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
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
        {value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%
      </span>
    </div>
  );
}

const medal = ["text-warning", "text-[#c0c7d4]", "text-[#d08a4a]"];

/** Positions only: the API never sends how much each partner billed. */
function PartnersRanking({ period }: { period: MetricsPeriod }) {
  const ranking = usePartnersRanking(period);
  const members = ranking.data?.members ?? [];
  return (
    <section className="dashboard-card rounded-2xl p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-surface-inset text-warning"><Crown size={16} /></span>
          <div>
            <h3 className="text-sm font-semibold text-fg">Ranking dos sócios</h3>
            <p className="text-[10px] uppercase tracking-[0.14em] text-muted">Corrida de faturamento</p>
          </div>
        </div>
        <span className="text-[11px] text-muted">{ranking.data?.period_label} · valores ficam ocultos</span>
      </div>
      {ranking.isLoading ? (
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {[0, 1, 2].map((key) => <div className="skeleton h-14" key={key} />)}
        </div>
      ) : members.length <= 1 ? (
        <p className="rounded-xl bg-surface-inset px-3 py-4 text-center text-xs text-muted">
          Quando você tiver sócios, a posição de cada um aparece aqui (sem mostrar quanto cada um faturou).
        </p>
      ) : (
        <ol className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {members.map((member) => (
            <li
              className={`flex items-center gap-3 rounded-xl border px-3 py-2.5 ${member.is_me ? "border-accent/60 bg-brand-soft/40" : "border-line-soft bg-surface-inset"}`}
              key={`${member.position}-${member.nickname}`}
            >
              <span className={`w-6 shrink-0 text-center text-sm font-bold ${medal[member.position - 1] ?? "text-muted"}`}>
                {member.position <= 3 ? <Crown className="mx-auto" size={16} /> : `#${member.position}`}
              </span>
              <Avatar className="size-9" name={member.name || member.nickname} src={member.avatar_url} />
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-1.5">
                  <span className={`truncate text-sm font-semibold ${member.position === 1 ? "text-warning" : "text-fg"}`}>@{member.nickname}</span>
                  <span className="shrink-0 rounded bg-well px-1 text-[10px] font-bold text-muted">#{member.position}</span>
                </span>
                <span className="block truncate text-[10px] uppercase tracking-wider text-muted">
                  {member.is_me ? "Você" : member.is_chief ? "Dono da operação" : "Sócio"}
                  {!member.has_sales && " · sem vendas no período"}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

/** FlashBot home: SharkBot-style KPI cards, daily revenue chart and the partners' ranking. */
export function ConversionOverview({ period, onPeriod }: { period: MetricsPeriod; onPeriod: (value: MetricsPeriod) => void }) {
  const stats = useBotStats(period);
  const t = stats.data?.totals;
  const pix = t?.pix_generated ?? 0;
  const paidShare = t && pix ? (100 * t.sales) / pix : 0;
  const series = (stats.data?.series ?? []).map((day) => ({
    ...day,
    label: (stats.data?.series.length ?? 0) <= 7 ? weekday(day.date) : `${day.date.slice(8, 10)}/${day.date.slice(5, 7)}`,
  }));
  const recent = series.slice(-7);
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
            <p className="mt-2 text-center text-[10px] text-muted">{t ? `${count(t.buyers)} compraram de ${count(t.leads)} leads` : ""}</p>
          </StatCard>

          <StatCard icon={<Zap size={16} />} title="Total de starts">
            <p className="text-2xl font-bold text-fg">{t ? count(t.leads) : "—"}</p>
            <p className="text-[10px] text-muted">leads iniciaram conversa</p>
            <p className="mt-1 text-[10px] text-muted">
              <span className="font-semibold text-fg">{t && t.sales ? count(Math.round(t.leads / t.sales)) : "—"}</span> starts por venda
            </p>
            <div className="mt-auto flex h-8 items-end gap-1 pt-2" aria-hidden="true">
              {recent.map((day, index) => (
                <span
                  className={`flex-1 rounded-sm ${index === recent.length - 1 ? "bg-accent" : "bg-accent/35"}`}
                  key={day.date}
                  style={{ height: `${Math.max(8, (100 * day.leads) / peak)}%` }}
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
              <p className="text-[10px] uppercase tracking-[0.14em] text-muted">{stats.data?.period_label ?? ""}</p>
            </div>
          </div>
          <p className="mb-1 flex items-center gap-1.5 text-[11px] text-muted">
            <span className="size-2 rounded-full bg-accent" /> Faturamento por dia
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
                  formatter={(value) => [money(Number(value ?? 0)), "Faturamento"]}
                  labelFormatter={(_, payload) => {
                    const date = payload?.[0]?.payload?.date as string | undefined;
                    return date ? `${date.slice(8, 10)}/${date.slice(5, 7)}` : "";
                  }}
                />
                <Area dataKey="revenue" fill="url(#revenueFill)" stroke="var(--grad-a)" strokeWidth={2.5} type="monotone" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <PartnersRanking period={period} />
    </section>
  );
}
