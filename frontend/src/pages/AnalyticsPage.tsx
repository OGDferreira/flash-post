import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  CircleCheck,
  Clock3,
  Eye,
  RefreshCw,
  UsersRound,
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
import { InstagramAvatar } from "@/components/InstagramAvatar";
import {
  InstagramAccountSelector,
  type InstagramAccountOption,
} from "@/components/InstagramAccountSelector";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { BotPerformancePanel } from "@/features/analytics/BotPerformancePanel";
import { SyncStatusBar, useWorkspaceSync } from "@/features/analytics/useWorkspaceSync";
import { DailyViewsPanel } from "@/features/analytics/DailyViewsPanel";
import { SharkSalesPanel } from "@/features/sharkbot/SharkSalesPanel";
import { EngagementRankingPanel } from "@/features/analytics/EngagementRankingPanel";
import {
  PeriodFilter,
  formatDateTime,
  isPeriodReady,
  periodParams,
  todayInput,
  type MetricsPeriod,
} from "@/features/analytics/period";
import { TopVideosPanel } from "@/features/analytics/TopVideosPanel";
import { ApiError, apiRequest } from "@/services/api";

type Account = InstagramAccountOption & {
  status: "connected" | "disconnected" | "error";
  token_expires_at: string;
  insights_synced_at?: string | null;
  insights_sync_error?: string | null;
};

type MetricsTab = "account" | "daily" | "videos" | "ranking" | "bots" | "sales";

const tabs: { value: MetricsTab; label: string }[] = [
  { value: "account", label: "Por conta" },
  { value: "daily", label: "Views por dia" },
  { value: "videos", label: "Vídeos em alta" },
  { value: "ranking", label: "Ranking de engajamento" },
  { value: "bots", label: "Bots e fluxos" },
  { value: "sales", label: "Vendas" },
];

function formatCount(value: number | null | undefined): string {
  return value === null || value === undefined
    ? "—"
    : new Intl.NumberFormat("pt-BR").format(value);
}

function insightHelper(error: string | undefined): string {
  if (!error) return "Insights da Meta no período selecionado";
  if (error.includes("instagram_business_manage_insights")) {
    return "Permissão necessária: instagram_business_manage_insights";
  }
  if (error.includes("não podem ser somados")) {
    return "A Meta não enviou o total do período; dias não são somados";
  }
  if (error.includes("vídeos")) return error;
  if (error.includes("descontinuou esta métrica")) {
    return "Métrica descontinuada pela Meta; consulte Visualizações";
  }
  return "Métrica indisponível para esta conta ou período";
}

