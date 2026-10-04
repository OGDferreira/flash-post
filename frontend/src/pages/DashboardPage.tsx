import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useReducedMotion } from "framer-motion";
import {
  AlertTriangle,
  ChartNoAxesCombined,
  CircleCheck,
  Clock3,
  Eye,
  UserRoundX,
  Search,
  UsersRound,
  Wallet,
  type LucideIcon,
} from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ErrorState, LoadingState } from "@/components/PageState";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { apiRequest } from "@/services/api";

type AnalyticsPeriod = InstagramAnalyticsSummary["period"];
type InstagramAccount = {
  id: string;
  username: string;
  status: "connected" | "disconnected" | "error";
  token_expires_at: string;
};

type CollaboratorRankingResponse = {
  month: string;
  total_connections: number;
  collaborators: {
    user_id: string;
    full_name: string;
    nickname: string;
    connections: number;
    position: number;
  }[];
};

const periodOptions: { value: AnalyticsPeriod; label: string }[] = [
  { value: "today", label: "Hoje" },
  { value: "yesterday", label: "Ontem" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "all", label: "Total" },
  { value: "custom", label: "Personalizado" },
];

function formatCount(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat("pt-BR").format(value);
}

function formatDay(day: string): string {
  return new Date(`${day}T00:00:00Z`).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "UTC",
  });
}

