import { EngagementCards } from "@/components/EngagementCards";
import { ConnectedAccountsCard, PerformanceChart } from "@/features/dashboard/FlashPanelParts";
import { ViewsRankingCard } from "@/features/rankings/RankingLists";
import { isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { usePartnerMe } from "@/features/partners/api";
import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  ChartNoAxesCombined,
  CircleCheck,
  CircleDollarSign,
  Link2,
  Receipt,
  UsersRound,
  type LucideIcon,
} from "lucide-react";

import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { apiRequest } from "@/services/api";
import { GreetingClock } from "@/components/GreetingClock";
import { useAuth } from "@/features/auth/AuthProvider";
import { AlertsBanner } from "@/components/AlertsBanner";
import { useInstagramCallbackToast } from "@/hooks/useInstagramCallbackToast";

type AnalyticsPeriod = InstagramAnalyticsSummary["period"];

const periodOptions: { value: AnalyticsPeriod; label: string }[] = [
  { value: "today", label: "Hoje" },
  { value: "yesterday", label: "Ontem" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "all", label: "Total" },
  { value: "custom", label: "Personalizado" },
];

function formatCount(value: number | null | undefined): string {
  return new Intl.NumberFormat("pt-BR").format(value ?? 0);
}

function localDateInputValue() {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map(({ type, value }) => [type, value]));
  return `${values.year}-${values.month}-${values.day}`;
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
}

function AnimatedMetricValue({
  target,
  loading,
  formatValue,
}: {
  target: number | null;
  loading: boolean;
  formatValue: (value: number) => string;
}) {
  if (target !== null) return <span className="tabular-nums">{formatValue(target)}</span>;
  if (!loading) return <>—</>;

  return (
    <span
      aria-label="Carregando métrica"
      className="inline-flex items-center gap-1.5 align-middle"
      role="status"
    >
      {[0, 1, 2].map((dot) => (
        <span
          aria-hidden="true"
          className="size-2 rounded-full bg-current motion-safe:animate-pulse motion-reduce:animate-none"
          key={dot}
          style={{ animationDelay: `${dot * 180}ms` }}
        />
      ))}
    </span>
  );
}

function MetricCard({
  title,
  target,
  loading,
  formatValue = formatCount,
  detail,
  icon: Icon,
  color,
  trend,
}: {
  title: string;
  target: number | null;
  loading: boolean;
  formatValue?: (value: number) => string;
  detail?: string;
  icon: LucideIcon;
  color: string;
  trend?: ReactNode;
}) {
  return (
    <article className="dashboard-card dashboard-metric-card">
      <div className="dashboard-metric-heading">
        <span className={`dashboard-metric-icon ${color}`}>
          <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
        </span>
        <h2 className="dashboard-metric-title">{title}</h2>
      </div>
      <p className="dashboard-metric-value">
        <AnimatedMetricValue
          formatValue={formatValue}
          loading={loading}
          target={target}
        />
      </p>
      {trend}
      {detail && <p className="dashboard-metric-detail">{detail}</p>}
    </article>
  );
}

type DashboardPageProps = {
  /** Sócio: revenue and sales come from the partnership (sales through shared funnels too). */
  partner?: boolean;
  /** Shown right below the top row (the loops shared with a sócio). */
  belowTop?: ReactNode;
  showAccounts?: boolean;
  showRanking?: boolean;
};

/** The Flash panel, the same layout for everyone: accounts on the side, eight cards, then
 *  the views ranking next to the views/revenue chart. Notices live only in their tab. */
