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

import { ErrorState, LoadingState } from "@/components/PageState";
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
  const accountsWithIssues = Math.max(
    0,
    (metrics?.accounts.length ?? 0) - (metrics?.active_accounts ?? 0),
  );
  const metricsCards = [
    {
      title: "Total de visualizações",
      value: formatCount(metrics?.views_count),
      detail: "Insights recebidos da Meta no período",
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
      value: formatCount(metrics?.followers_count),
      detail: "Snapshot das contas selecionadas",
      icon: UsersRound,
      color: "text-[#aab7ff]",
    },
    {
      title: "Mídias nos perfis",
      value: formatCount(metrics?.media_count),
      detail: "Snapshot de mídia retornado pela Meta",
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
      detail: "Pix pagos no período, pelo horário local",
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

      {summary.error && (
        <ErrorState message="Não foi possível carregar as métricas deste workspace." />
      )}
      {summary.isLoading && <LoadingState label="Carregando métricas do dashboard" />}
      {metrics?.missing_permissions.map((permission) => (
        <article
          className="rounded-xl border border-[#6b552b] bg-[#1c180e] p-4 text-sm text-[#f2d48a]"
          key={permission}
          role="alert"
        >
          <h2 className="font-semibold">Analytics da Meta indisponível</h2>
          <p className="mt-1">
            Permissão de API ausente: <code className="font-mono">{permission}</code>.
            Reconecte as contas e conceda essa permissão no fluxo de autorização do Instagram.
          </p>
        </article>
      ))}
      {metrics?.insights_unavailable && (
        <article
          className="rounded-xl border border-[#6b552b] bg-[#1c180e] p-4 text-sm text-[#f2d48a]"
          role="status"
        >
          Algumas métricas de visualizações não puderam ser carregadas da Meta. Verifique a
          autorização e tente novamente.
        </article>
      )}

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
    </div>
  );
}
