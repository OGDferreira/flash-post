import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  BarChart3,
  CircleCheck,
  Clock3,
  CreditCard,
  UsersRound,
} from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { InstagramAvatar } from "@/components/InstagramAvatar";
import type {
  InstagramAnalyticsAccount,
  InstagramAnalyticsSummary,
} from "@/features/analytics/types";
import { apiRequest } from "@/services/api";

type InstagramAccount = {
  id: string;
  username: string;
  profile_picture_url: string | null;
  status: "connected" | "disconnected" | "error";
  token_expires_at: string;
};

type InstagramAccountsResponse = {
  accounts: InstagramAccount[];
};

function formatCount(value: number | null | undefined): string {
  return value == null ? "—" : new Intl.NumberFormat("pt-BR").format(value);
}

function formatMoney(value: string | number | null | undefined): string {
  if (value == null) return "R$ —";
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value));
}

function isHealthy(account: InstagramAccount): boolean {
  return (
    account.status === "connected" &&
    Date.parse(account.token_expires_at) > Date.now()
  );
}

function FeedMetric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: typeof UsersRound;
}) {
  return (
    <div className="rounded-lg border border-[#202838] bg-[#090b0f] p-3">
      <div className="flex items-center gap-2 text-xs text-[#94a3b8]">
        <Icon className="text-[#8295ff]" size={14} />
        {label}
      </div>
      <p className="mt-2 text-lg font-semibold text-[#f5f7fb]">{value}</p>
    </div>
  );
}

export function FeedPage() {
  const accounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<InstagramAccountsResponse>("/api/instagram/accounts"),
    refetchInterval: 60_000,
    retry: false,
  });
  const accountIds = useMemo(
    () => (accounts.data?.accounts ?? []).map(({ id }) => id).sort(),
    [accounts.data?.accounts],
  );
  const summary = useQuery({
    queryKey: ["analytics", "feed", "30d", accountIds],
    queryFn: () => {
      const query = new URLSearchParams({ period: "30d" });
      accountIds.forEach((id) => query.append("account_ids", id));
      return apiRequest<InstagramAnalyticsSummary>(`/api/analytics/summary?${query}`);
    },
    enabled: !accounts.isLoading && !accounts.error,
    retry: false,
  });
  const metricsByAccount = useMemo(
    () =>
      new Map<string, InstagramAnalyticsAccount>(
        (summary.data?.accounts ?? []).map((item) => [item.account_id, item]),
      ),
    [summary.data?.accounts],
  );

  if (accounts.isLoading) return <LoadingState label="Carregando contas do Feed" />;
  if (accounts.error || !accounts.data) {
    return <ErrorState message="Não foi possível carregar as contas deste workspace." />;
  }

  return (
    <div className="mx-auto max-w-[1280px] space-y-6">
      <header>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#7186ff]">
          Desempenho por perfil
        </p>
        <h1 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-[#f5f7fb] sm:text-3xl">
          Feed
        </h1>
        <p className="mt-2 max-w-3xl text-sm leading-6 text-[#94a3b8]">
          Veja as métricas de cada conta separadamente. Publicações e eventos Sharkbot mostram os
          últimos 30 dias; seguidores e mídias são os retratos recebidos na última autorização Meta.
        </p>
      </header>

      {summary.error && (
        <ErrorState message="Não foi possível carregar as métricas das contas." />
      )}
      {summary.isLoading && <LoadingState label="Carregando métricas individuais" />}

      {accounts.data.accounts.length === 0 ? (
        <EmptyState message="Conecte uma conta Instagram para começar a consultar o Feed." />
      ) : (
        <section aria-label="Métricas por conta Instagram" className="grid gap-4 xl:grid-cols-2">
          {accounts.data.accounts.map((account) => {
            const metrics = metricsByAccount.get(account.id);
            const healthy = isHealthy(account);
            return (
              <article
                className="dashboard-card space-y-4 rounded-xl p-4 sm:p-5"
                key={account.id}
              >
                <header className="flex items-center justify-between gap-3">
                  <div className="flex min-w-0 items-center gap-3">
                    <InstagramAvatar
                      className="size-12 rounded-full border border-[#27334a] object-cover"
                      src={account.profile_picture_url}
                      username={account.username}
                    />
                    <div className="min-w-0">
                      <h2 className="truncate font-semibold text-[#f5f7fb]">
                        @{account.username}
                      </h2>
                      <p
                        className={`mt-1 text-xs ${
                          healthy ? "text-[#9de0c0]" : "text-[#f1a3ad]"
                        }`}
                      >
                        {healthy ? "Conectada e saudável" : "Conta com erro ou autorização expirada"}
                      </p>
                    </div>
                  </div>
                  <span className="shrink-0 rounded-full bg-[#17202b] px-2.5 py-1 text-xs text-[#aeb9ce]">
                    Últimos 30 dias
                  </span>
                </header>

                {metrics ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <FeedMetric
                      icon={UsersRound}
                      label="Seguidores"
                      value={formatCount(metrics.follower_count)}
                    />
                    <FeedMetric
                      icon={BarChart3}
                      label="Mídias no perfil"
                      value={formatCount(metrics.media_count)}
                    />
                    <FeedMetric
                      icon={CircleCheck}
                      label="Publicações concluídas"
                      value={formatCount(metrics.published_posts)}
                    />
                    <FeedMetric
                      icon={Clock3}
                      label="Publicações na fila"
                      value={formatCount(metrics.queued_posts)}
                    />
                    <FeedMetric
                      icon={AlertTriangle}
                      label="Publicações com falha"
                      value={formatCount(metrics.failed_posts)}
                    />
                    <FeedMetric
                      icon={UsersRound}
                      label="Leads Sharkbot"
                      value={formatCount(metrics.leads)}
                    />
                    <FeedMetric
                      icon={CreditCard}
                      label="Pix gerados / pagos"
                      value={`${formatCount(metrics.pix_generated)} / ${formatCount(metrics.pix_paid)}`}
                    />
                    <FeedMetric
                      icon={CreditCard}
                      label="Valor de Pix pagos"
                      value={formatMoney(metrics.pix_paid_amount)}
                    />
                  </div>
                ) : (
                  <p className="rounded-lg border border-dashed border-[#27334a] p-4 text-sm text-[#94a3b8]">
                    {summary.isLoading
                      ? "Carregando os dados deste perfil..."
                      : "Ainda não há métricas disponíveis para esta conta."}
                  </p>
                )}
              </article>
            );
          })}
        </section>
      )}
    </div>
  );
}