export function DashboardPage({ partner = false, belowTop, showAccounts = true, showRanking = true }: DashboardPageProps = {}) {
  const { user } = useAuth();
  const isSuperAdmin = user?.role === "SUPER_ADMIN";
  useInstagramCallbackToast();
  const [period, setPeriod] = useState<AnalyticsPeriod>("today");
  const [startDate, setStartDate] = useState(localDateInputValue);
  const [endDate, setEndDate] = useState(localDateInputValue);
  const summary = useQuery({
    queryKey: [
      "analytics",
      "summary",
      "fast",
      period,
      period === "custom" ? startDate : null,
      period === "custom" ? endDate : null,
    ],
    queryFn: () => {
      const query = new URLSearchParams({ period });
      if (period === "custom") {
        query.set("start_date", startDate);
        query.set("end_date", endDate);
      }
      return apiRequest<InstagramAnalyticsSummary>(`/api/analytics/summary?${query}`);
    },
    retry: false,
    staleTime: 60_000,
    placeholderData: (previousData) => previousData,
  });
  const metaSummary = useQuery({
    queryKey: [
      "analytics",
      "summary",
      "meta",
      period,
      period === "custom" ? startDate : null,
      period === "custom" ? endDate : null,
    ],
    queryFn: () => {
      const query = new URLSearchParams({
        period,
        include_meta_insights: "true",
      });
      if (period === "custom") {
        query.set("start_date", startDate);
        query.set("end_date", endDate);
      }
      return apiRequest<InstagramAnalyticsSummary>(`/api/analytics/summary?${query}`);
    },
    enabled: Boolean(summary.data && summary.data.active_accounts > 0),
    retry: false,
    staleTime: 5 * 60_000,
  });
  const metrics = metaSummary.data ?? summary.data;
  const fastLoading = summary.isFetching && !summary.data;
  const viewsUnavailable =
    !metrics ||
    !metrics.insights_checked ||
    metrics.active_accounts === 0 ||
    metrics.insights_unavailable ||
    metrics.missing_permissions.length > 0;
  const droppedKinds = (metrics?.disconnected_period_accounts ?? []).reduce<Record<string, number>>(
    (acc, item) => ({ ...acc, [item.kind]: (acc[item.kind] ?? 0) + 1 }),
    {},
  );
  const droppedDetail = [
    droppedKinds.suspended ? `${droppedKinds.suspended} suspensa(s)` : null,
    droppedKinds.restricted ? `${droppedKinds.restricted} restrita(s)` : null,
    droppedKinds.expired ? `${droppedKinds.expired} com autorização expirada` : null,
    droppedKinds.manual ? `${droppedKinds.manual} desconectada(s) manualmente` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  const rankingPeriod: MetricsPeriod = { period, start: startDate, end: endDate };
  const partnerMe = usePartnerMe(periodParams(rankingPeriod), partner && isPeriodReady(rankingPeriod));
  const totals = partner ? partnerMe.data?.totals : undefined;
  const revenue = totals ? { amount: totals.gross, sales: totals.sales } : null;
  // A lean panel: revenue, views, accounts and posts of the period. The money free to
  // withdraw lives only in the wallet.
  const metricsCards: Parameters<typeof MetricCard>[0][] = [
    {
      title: isSuperAdmin ? "Faturado no período" : "Faturamento",
      target: revenue ? revenue.amount : metrics ? Number(metrics.period_revenue ?? 0) : null,
      loading: fastLoading,
      formatValue: formatMoney,
      icon: CircleDollarSign,
      color: "text-success",
    },
    {
      title: "Vendas",
      target: revenue ? revenue.sales : metrics?.period_sales ?? null,
      loading: fastLoading,
      icon: Receipt,
      color: "text-accent",
    },
    {
      title: "Visualizações no período",
      target: viewsUnavailable ? null : metrics?.period_views_count ?? null,
      loading:
        !viewsUnavailable
          ? false
          : Boolean(
              metrics?.active_accounts &&
                metaSummary.isFetching &&
                !metaSummary.error &&
                !metrics.insights_checked,
            ),
      detail:
        viewsUnavailable
          ? metaSummary.isFetching
            ? "Consultando a Meta"
            : metaSummary.error
              ? "A Meta não retornou os Insights; consulte as notificações"
              : "Consulte as notificações para verificar os Insights da Meta"
          : metrics?.period_views_count === null || metrics?.period_views_count === undefined
            ? "A Meta não retornou o total do período"
            : "Ocorridas no período (Insights da Meta)",
      icon: ChartNoAxesCombined,
      color: "text-accent",
    },
    {
      title: "Contas ativas",
      target: metrics?.active_accounts ?? null,
      loading: fastLoading,
      detail: "Com autorização válida",
      icon: UsersRound,
      color: "text-accent",
    },
    {
      title: "Posts no período",
      target: metrics?.published_posts ?? null,
      loading: fastLoading,
      detail: "Publicados pelo Flash",
      icon: CircleCheck,
      color: "text-success",
    },
  ];

  return (
    <div className="dashboard-ambient min-h-[calc(100vh-144px)] w-full space-y-4">
      <GreetingClock nickname={user?.nickname} />
      <AlertsBanner />
      <header className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <Link className="btn-primary" to="/feature/accounts?connect=1">
            <Link2 size={16} />
            Conectar conta
          </Link>
        </div>
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

      {(summary.isFetching || metaSummary.isFetching) && (
        <p className="text-xs text-muted" role="status">
          {summary.isFetching
            ? "Atualizando indicadores do painel…"
            : "Atualizando métricas da Meta em segundo plano…"}
        </p>
      )}

      <div className={`grid gap-4 ${showAccounts ? "xl:grid-cols-[320px_minmax(0,1fr)]" : ""}`}>
        {showAccounts && <ConnectedAccountsCard summary={summary.data} />}
        <section
          aria-label="Indicadores numéricos do workspace"
          className="grid auto-rows-fr grid-cols-2 gap-3 md:grid-cols-4"
        >
          <article className="dashboard-card dashboard-metric-card">
            <div className="dashboard-metric-heading">
              <span className="dashboard-metric-icon text-accent">
                <Link2 size={16} />
              </span>
              <h2 className="dashboard-metric-title">Conexões do período</h2>
            </div>
            <div className="flex items-end gap-3 sm:gap-4">
              <div>
                <p className="dashboard-metric-value text-success">{formatCount(metrics?.connected_period)}</p>
                <p className="text-[10px] text-muted sm:text-[11px]">conectadas</p>
              </div>
              <div>
                <p className="dashboard-metric-value text-danger">{formatCount(metrics?.disconnected_period)}</p>
                <p className="text-[10px] text-muted sm:text-[11px]">desconectadas</p>
              </div>
            </div>
            <p className="dashboard-metric-detail">
              {droppedDetail || "Nenhuma queda de conta no período"}
            </p>
          </article>
          {metricsCards.map((metric) => (
            <MetricCard key={metric.title} {...metric} />
          ))}
          <EngagementCards />
        </section>
      </div>
      {belowTop}
      <div className={`grid gap-4 ${showRanking ? "lg:grid-cols-2" : ""}`}>
        {showRanking && <ViewsRankingCard period={rankingPeriod} />}
        <PerformanceChart period={rankingPeriod} />
      </div>
    </div>
  );
}