function localDateInputValue() {
  const now = new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function localMonthInputValue() {
  return localDateInputValue().slice(0, 7);
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(value);
}

function MetricCard({
  title,
  value,
  detail,
  icon: Icon,
  color,
}: {
  title: string;
  value: string;
  detail: string;
  icon: LucideIcon;
  color: string;
}) {
  return (
    <article className="dashboard-card dashboard-metric-card">
      <span className={`dashboard-metric-icon ${color}`}>
        <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
      </span>
      <p className="dashboard-metric-value">{value}</p>
      <div className="min-w-0">
        <h2 className="dashboard-metric-title">{title}</h2>
        <p className="dashboard-metric-detail">{detail}</p>
      </div>
    </article>
  );
}

export function DashboardPage() {
  const reduceMotion = useReducedMotion();
  const [period, setPeriod] = useState<AnalyticsPeriod>("7d");
  const [startDate, setStartDate] = useState(localDateInputValue);
  const [endDate, setEndDate] = useState(localDateInputValue);
  const [rankingMonth, setRankingMonth] = useState(localMonthInputValue);
  const [searchTerm, setSearchTerm] = useState("");
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<{ accounts: InstagramAccount[] }>("/api/instagram/accounts"),
    refetchInterval: 60_000,
    retry: false,
  });

  const matchingAccounts = useMemo(() => {
    const query = searchTerm.trim().replace(/^@/, "").toLocaleLowerCase("pt-BR");
    return (accounts.data?.accounts ?? []).filter((account) =>
      account.username.toLocaleLowerCase("pt-BR").includes(query),
    );
  }, [accounts.data?.accounts, searchTerm]);
  const accountIds = useMemo(
    () => matchingAccounts.map(({ id }) => id).sort(),
    [matchingAccounts],
  );

  const summary = useQuery({
    queryKey: [
      "analytics",
      "summary",
      period,
      period === "custom" ? startDate : null,
      period === "custom" ? endDate : null,
      accountIds,
    ],
    queryFn: () => {
      const query = new URLSearchParams({ period });
      if (period === "custom") {
        query.set("start_date", startDate);
        query.set("end_date", endDate);
      }
      accountIds.forEach((id) => query.append("account_ids", id));
      return apiRequest<InstagramAnalyticsSummary>(`/api/analytics/summary?${query}`);
    },
    enabled: !accounts.isLoading && accountIds.length > 0,
    retry: false,
  });
  const ranking = useQuery({
    queryKey: ["collaborators", "ranking", rankingMonth],
    queryFn: () =>
      apiRequest<CollaboratorRankingResponse>(
        `/api/collaborators/ranking?month=${encodeURIComponent(rankingMonth)}`,
      ),
    retry: false,
  });
  const metrics = summary.data;
  const accountsWithIssues = matchingAccounts.filter(
    (account) =>
      account.status !== "connected" ||
      Date.parse(account.token_expires_at) <= Date.now(),
  ).length;
  const pixGenerated = metrics?.pix_generated ?? 0;
  const pixPaid = metrics?.pix_paid ?? 0;
  const pixConversion =
    pixGenerated > 0 ? Math.round((pixPaid / pixGenerated) * 100) : null;
  const totalRevenue =
    metrics && metrics.pix_paid > 0
      ? formatMoney(Number(metrics.pix_paid_amount))
      : "R$ —";

  const metricsCards = [
    {
      title: "Total de visualizações",
      value: "—",
      detail: "Insights da Meta não integrados",
      icon: Eye,
      color: "text-[#71c8e8]",
    },
    {
      title: "Contas ativas",
      value: formatCount(metrics?.active_accounts),
      detail: "Com autorização válida",
      icon: UsersRound,
      color: "text-[#8295ff]",
    },
    {
      title: "Seguidores líquidos",
      value: "—",
      detail: "Variação exige histórico de snapshots",
      icon: UsersRound,
      color: "text-[#aab7ff]",
    },
    {
      title: "Taxa de conversão",
      value: "—",
      detail: "Sem dados de visitantes e conversões",
      icon: ChartNoAxesCombined,
      color: "text-[#b171ff]",
    },
    {
      title: "Posts no período",
      value: formatCount(metrics?.published_posts),
      detail: "Publicados pelo FlashPost",
      icon: CircleCheck,
      color: "text-[#76c8a0]",
    },
    {
      title: "Na fila",
      value: formatCount(metrics?.queued_posts),
      detail: "Aguardando processamento",
      icon: Clock3,
      color: "text-[#f2d48a]",
    },
    {
      title: "Falhas",
      value: formatCount(metrics?.failed_posts),
      detail: "Precisam de atenção",
      icon: AlertTriangle,
      color: "text-[#f16f82]",
    },
    {
      title: "Contas com erro",
      value: formatCount(accountsWithIssues),
      detail: "Desconectadas ou com token expirado",
      icon: UserRoundX,
      color: "text-[#f16f82]",
    },
    {
      title: "Leads Sharkbot",
      value: formatCount(metrics?.leads),
      detail: "Leads recebidos no período",
      icon: UsersRound,
      color: "text-[#71c8e8]",
    },
    {
      title: "Pix gerados",
      value: formatCount(metrics?.pix_generated),
      detail: "Pagamentos iniciados no período",
      icon: Wallet,
      color: "text-[#f2d48a]",
    },
    {
      title: "Pix pagos",
      value: formatCount(metrics?.pix_paid),
      detail: "Pagamentos aprovados no período",
      icon: CircleCheck,
      color: "text-[#76c8a0]",
    },
    {
      title: "Valor faturado",
      value: totalRevenue,
      detail: "Total de Pix pagos no período",
      icon: Wallet,
      color: "text-[#76c8a0]",
    },
  ];
  const revenueSeries = (metrics?.daily_revenue ?? []).map(({ day, amount }) => ({
    day: formatDay(day),
    revenue: Number(amount),
  }));
  return (
    <div className="dashboard-ambient min-h-[calc(100vh-144px)] w-full space-y-6">
      <header className="space-y-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
            Período
          </p>
        </div>
        <div className="dashboard-toolbar">
          <label className="dashboard-search">
            <Search aria-hidden="true" size={16} />
            <span className="sr-only">Pesquisar contas</span>
            <input
              aria-label="Pesquisar contas do Instagram"
              onChange={(event) => setSearchTerm(event.target.value)}
              placeholder="PESQUISAR"
              type="search"
              value={searchTerm}
            />
          </label>
          <div aria-label="Filtrar por período" className="dashboard-periods" role="group">
            {periodOptions.map(({ value, label }) => (
              <button
                aria-pressed={period === value}
                className={period === value ? "is-selected" : ""}
                key={value}
                onClick={() => setPeriod(value)}
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
        </div>
        {period === "custom" && (
          <div className="dashboard-date-range">
            <label>
              De
              <input
                aria-label="Data inicial"
                max={endDate}
                onChange={(event) => setStartDate(event.target.value)}
                type="date"
                value={startDate}
              />
            </label>
            <label>
              Até
              <input
                aria-label="Data final"
                min={startDate}
                onChange={(event) => setEndDate(event.target.value)}
                type="date"
                value={endDate}
              />
            </label>
          </div>
        )}
      </header>

      {accounts.error && (
        <ErrorState message="Não foi possível carregar as contas deste workspace." />
      )}
      {summary.error && (
        <ErrorState message="Não foi possível carregar as métricas deste workspace." />
      )}
      {(accounts.isLoading || summary.isLoading) && (
        <LoadingState label="Carregando métricas do dashboard" />
      )}

      <section aria-label="Produção de conexões hoje" className="grid gap-3 sm:grid-cols-2">
        <article className="dashboard-card rounded-xl p-4">
          <p className="text-xs text-[#94a3b8]">Contas conectadas por você hoje</p>
          <p className="mt-2 text-2xl font-semibold text-[#f5f7fb]">
            {formatCount(metrics?.owner_connections_today)}
          </p>
        </article>
        <article className="dashboard-card rounded-xl p-4">
          <p className="text-xs text-[#94a3b8]">Contas conectadas pela equipe hoje</p>
          <p className="mt-2 text-2xl font-semibold text-[#aab7ff]">
            {formatCount(metrics?.team_connections_today)}
          </p>
        </article>
      </section>

      <section aria-label="Ranking mensal de colaboradores" className="dashboard-card space-y-4 rounded-xl p-4 sm:p-5">
        <header className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="dashboard-eyebrow">Equipe</p>
            <h2 className="dashboard-panel-title">Ranking de conexões no mês</h2>
          </div>
          <label className="flex items-center gap-2 text-xs text-[#94a3b8]">
            Mês
            <input
              aria-label="Mês do ranking"
              className="min-h-9 rounded-lg border border-[#27334a] bg-[#090b0f] px-2 text-sm text-[#f5f7fb]"
              max={localMonthInputValue()}
              onChange={(event) => setRankingMonth(event.target.value)}
              type="month"
              value={rankingMonth}
            />
          </label>
        </header>
        {ranking.error ? (
          <p className="text-sm text-[#f1a3ad]">Não foi possível carregar o ranking.</p>
        ) : ranking.isLoading ? (
          <p className="text-sm text-[#94a3b8]">Carregando ranking...</p>
        ) : ranking.data?.collaborators.length ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[420px] text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-[#64748b]">
                <tr>
                  <th className="py-2 pr-3 font-medium">Posição</th>
                  <th className="py-2 pr-3 font-medium">Colaborador</th>
                  <th className="py-2 text-right font-medium">Conexões</th>
                </tr>
              </thead>
              <tbody>
                {ranking.data.collaborators.map((person) => (
                  <tr className="border-t border-[#202838]" key={person.user_id}>
                    <td className="py-3 pr-3 font-semibold text-[#aab7ff]">#{person.position}</td>
                    <td className="py-3 pr-3 text-[#e6eaf2]">@{person.nickname}</td>
                    <td className="py-3 text-right font-semibold text-[#f5f7fb]">
                      {formatCount(person.connections)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-[#34446f] text-[#cbd5e1]">
                  <th className="py-3 pr-3" colSpan={2}>Total da equipe</th>
                  <td className="py-3 text-right font-semibold">
                    {formatCount(ranking.data.total_connections)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        ) : (
          <p className="text-sm text-[#94a3b8]">
            Nenhuma conexão de colaborador registrada neste mês.
          </p>
        )}
      </section>

      <main className="dashboard-layout">
        <section aria-label="Indicadores do workspace" className="dashboard-metrics">
          {metricsCards.map((metric) => (
            <MetricCard key={metric.title} {...metric} />
          ))}
        </section>

        <section aria-label="Análises do workspace" className="dashboard-visuals">
          <article className="dashboard-card dashboard-chart-panel">
            <header className="dashboard-panel-header">
              <div>
                <p className="dashboard-eyebrow">Financeiro</p>
                <h2 className="dashboard-panel-title">Rendimento financeiro</h2>
              </div>
              <div className="dashboard-revenue-total">
                <span>Total vendido no período</span>
                <strong>{totalRevenue}</strong>
              </div>
            </header>
            <div className="dashboard-revenue-chart" aria-live="polite">
              <ResponsiveContainer height="100%" width="100%">
                <AreaChart data={revenueSeries} margin={{ top: 10, right: 12, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="revenueFill" x1="0" x2="0" y1="0" y2="1">
                      <stop offset="0%" stopColor="#8295ff" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#8295ff" stopOpacity={0.015} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid stroke="#232a3b" strokeDasharray="3 3" vertical={false} />
                  <XAxis dataKey="day" stroke="#64748b" tick={{ fontSize: 10 }} />
                  <YAxis
                    stroke="#64748b"
                    tick={{ fontSize: 10 }}
                    tickFormatter={(value: number) => `R$${value}`}
                    width={52}
                  />
                  <Tooltip
                    formatter={(value) => [formatMoney(Number(value)), "Pix pagos"]}
                    contentStyle={{
                      background: "#0d1015",
                      border: "1px solid #27334a",
                      borderRadius: 8,
                    }}
                  />
                  <Area
                    dataKey="revenue"
                    fill="url(#revenueFill)"
                    stroke="#8295ff"
                    strokeWidth={2}
                    type="monotone"
                  />
                </AreaChart>
              </ResponsiveContainer>
              {revenueSeries.length === 0 && <div className="dashboard-chart-empty">
                <Wallet aria-hidden="true" size={22} />
                <p>Nenhum Pix pago no período</p>
                <span>
                  Os valores são preenchidos pelos eventos aprovados recebidos do Sharkbot.
                </span>
              </div>}
            </div>
          </article>

          <div className="dashboard-bottom-panels">
            <article className="dashboard-card dashboard-summary-panel">
              <header className="dashboard-panel-header">
                <div>
                  <p className="dashboard-eyebrow">Pagamentos</p>
                  <h2 className="dashboard-panel-title">Conversão de Pix</h2>
                </div>
              </header>
              <p className="dashboard-summary-value">
                {pixConversion === null ? "—" : `${pixConversion}%`}
              </p>
              <p className="dashboard-summary-detail">Pix pagos em relação aos gerados</p>
            </article>

            <article className="dashboard-card dashboard-summary-panel">
              <header className="dashboard-panel-header">
                <div>
                  <p className="dashboard-eyebrow">Sharkbot</p>
                  <h2 className="dashboard-panel-title">Taxa de lead</h2>
                </div>
              </header>
              <p className="dashboard-summary-value">—</p>
              <p className="dashboard-summary-detail">
                {formatCount(metrics?.leads)} leads no período; visitantes não integrados.
              </p>
            </article>

            <article className="dashboard-card dashboard-summary-panel">
              <header className="dashboard-panel-header">
                <div>
                  <p className="dashboard-eyebrow">Status</p>
                  <h2 className="dashboard-panel-title">Pix gerados e pagos</h2>
                </div>
              </header>
              <div className="dashboard-payment-stats">
                <div>
                  <span>Gerados</span>
                  <strong>{formatCount(metrics?.pix_generated)}</strong>
                </div>
                <div>
                  <span>Pagos</span>
                  <strong>{formatCount(metrics?.pix_paid)}</strong>
                </div>
              </div>
              <div
                aria-label={`Conversão de Pix: ${pixConversion ?? 0}%`}
                aria-valuemax={100}
                aria-valuemin={0}
                aria-valuenow={pixConversion ?? 0}
                className="dashboard-payment-track"
                role="progressbar"
              >
                <span style={{ width: `${pixConversion ?? 0}%` }} />
              </div>
            </article>
          </div>
        </section>
      </main>

      {metrics?.daily_publications.length ? (
        <article className="dashboard-card dashboard-history-panel">
          <header className="dashboard-panel-header">
            <div>
              <p className="dashboard-eyebrow">FlashPost</p>
              <h2 className="dashboard-panel-title">Publicações concluídas por dia</h2>
            </div>
          </header>
          <div className="h-[220px] w-full">
            <ResponsiveContainer height="100%" width="100%">
              <AreaChart
                data={metrics.daily_publications}
                margin={{ top: 8, right: 12, left: -16, bottom: 0 }}
              >
                <defs>
                  <linearGradient id="dashboardPublishedFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#7187ff" stopOpacity={0.34} />
                    <stop offset="95%" stopColor="#7187ff" stopOpacity={0.015} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#232a3b" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  axisLine={false}
                  dataKey="day"
                  tick={{ fill: "#778198", fontSize: 11 }}
                  tickFormatter={formatDay}
                  tickLine={false}
                />
                <YAxis
                  allowDecimals={false}
                  axisLine={false}
                  tick={{ fill: "#778198", fontSize: 11 }}
                  tickLine={false}
                />
                <Tooltip
                  contentStyle={{
                    background: "#10141b",
                    border: "1px solid #303954",
                    borderRadius: 10,
                    color: "#f5f7fb",
                  }}
                  labelFormatter={(day) => formatDay(String(day))}
                />
                <Area
                  animationDuration={reduceMotion ? 0 : 450}
                  dataKey="published_posts"
                  fill="url(#dashboardPublishedFill)"
                  name="Publicações"
                  stroke="#8295ff"
                  strokeWidth={2.5}
                  type="monotone"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </article>
      ) : null}
      {!accounts.isLoading && matchingAccounts.length === 0 && (
        <p className="text-center text-sm text-[#f2d48a]">
          Nenhuma conta corresponde à pesquisa.
        </p>
      )}
    </div>
  );
}