export function AnalyticsPage() {
  const [selectedAccountIds, setSelectedAccountIds] = useState<string[]>([]);
  const [tab, setTab] = useState<MetricsTab>("account");
  const sync = useWorkspaceSync();
  const [period, setPeriod] = useState<MetricsPeriod>(() => ({
    period: "7d",
    start: todayInput(),
    end: todayInput(),
  }));
  const queryClient = useQueryClient();
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<{ accounts: Account[] }>("/api/instagram/accounts"),
    refetchInterval: 120_000,
    retry: false,
  });
  const activeAccounts = useMemo(
    () =>
      (accounts.data?.accounts ?? []).filter(
        (account) =>
          account.status === "connected" && Date.parse(account.token_expires_at) > Date.now(),
      ),
    [accounts.data?.accounts],
  );
  const selectedAccountId = selectedAccountIds[0];

  useEffect(() => {
    if (selectedAccountId && activeAccounts.some(({ id }) => id === selectedAccountId)) return;
    const nextId = activeAccounts[0]?.id;
    if (nextId !== selectedAccountId) setSelectedAccountIds(nextId ? [nextId] : []);
  }, [activeAccounts, selectedAccountId]);
  const summary = useQuery({
    queryKey: ["analytics", "account", selectedAccountId, periodParams(period)],
    queryFn: () => {
      const query = new URLSearchParams(periodParams(period));
      query.append("account_ids", selectedAccountId);
      query.set("include_meta_insights", "true");
      return apiRequest<InstagramAnalyticsSummary>(
        `/api/analytics/summary?${query.toString()}`,
      );
    },
    enabled: Boolean(selectedAccountId) && isPeriodReady(period),
    retry: false,
    staleTime: 60_000,
  });
  const selectedAccount = activeAccounts.find(({ id }) => id === selectedAccountId);
  const syncNow = useMutation({
    mutationFn: (accountId: string) =>
      apiRequest(`/api/analytics/accounts/${accountId}/sync`, { method: "POST" }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["instagram", "accounts"] });
      void queryClient.invalidateQueries({ queryKey: ["analytics"] });
    },
  });
  const accountMetrics = summary.data?.accounts[0];
  const appMetrics = [
    {
      title: "Seguidores",
      value: formatCount(accountMetrics?.follower_count),
      helper: accountMetrics?.profile_metrics_error ?? "Informado pela Meta",
      icon: UsersRound,
    },
    {
      title: "Seguindo",
      value: formatCount(accountMetrics?.follows_count),
      helper: accountMetrics?.profile_metrics_error ?? "Informado pela Meta",
      icon: UsersRound,
    },
    {
      title: "Posts no perfil",
      value: formatCount(accountMetrics?.media_count),
      helper: accountMetrics?.profile_metrics_error ?? "Informado pela Meta",
      icon: BarChart3,
    },
    {
      title: "Publicados pelo Flash",
      value: formatCount(accountMetrics?.published_posts),
      helper: "Publicações concluídas pela ferramenta",
      icon: CircleCheck,
    },
    {
      title: "Na fila",
      value: formatCount(accountMetrics?.queued_posts),
      helper: "Aguardando envio ou processamento",
      icon: Clock3,
    },
    {
      title: "Falhas",
      value: formatCount(accountMetrics?.failed_posts),
      helper: "Publicações que precisam de atenção",
      icon: AlertTriangle,
    },
    {
      title: "Leads Sharkbot",
      value: formatCount(accountMetrics?.leads),
      helper: "Recebidos no período",
      icon: UsersRound,
    },
    {
      title: "Pix gerados",
      value: formatCount(accountMetrics?.pix_generated),
      helper: "Iniciados no período",
      icon: BarChart3,
    },
    {
      title: "Pix pagos",
      value: formatCount(accountMetrics?.pix_paid),
      helper: "Aprovados no período",
      icon: CircleCheck,
    },
  ];
  const metaInsightMetrics = [
    { key: "period_views", title: "Visualizações no período", icon: Eye },
    { key: "views", title: "Visualizações acumuladas dos vídeos do período", icon: Eye },
    { key: "reach", title: "Alcance", icon: Eye },
    { key: "impressions", title: "Impressões", icon: Eye },
    { key: "accounts_engaged", title: "Contas engajadas", icon: UsersRound },
    { key: "total_interactions", title: "Interações totais", icon: BarChart3 },
    { key: "likes", title: "Curtidas", icon: CircleCheck },
    { key: "comments", title: "Comentários", icon: BarChart3 },
    { key: "shares", title: "Compartilhamentos", icon: BarChart3 },
    { key: "saves", title: "Salvamentos", icon: BarChart3 },
    { key: "profile_views", title: "Visitas ao perfil", icon: Eye },
    { key: "website_clicks", title: "Cliques no site", icon: BarChart3 },
    { key: "profile_links_taps", title: "Toques em links do perfil", icon: BarChart3 },
    { key: "replies", title: "Respostas", icon: BarChart3 },
    { key: "reposts", title: "Reposts", icon: BarChart3 },
  ].map(({ key, title, icon }) => ({
    title,
    value: formatCount(accountMetrics?.insights[key] ?? null),
    helper: insightHelper(
      accountMetrics?.insights_metric_errors[key] ??
      accountMetrics?.insights_metric_errors.all ??
      accountMetrics?.insights_error ?? undefined,
    ),
    icon,
  }));
  const metrics = [...appMetrics, ...metaInsightMetrics];

  if (accounts.isLoading) return <LoadingState label="Carregando contas para Analytics" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as contas deste workspace." />;
  }

  return (
    <div className="tab-host mx-auto max-w-[1440px] space-y-4">
      <header className="space-y-4">
        <div>
          <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">
            Analytics
          </h2>
        </div>
        <nav aria-label="Seções de métricas" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
          {tabs.map((item) => (
            <button
              aria-current={tab === item.value ? "page" : undefined}
              className={`shrink-0 rounded-full px-4 py-2 text-sm transition ${
                tab === item.value
                  ? "bg-brand/20 font-medium text-accent shadow-[inset_0_0_0_1px_rgba(130,149,255,0.45)]"
                  : "text-muted hover:bg-white/5 hover:text-fg"
              }`}
              key={item.value}
              onClick={() => setTab(item.value)}
              type="button"
            >
              {item.label}
            </button>
          ))}
        </nav>
        <PeriodFilter onChange={setPeriod} value={period} />
      </header>
      <SyncStatusBar onRefresh={() => sync.start.mutate(true)} starting={sync.start.isPending} status={sync.status.data} />
      {tab === "daily" && <DailyViewsPanel period={period} />}
      {tab === "sales" && <SharkSalesPanel period={period} />}
      {tab === "videos" && <TopVideosPanel period={period} />}
      {tab === "ranking" && (
        <EngagementRankingPanel
          onSelectAccount={(accountId) => {
            setSelectedAccountIds([accountId]);
            setTab("account");
          }}
          period={period}
        />
      )}
      {tab === "bots" && <BotPerformancePanel period={period} />}
      {tab === "account" && (
      <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)] lg:items-start">
        <InstagramAccountSelector
          accounts={activeAccounts}
          selectedAccountIds={selectedAccountIds}
          onSelectionChange={setSelectedAccountIds}
          selectionMode="single"
          label="Conta Instagram"
        />
        <div className="min-w-0 space-y-4">
          {!activeAccounts.length ? (
            <section className="rounded-xl border border-dashed border-line p-5 text-center text-sm text-muted">
              Conecte uma conta ativa no Hub de Contas para consultar o Analytics.
            </section>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <InstagramAvatar
                  className="size-10 rounded-full object-cover"
                  src={accountMetrics?.profile_picture_url ?? null}
                  username={
                    accountMetrics?.username ??
                    activeAccounts.find(({ id }) => id === selectedAccountId)?.username ??
                    "Instagram"
                  }
                />
                <div className="min-w-0 flex-1">
                  <p className="text-xs uppercase tracking-[0.13em] text-accent">Conta atual</p>
                  <h3 className="font-medium text-fg">
                    @{accountMetrics?.username ?? selectedAccount?.username}
                  </h3>
                  <p className="text-[11px] text-muted">
                    Publicações sincronizadas: {formatDateTime(selectedAccount?.insights_synced_at)}
                    {selectedAccount?.insights_sync_error ? ` · ${selectedAccount.insights_sync_error}` : ""}
                  </p>
                </div>
                <button
                  className="btn-secondary !min-h-9 shrink-0 !px-3 text-xs"
                  disabled={!selectedAccountId || syncNow.isPending}
                  onClick={() => syncNow.mutate(selectedAccountId)}
                  type="button"
                >
                  <RefreshCw className={syncNow.isPending ? "animate-spin" : ""} size={14} />
                  Sincronizar
                </button>
              </div>
              {syncNow.error && (
                <ErrorState
                  message={
                    syncNow.error instanceof ApiError
                      ? syncNow.error.message
                      : "Não foi possível sincronizar agora."
                  }
                />
              )}
              {summary.error && (
                <ErrorState message="Não foi possível carregar as métricas desta conta." />
              )}
              {summary.isLoading && <LoadingState label="Carregando dados da conta" />}
              <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                {metrics.map(({ title, value, helper, icon: Icon }) => (
                  <article
                    className="rounded-xl border border-line-soft bg-surface p-4"
                    key={title}
                  >
                    <div className="flex items-center gap-2 text-xs text-muted">
                      <Icon className="text-accent" size={15} />
                      {title}
                    </div>
                    <p className="mt-3 text-xl font-semibold text-fg">{value}</p>
                    <p className="mt-1 text-xs leading-5 text-muted">{helper}</p>
                  </article>
                ))}
              </div>
              <section className="rounded-xl border border-line-soft bg-surface p-4 sm:p-4">
                <h3 className="text-sm font-medium text-fg">
                  Publicações feitas pelo Flash no período
                </h3>
                <div className="mt-4 h-[260px]">
                  <ResponsiveContainer height="100%" width="100%">
                    <AreaChart data={summary.data?.daily_publications ?? []}>
                      <defs>
                        <linearGradient id="accountPublishedFill" x1="0" x2="0" y1="0" y2="1">
                          <stop offset="0%" stopColor="#1e9cfd" stopOpacity={0.38} />
                          <stop offset="95%" stopColor="#1e9cfd" stopOpacity={0.02} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid stroke="#202838" strokeDasharray="3 3" vertical={false} />
                      <XAxis
                        axisLine={false}
                        dataKey="day"
                        tick={{ fill: "#64748b", fontSize: 11 }}
                        tickLine={false}
                        tickFormatter={(day: string) =>
                          new Date(`${day}T00:00:00Z`).toLocaleDateString("pt-BR", {
                            day: "2-digit",
                            month: "2-digit",
                            timeZone: "UTC",
                          })
                        }
                      />
                      <YAxis
                        allowDecimals={false}
                        axisLine={false}
                        tick={{ fill: "#64748b", fontSize: 11 }}
                        tickLine={false}
                      />
                      <Tooltip
                        contentStyle={{
                          background: "#10141b",
                          border: "1px solid #27334a",
                          borderRadius: 10,
                          color: "#f5f7fb",
                        }}
                      />
                      <Area
                        dataKey="published_posts"
                        fill="url(#accountPublishedFill)"
                        name="Publicações"
                        stroke="#6684ff"
                        strokeWidth={2.5}
                        type="monotone"
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </section>
              {selectedAccountId && <TopVideosPanel accountId={selectedAccountId} compact period={period} />}
              <p className="rounded-lg border border-line bg-surface-raised px-4 py-3 text-xs leading-5 text-muted">
                Os cards acima são consultados na Meta no momento da abertura para o período
                selecionado (Insights podem atrasar até 48 h). A lista de publicações usa os dados
                sincronizados automaticamente a cada 3 horas. Um “—” indica que a Meta não
                disponibilizou aquela métrica; o motivo aparece no card.
              </p>
            </>
          )}
        </div>
      </div>
      )}
    </div>
  );
}
