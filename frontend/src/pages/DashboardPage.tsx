import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChartNoAxesCombined,
  CircleCheck,
  Clock3,
  UserRoundX,
  UsersRound,
  Wallet,
  type LucideIcon,
} from "lucide-react";

import { LoadingState } from "@/components/PageState";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { apiRequest } from "@/services/api";

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
      <div className="dashboard-metric-heading">
        <span className={`dashboard-metric-icon ${color}`}>
          <Icon aria-hidden="true" size={18} strokeWidth={1.8} />
        </span>
        <h2 className="dashboard-metric-title">{title}</h2>
      </div>
      <p className="dashboard-metric-value">{value}</p>
      <p className="dashboard-metric-detail">{detail}</p>
    </article>
  );
}

export function DashboardPage() {
  const [period, setPeriod] = useState<AnalyticsPeriod>("7d");
  const [startDate, setStartDate] = useState(localDateInputValue);
  const [endDate, setEndDate] = useState(localDateInputValue);
  const summary = useQuery({
    queryKey: [
      "analytics",
      "summary",
      period,
      period === "custom" ? startDate : null,
      period === "custom" ? endDate : null,
    ],
    queryFn: () => {
      const query = new URLSearchParams({ period, include_meta_insights: "true" });
      if (period === "custom") {
        query.set("start_date", startDate);
        query.set("end_date", endDate);
      }
      return apiRequest<InstagramAnalyticsSummary>(`/api/analytics/summary?${query}`);
    },
    retry: false,
  });
  const metrics = summary.data;
  const pixGenerated = metrics?.pix_generated ?? 0;
  const pixPaid = metrics?.pix_paid ?? 0;
  const pixConversion =
    pixGenerated > 0 ? Math.round((pixPaid / pixGenerated) * 100) : 0;
  const accountsWithIssues =
    (metrics?.errored_accounts ?? 0) +
    (metrics?.disconnected_accounts ?? 0) +
    (metrics?.expired_accounts ?? 0);
  const viewsUnavailable =
    !metrics ||
    metrics.active_accounts === 0 ||
    metrics.insights_unavailable ||
    metrics.missing_permissions.length > 0;
  const dailyConnections = metrics?.daily_account_connections ?? [];
  const dailyConnectionMaximum = Math.max(
    ...dailyConnections.map(({ connected_accounts }) => connected_accounts),
    1,
  );
  const dailyConnectionPoints = dailyConnections.map(({ connected_accounts }, index) => {
    const x =
      dailyConnections.length > 1
        ? (index / (dailyConnections.length - 1)) * 100
        : 50;
    const y = 38 - (connected_accounts / dailyConnectionMaximum) * 30;
    return `${x},${y}`;
  });
  const dailyConnectionArea = dailyConnectionPoints.length
    ? `0,42 ${dailyConnectionPoints.join(" ")} 100,42`
    : "";
  const topConnectionCount = Math.max(
    ...((metrics?.account_connection_ranking ?? []).map(
      ({ connected_accounts }) => connected_accounts,
    )),
    1,
  );
  const metricsCards = [
    {
      title: "Total de visualizações",
      value:
        viewsUnavailable
          ? "—"
          : formatCount(metrics?.views_count),
      detail:
        viewsUnavailable
          ? "Consulte as notificações para verificar os Insights da Meta"
          : "Insights recebidos da Meta no período",
      icon: ChartNoAxesCombined,
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
      title: "Colaboradores ativos",
      value: formatCount(metrics?.active_collaborators),
      detail: "Membros ativos deste workspace",
      icon: UsersRound,
      color: "text-[#71c8e8]",
    },
    {
      title: "Seguidores",
      value:
        metrics?.followers_count == null
          ? "—"
          : formatCount(metrics.followers_count),
      detail: metrics?.profile_metrics_unavailable
        ? "Meta indisponível; mostrando último valor salvo"
        : "Atualizado diretamente pela Meta",
      icon: UsersRound,
      color: "text-[#aab7ff]",
    },
    {
      title: "Mídias nos perfis",
      value:
        metrics?.media_count == null
          ? "—"
          : formatCount(metrics.media_count),
      detail: metrics?.profile_metrics_unavailable
        ? "Meta indisponível; mostrando último valor salvo"
        : "Atualizado diretamente pela Meta",
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
      detail: "Publicações que precisam de atenção",
      icon: AlertTriangle,
      color: "text-[#f16f82]",
    },
    {
      title: "Contas com erro",
      value: formatCount(accountsWithIssues),
      detail: "Desconectadas ou com autorização expirada",
      icon: UserRoundX,
      color: "text-[#f16f82]",
    },
    {
      title: "Leads Sharkbot",
      value: formatCount(metrics?.leads),
      detail: "Recebidos no período",
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
      title: "Conversão de Pix",
      value: `${pixConversion}%`,
      detail: "Pagos em relação aos gerados no período",
      icon: ChartNoAxesCombined,
      color: "text-[#b171ff]",
    },
    {
      title: "Valor faturado",
      value: formatMoney(Number(metrics?.pix_paid_amount ?? 0)),
      detail: "Pix pagos no período, pelo horário de Brasília",
      icon: Wallet,
      color: "text-[#76c8a0]",
    },
  ];

  return (
    <div className="dashboard-ambient min-h-[calc(100vh-144px)] w-full space-y-6">
      <header className="space-y-4">
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
          Período das métricas
        </p>
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

      {summary.isLoading && <LoadingState label="Carregando métricas do dashboard" />}

      <main className="dashboard-layout">
        <section
          aria-label="Indicadores numéricos do workspace"
          className="dashboard-metrics"
        >
          {metricsCards.map((metric) => (
            <MetricCard key={metric.title} {...metric} />
          ))}
        </section>
      </main>
      <section
        aria-label="Resumo da equipe e novas contas"
        className="grid gap-4 xl:grid-cols-3"
      >
        <article className="dashboard-card rounded-xl p-5">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-[#8295ff]">
              Equipe
            </p>
            <h2 className="mt-1 text-base font-semibold text-[#e6eaf2]">
              Ranking de conexões
            </h2>
            <p className="mt-1 text-xs text-[#718096]">
              Contas conectadas no período selecionado
            </p>
          </div>
          {metrics?.account_connection_ranking.length ? (
            <ol className="mt-4 space-y-3">
              {metrics.account_connection_ranking.slice(0, 5).map((member, index) => (
                <li className="flex items-center gap-3" key={member.user_id}>
                  <span className="grid size-7 shrink-0 place-items-center rounded-full bg-[#171e31] text-xs font-semibold text-[#aab7ff]">
                    {index + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm text-[#dce2f0]">
                        {member.full_name}
                      </span>
                      <span className="shrink-0 text-xs text-[#94a3b8]">
                        {formatCount(member.connected_accounts)}
                      </span>
                    </div>
                    <div className="mt-1 flex items-center gap-2">
                      <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-[#202838]">
                        <div
                          className="h-full rounded-full bg-[#7187ff]"
                          style={{
                            width: `${(member.connected_accounts / topConnectionCount) * 100}%`,
                          }}
                        />
                      </div>
                      <span className="text-[10px] text-[#718096]">
                        {member.role === "OWNER" ? "Chefe" : "Colaborador"}
                      </span>
                    </div>
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-4 text-sm text-[#94a3b8]">
              Nenhuma conexão registrada no período.
            </p>
          )}
        </article>

        <article className="dashboard-card rounded-xl p-5">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-[#8295ff]">
              Saúde das contas
            </p>
            <h2 className="mt-1 text-base font-semibold text-[#e6eaf2]">
              Ativas e que precisam de atenção
            </h2>
          </div>
          <p className="mt-4 text-3xl font-semibold tracking-[-0.045em] text-[#f5f7fb]">
            {formatCount(metrics?.active_accounts)}
            <span className="ml-2 text-sm font-normal tracking-normal text-[#94a3b8]">
              ativas
            </span>
          </p>
          <ul className="mt-3 space-y-2 border-t border-[#202838] pt-3 text-sm">
            <li className="flex items-center justify-between gap-3">
              <span className="text-[#f1a3ad]">Com erro</span>
              <span className="font-medium text-[#e6eaf2]">
                {formatCount(metrics?.errored_accounts)}
              </span>
            </li>
            <li className="flex items-center justify-between gap-3">
              <span className="text-[#f2d48a]">Desconectadas</span>
              <span className="font-medium text-[#e6eaf2]">
                {formatCount(metrics?.disconnected_accounts)}
              </span>
            </li>
            <li className="flex items-center justify-between gap-3">
              <span className="text-[#f2d48a]">Autorização expirada</span>
              <span className="font-medium text-[#e6eaf2]">
                {formatCount(metrics?.expired_accounts)}
              </span>
            </li>
          </ul>
        </article>

        <article className="dashboard-card rounded-xl p-5">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.12em] text-[#8295ff]">
              Crescimento
            </p>
            <h2 className="mt-1 text-base font-semibold text-[#e6eaf2]">
              Novas contas por dia
            </h2>
            <p className="mt-1 text-xs text-[#718096]">
              No máximo 30 dias do período selecionado
            </p>
          </div>
          {dailyConnections.length ? (
            <>
              <svg
                aria-label="Gráfico diário de contas conectadas"
                className="mt-4 h-28 w-full overflow-visible"
                preserveAspectRatio="none"
                role="img"
                viewBox="0 0 100 44"
              >
                <defs>
                  <linearGradient id="accountConnectionsFill" x1="0" x2="0" y1="0" y2="1">
                    <stop offset="0%" stopColor="#7187ff" stopOpacity="0.34" />
                    <stop offset="100%" stopColor="#7187ff" stopOpacity="0.01" />
                  </linearGradient>
                </defs>
                <polygon fill="url(#accountConnectionsFill)" points={dailyConnectionArea} />
                <polyline
                  fill="none"
                  points={dailyConnectionPoints.join(" ")}
                  stroke="#8295ff"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="1.5"
                  vectorEffect="non-scaling-stroke"
                />
              </svg>
              <div className="flex justify-between text-[10px] text-[#718096]">
                <span>
                  {new Intl.DateTimeFormat("pt-BR", {
                    day: "2-digit",
                    month: "short",
                    timeZone: "America/Sao_Paulo",
                  }).format(new Date(`${dailyConnections[0].day}T12:00:00`))}
                </span>
                <span>
                  {new Intl.DateTimeFormat("pt-BR", {
                    day: "2-digit",
                    month: "short",
                    timeZone: "America/Sao_Paulo",
                  }).format(
                    new Date(
                      `${dailyConnections[dailyConnections.length - 1].day}T12:00:00`,
                    ),
                  )}
                </span>
              </div>
            </>
          ) : (
            <p className="mt-4 text-sm text-[#94a3b8]">
              Sem dados diários de conexão para exibir.
            </p>
          )}
        </article>
      </section>
    </div>
  );
}
