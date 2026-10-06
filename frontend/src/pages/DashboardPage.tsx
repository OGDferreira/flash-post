import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  ChartNoAxesCombined,
  CircleCheck,
  BellRing,
  Clock3,
  UserRoundX,
  UsersRound,
  Wallet,
  Volume2,
  type LucideIcon,
} from "lucide-react";

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

function formatPercent(value: number): string {
  return `${Math.round(value)}%`;
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
}: {
  title: string;
  target: number | null;
  loading: boolean;
  formatValue?: (value: number) => string;
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
      <p className="dashboard-metric-value">
        <AnimatedMetricValue
          formatValue={formatValue}
          loading={loading}
          target={target}
        />
      </p>
      <p className="dashboard-metric-detail">{detail}</p>
    </article>
  );
}

export function DashboardPage() {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<AnalyticsPeriod>("7d");
  const [startDate, setStartDate] = useState(localDateInputValue);
  const [endDate, setEndDate] = useState(localDateInputValue);
  const [dailyGoalDraft, setDailyGoalDraft] = useState<string | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [soundError, setSoundError] = useState<string | null>(null);
  const seenSaleIds = useRef<Set<string> | null>(null);
  const smokepayFinance = useQuery({
    queryKey: ["analytics", "smokepay"],
    queryFn: () =>
      apiRequest<{
        day: string;
        daily_goal: string;
        gross_total: string;
        net_total: string;
        sale_count: number;
        operations: {
          operation_id: string;
          name: string;
          split_percent: string;
          sale_count: number;
          gross_amount: string;
          net_amount: string;
        }[];
        recent_sales: {
          id: string;
          operation_id: string;
          operation_name: string;
          transaction_id: string | null;
          customer_name: string | null;
          plan_name: string | null;
          gross_amount: string;
          net_amount: string;
          occurred_at: string;
        }[];
      }>("/api/analytics/smokepay"),
    retry: false,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
  const saveDailyGoal = useMutation({
    mutationFn: (daily_goal: string) =>
      apiRequest("/api/analytics/smokepay/daily-goal", {
        method: "PUT",
        body: { daily_goal },
      }),
    onSuccess: async () => {
      setDailyGoalDraft(null);
      await queryClient.invalidateQueries({
        queryKey: ["analytics", "smokepay"],
      });
    },
  });
  async function playSaleSound() {
    try {
      const AudioContextClass =
        window.AudioContext ??
        (window as typeof window & { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (!AudioContextClass) {
        throw new Error("Este navegador não oferece áudio Web Audio.");
      }
      const context = new AudioContextClass();
      await context.resume();
      const gain = context.createGain();
      gain.gain.setValueAtTime(0.0001, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.12, context.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.35);
      gain.connect(context.destination);
      for (const [offset, frequency] of [
        [0, 880],
        [0.11, 1320],
      ]) {
        const oscillator = context.createOscillator();
        oscillator.type = "sine";
        oscillator.frequency.value = frequency;
        oscillator.connect(gain);
        oscillator.start(context.currentTime + offset);
        oscillator.stop(context.currentTime + offset + 0.16);
      }
      window.setTimeout(() => void context.close(), 500);
      setSoundError(null);
    } catch (error) {
      console.warn("The sale notification sound could not be played.", error);
      setSoundError("O navegador bloqueou o som. Interaja com a página e ative-o novamente.");
    }
  }
  useEffect(() => {
    const sales = smokepayFinance.data?.recent_sales;
    if (!sales) return;
    const currentIds = new Set(sales.map((sale) => sale.id));
    const knownIds = seenSaleIds.current;
    if (
      soundEnabled &&
      knownIds !== null &&
      [...currentIds].some((saleId) => !knownIds.has(saleId))
    ) {
      void playSaleSound();
    }
    seenSaleIds.current = currentIds;
  }, [smokepayFinance.data?.recent_sales, soundEnabled]);
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
  const metricCount = (value: number | null | undefined) =>
    metrics ? formatCount(value) : "—";
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
    !metrics.insights_checked ||
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
      target: viewsUnavailable ? null : metrics?.views_count ?? null,
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
            ? "Consultando a Meta; número animado provisório"
            : metaSummary.error
              ? "A Meta não retornou os Insights; consulte as notificações"
              : "Consulte as notificações para verificar os Insights da Meta"
          : "Insights recebidos da Meta no período",
      icon: ChartNoAxesCombined,
      color: "text-[#71c8e8]",
    },
    {
      title: "Contas ativas",
      target: metrics?.active_accounts ?? null,
      loading: summary.isFetching && !summary.data,
      detail: "Com autorização válida",
      icon: UsersRound,
      color: "text-[#8295ff]",
    },
    {
      title: "Colaboradores ativos",
      target: metrics?.active_collaborators ?? null,
      loading: summary.isFetching && !summary.data,
      detail: "Membros ativos deste workspace",
      icon: UsersRound,
      color: "text-[#71c8e8]",
    },
    {
      title: "Seguidores",
      target: metrics?.followers_count ?? null,
      loading: summary.isFetching && !summary.data,
      detail: metrics?.profile_metrics_unavailable
        ? "Meta indisponível; mostrando último valor salvo"
        : "Atualizado diretamente pela Meta",
      icon: UsersRound,
      color: "text-[#aab7ff]",
    },
    {
      title: "Mídias nos perfis",
      target: metrics?.media_count ?? null,
      loading: summary.isFetching && !summary.data,
      detail: metrics?.profile_metrics_unavailable
        ? "Meta indisponível; mostrando último valor salvo"
        : "Atualizado diretamente pela Meta",
      icon: ChartNoAxesCombined,
      color: "text-[#b171ff]",
    },
    {
      title: "Posts no período",
      target: metrics?.published_posts ?? null,
      loading: summary.isFetching && !summary.data,
      detail: "Publicados pelo FlashPost",
      icon: CircleCheck,
      color: "text-[#76c8a0]",
    },
    {
      title: "Na fila",
      target: metrics?.queued_posts ?? null,
      loading: summary.isFetching && !summary.data,
      detail: "Aguardando processamento",
      icon: Clock3,
      color: "text-[#f2d48a]",
    },
    {
      title: "Falhas",
      target: metrics?.failed_posts ?? null,
      loading: summary.isFetching && !summary.data,
      detail: "Publicações que precisam de atenção",
      icon: AlertTriangle,
      color: "text-[#f16f82]",
    },
    {
      title: "Contas com erro",
      target: metrics ? accountsWithIssues : null,
      loading: summary.isFetching && !summary.data,
      detail: "Desconectadas ou com autorização expirada",
      icon: UserRoundX,
      color: "text-[#f16f82]",
    },
    {
      title: "Leads Sharkbot",
      target: metrics?.leads ?? null,
      loading: summary.isFetching && !summary.data,
      detail: "Recebidos no período",
      icon: UsersRound,
      color: "text-[#71c8e8]",
    },
    {
      title: "Pix gerados",
      target: metrics?.pix_generated ?? null,
      loading: summary.isFetching && !summary.data,
      detail: "Pagamentos iniciados no período",
      icon: Wallet,
      color: "text-[#f2d48a]",
    },
    {
      title: "Pix pagos",
      target: metrics?.pix_paid ?? null,
      loading: summary.isFetching && !summary.data,
      detail: "Pagamentos aprovados no período",
      icon: CircleCheck,
      color: "text-[#76c8a0]",
    },
    {
      title: "Conversão de Pix",
      target: metrics ? pixConversion : null,
      loading: summary.isFetching && !summary.data,
      formatValue: formatPercent,
      detail: "Pagos em relação aos gerados no período",
      icon: ChartNoAxesCombined,
      color: "text-[#b171ff]",
    },
    {
      title: "Valor faturado",
      target: metrics ? Number(metrics.pix_paid_amount) : null,
      loading: summary.isFetching && !summary.data,
      formatValue: formatMoney,
      detail: "Pix pagos no período, pelo horário de Brasília",
      icon: Wallet,
      color: "text-[#76c8a0]",
    },
  ];
  const salesFinance = smokepayFinance.data;
  const numericNetTotal = Number(salesFinance?.net_total ?? 0);
  const numericDailyGoal = Number(
    dailyGoalDraft ?? salesFinance?.daily_goal ?? 0,
  );
  const dailyGoalProgress =
    numericDailyGoal > 0
      ? Math.min(Math.round((numericNetTotal / numericDailyGoal) * 100), 100)
      : 0;

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

      {(summary.isFetching || metaSummary.isFetching) && (
        <p className="text-xs text-[#64748b]" role="status">
          {summary.isFetching
            ? "Atualizando indicadores do painel…"
            : "Atualizando métricas da Meta em segundo plano…"}
        </p>
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
      <section aria-label="Financeiro Smokepay" className="space-y-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-medium uppercase tracking-[0.14em] text-[#8295ff]">
              Smokepay · {salesFinance?.day ?? localDateInputValue()}
            </p>
            <h2 className="mt-1 text-xl font-semibold text-[#f5f7fb]">
              Vendas de hoje
            </h2>
            <p className="mt-1 text-xs text-[#94a3b8]">
              Atualização automática a cada 5 segundos.
            </p>
          </div>
          <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-[#cbd5e1]">
            <input
              checked={soundEnabled}
              onChange={(event) => {
                setSoundEnabled(event.target.checked);
                if (event.target.checked) void playSaleSound();
              }}
              type="checkbox"
            />
            <Volume2 size={14} />
            Som de nova venda
          </label>
        </header>
        {smokepayFinance.error ? (
          <article className="rounded-xl border border-[#63343b] bg-[#2b171b] p-4 text-sm text-[#f1a3ad]">
            Não foi possível atualizar as vendas da Smokepay. Verifique a conexão
            e tente novamente.
          </article>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-3">
              <article className="dashboard-card rounded-xl p-4">
                <p className="text-xs text-[#94a3b8]">Faturamento bruto</p>
                <p className="mt-2 text-2xl font-semibold text-[#f5f7fb]">
                  {formatMoney(Number(salesFinance?.gross_total ?? 0))}
                </p>
                <p className="mt-1 text-[11px] text-[#78839b]">
                  {salesFinance?.sale_count ?? 0} venda(s) aprovada(s) hoje
                </p>
              </article>
              <article className="dashboard-card rounded-xl p-4">
                <p className="text-xs text-[#94a3b8]">Faturamento líquido</p>
                <p className="mt-2 text-2xl font-semibold text-[#76c8a0]">
                  {formatMoney(numericNetTotal)}
                </p>
                <p className="mt-1 text-[11px] text-[#78839b]">
                  Seu valor líquido após os splits configurados
                </p>
              </article>
              <article className="dashboard-card rounded-xl p-4">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-[#94a3b8]">Meta líquida do dia</p>
                  <p className="text-xs font-semibold text-[#aab7ff]">
                    {dailyGoalProgress}%
                  </p>
                </div>
                <form
                  className="mt-2 flex gap-2"
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (numericDailyGoal >= 0) {
                      saveDailyGoal.mutate(numericDailyGoal.toFixed(2));
                    }
                  }}
                >
                  <input
                    aria-label="Meta líquida diária em reais"
                    className="collaborator-input min-w-0 flex-1"
                    min={0}
                    onChange={(event) => setDailyGoalDraft(event.target.value)}
                    placeholder="Defina uma meta"
                    step="0.01"
                    type="number"
                    value={
                      dailyGoalDraft ??
                      salesFinance?.daily_goal ??
                      ""
                    }
                  />
                  <button
                    className="rounded-lg border border-[#34446f] px-3 text-xs font-medium text-[#c3ccff] disabled:opacity-50"
                    disabled={saveDailyGoal.isPending || !salesFinance}
                    type="submit"
                  >
                    Salvar
                  </button>
                </form>
                <div
                  aria-label={`Meta diária atingida: ${dailyGoalProgress}%`}
                  className="mt-3 h-2 overflow-hidden rounded-full bg-[#202838]"
                  role="progressbar"
                  aria-valuemax={100}
                  aria-valuemin={0}
                  aria-valuenow={dailyGoalProgress}
                >
                  <div
                    className="h-full rounded-full bg-[#76c8a0] transition-[width]"
                    style={{ width: `${dailyGoalProgress}%` }}
                  />
                </div>
                {saveDailyGoal.error && (
                  <p className="mt-2 text-[11px] text-[#f1a3ad]">
                    Não foi possível salvar a meta diária.
                  </p>
                )}
              </article>
            </div>

            <div className="grid gap-4 xl:grid-cols-2">
              <article className="dashboard-card rounded-xl p-4">
                <h3 className="text-sm font-semibold text-[#eef1f8]">
                  Líquido por operação
                </h3>
                {salesFinance?.operations.length ? (
                  <ul className="mt-3 divide-y divide-[#202838]">
                    {salesFinance.operations.map((operation) => (
                      <li
                        className="flex flex-wrap items-center justify-between gap-2 py-3"
                        key={operation.operation_id}
                      >
                        <div>
                          <p className="text-sm text-[#e6eaf2]">
                            {operation.name}
                          </p>
                          <p className="mt-0.5 text-[11px] text-[#78839b]">
                            Split {operation.split_percent}% · {operation.sale_count} venda(s) · Bruto{" "}
                            {formatMoney(Number(operation.gross_amount))}
                          </p>
                        </div>
                        <strong className="text-sm text-[#76c8a0]">
                          {formatMoney(Number(operation.net_amount))}
                        </strong>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm text-[#94a3b8]">
                    Cadastre uma operação em Integrações para receber vendas.
                  </p>
                )}
              </article>
              <article aria-live="polite" className="dashboard-card rounded-xl p-4">
                <div className="flex items-center gap-2">
                  <BellRing className="text-[#aab7ff]" size={15} />
                  <h3 className="text-sm font-semibold text-[#eef1f8]">
                    Vendas ao vivo
                  </h3>
                </div>
                {salesFinance?.recent_sales.length ? (
                  <ul className="mt-3 divide-y divide-[#202838]">
                    {salesFinance.recent_sales.slice(0, 10).map((sale) => (
                      <li
                        className="flex items-center justify-between gap-3 py-2.5"
                        key={sale.id}
                      >
                        <div className="min-w-0">
                          <p className="truncate text-xs font-medium text-[#e6eaf2]">
                            {sale.customer_name || sale.plan_name || "Venda aprovada"}
                          </p>
                          <p className="mt-0.5 truncate text-[10px] text-[#78839b]">
                            {sale.operation_name} ·{" "}
                            {new Intl.DateTimeFormat("pt-BR", {
                              hour: "2-digit",
                              minute: "2-digit",
                              timeZone: "America/Sao_Paulo",
                            }).format(new Date(sale.occurred_at))}
                          </p>
                        </div>
                        <span className="shrink-0 text-right">
                          <strong className="block text-xs text-[#76c8a0]">
                            +{formatMoney(Number(sale.net_amount))}
                          </strong>
                          <span className="text-[10px] text-[#78839b]">
                            Bruto {formatMoney(Number(sale.gross_amount))}
                          </span>
                        </span>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm text-[#94a3b8]">
                    Aguardando vendas aprovadas.
                  </p>
                )}
                {soundError && (
                  <p className="mt-2 text-[11px] text-[#f2d48a]">{soundError}</p>
                )}
              </article>
            </div>
          </>
        )}
      </section>
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
            {metricCount(metrics?.active_accounts)}
            <span className="ml-2 text-sm font-normal tracking-normal text-[#94a3b8]">
              ativas
            </span>
          </p>
          <ul className="mt-3 space-y-2 border-t border-[#202838] pt-3 text-sm">
            <li className="flex items-center justify-between gap-3">
              <span className="text-[#f1a3ad]">Com erro</span>
              <span className="font-medium text-[#e6eaf2]">
                {metricCount(metrics?.errored_accounts)}
              </span>
            </li>
            <li className="flex items-center justify-between gap-3">
              <span className="text-[#f2d48a]">Desconectadas</span>
              <span className="font-medium text-[#e6eaf2]">
                {metricCount(metrics?.disconnected_accounts)}
              </span>
            </li>
            <li className="flex items-center justify-between gap-3">
              <span className="text-[#f2d48a]">Autorização expirada</span>
              <span className="font-medium text-[#e6eaf2]">
                {metricCount(metrics?.expired_accounts)}
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
