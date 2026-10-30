import { useState } from "react";
import { Link } from "react-router-dom";
import { CircleDollarSign, Plus, Receipt, Trophy, UserRoundCheck, UsersRound, type LucideIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { ConnectAppsPanel } from "@/components/ConnectAccountModal";
import { GreetingClock } from "@/components/GreetingClock";
import { ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { PeriodFilter, isPeriodReady, periodParams, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { useAuth } from "@/features/auth/AuthProvider";
import { usePartnerMe, brl } from "@/features/partners/api";
import { SharedLoopsSection } from "@/features/partners/SharedTemplates";
import { ViewsRankingList } from "@/features/rankings/RankingLists";
import { apiRequest } from "@/services/api";
import type { InstagramLoopsResponse } from "@/pages/loops/loopShared";

function Metric({ label, value, icon: Icon, tone = "text-fg", hint }: { label: string; value: string; icon: LucideIcon; tone?: string; hint?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line-soft bg-surface-inset px-3 py-3">
      <dt className="flex items-center gap-2 text-xs text-muted">
        <Icon aria-hidden="true" size={15} />
        {label}
      </dt>
      <dd className={`dashboard-metric-value mt-2 truncate text-2xl font-semibold ${tone}`} title={value}>{value}</dd>
      {hint && <p className="mt-1 truncate text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

/** Flash panel of a sócio (partner): their accounts, revenue and the views ranking. */
export function PartnerDashboardPage() {
  const { user } = useAuth();
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "today", start: todayInput(), end: todayInput() });
  const [connecting, setConnecting] = useState(false);
  const [accountsView, setAccountsView] = useState<"connected" | "disconnected">("connected");
  const params = periodParams(period);
  const partner = usePartnerMe(params, isPeriodReady(period));
  const permissions = partner.data?.permissions;
  const canViewAccounts = !permissions || permissions.full_panel || permissions.post.accounts;
  const sharedLoops = useQuery({
    queryKey: ["loops"],
    queryFn: () => apiRequest<InstagramLoopsResponse>("/api/loops?include_accounts=false"),
    enabled: partner.data?.role === "partner" && canViewAccounts,
    refetchInterval: 120_000,
    retry: false,
  });

  // Account counts are the current state (connected now / disconnected now), not a period.
  const summary = useQuery({
    queryKey: ["analytics", "summary", "fast", "today", null, null],
    queryFn: () => apiRequest<InstagramAnalyticsSummary>("/api/analytics/summary?period=today"),
    retry: false,
    staleTime: 60_000,
  });

  if (summary.isLoading && !summary.data) return <LoadingState label="Carregando seu painel" />;
  if (summary.error) {
    return <ErrorState message="Não foi possível carregar suas contas." onRetry={() => void summary.refetch()} />;
  }

  const metrics = summary.data;
  const disconnected = metrics ? metrics.disconnected_accounts + metrics.errored_accounts + metrics.expired_accounts : 0;
  const totals = partner.data?.totals;
  const shownAccounts = (metrics?.accounts ?? []).filter(({ status }) =>
    accountsView === "connected" ? status === "connected" : status !== "connected",
  );
  const canViewRanking = !permissions || permissions.full_panel || permissions.post.ranking;

  return (
    <div className="mx-auto max-w-[1320px] space-y-4">
      <GreetingClock nickname={user?.nickname} />

      {canViewAccounts && (
        <section aria-labelledby="partner-accounts-title" className="dashboard-card space-y-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-base font-semibold text-fg" id="partner-accounts-title">
              <UserRoundCheck aria-hidden="true" className="text-accent" size={18} /> Contas Conectadas
            </h2>
            <button className="btn-primary" onClick={() => setConnecting(true)} type="button">
              <Plus size={16} /> Conectar nova conta
            </button>
          </div>
          <div aria-label="Exibir contas" className="inline-flex gap-1 rounded-full bg-well p-1" role="tablist">
            {([
              ["connected", "Conectadas", metrics?.active_accounts ?? 0],
              ["disconnected", "Desconectadas", disconnected],
            ] as const).map(([value, label, total]) => (
              <button
                aria-selected={accountsView === value}
                className={`min-h-8 rounded-full px-4 text-xs font-medium ${accountsView === value ? "bg-brand text-white" : "text-muted"}`}
                key={value}
                onClick={() => setAccountsView(value)}
                role="tab"
                type="button"
              >
                {label} ({total})
              </button>
            ))}
          </div>
          {shownAccounts.length ? (
            <ul className="flex flex-wrap gap-2">
              {shownAccounts.slice(0, 24).map((account) => (
                <li
                  className={`rounded-full border border-line-soft px-3 py-1 text-xs ${accountsView === "connected" ? "text-fg" : "text-danger"}`}
                  key={account.account_id}
                >
                  @{account.username}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-xs text-muted">
              {accountsView === "connected" ? "Nenhuma conta conectada." : "Nenhuma conta desconectada."}
            </p>
          )}
          <Link className="text-xs font-medium text-accent hover:underline" to="/feature/accounts">Ver e gerenciar contas →</Link>
        </section>
      )}

      {partner.data?.role === "partner" && canViewAccounts && (
        <div className="space-y-3">
          {sharedLoops.isLoading && <LoadingState label="Carregando loops compartilhados" />}
          {sharedLoops.error && (
            <ErrorState
              message="Não foi possível carregar os loops compartilhados."
              onRetry={() => void sharedLoops.refetch()}
            />
          )}
          {sharedLoops.data && <SharedLoopsSection loops={sharedLoops.data.loops} />}
        </div>
      )}

      <section aria-labelledby="partner-revenue-title" className="dashboard-card space-y-4 p-4 sm:p-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="flex items-center gap-2 text-base font-semibold text-fg" id="partner-revenue-title">
            <CircleDollarSign aria-hidden="true" className="text-accent" size={18} /> Faturamento
          </h2>
          <PeriodFilter onChange={setPeriod} value={period} />
        </div>
        {partner.error ? (
          <ErrorState message="Não foi possível carregar o faturamento." onRetry={() => void partner.refetch()} />
        ) : (
          <dl className="grid grid-cols-2 gap-2 lg:grid-cols-3">
            <Metric icon={UsersRound} label="Contas Ativas" value={String(metrics?.active_accounts ?? 0)} />
            <Metric icon={Receipt} label="Vendas" value={totals ? String(totals.sales) : "—"} />
            <Metric icon={CircleDollarSign} label="Faturamento" value={totals ? brl(totals.gross) : "—"} />
          </dl>
        )}
      </section>

      {canViewRanking && (
        <section aria-labelledby="partner-ranking-title" className="space-y-2">
          <h2 className="flex items-center gap-2 px-1 text-base font-semibold text-fg" id="partner-ranking-title">
            <Trophy aria-hidden="true" className="text-accent" size={18} /> Ranking de visualizações
          </h2>
          <div className="dashboard-card p-4 sm:p-5">
            <ViewsRankingList limit={10} period={period} />
          </div>
        </section>
      )}

      <Modal onClose={() => setConnecting(false)} open={connecting} title="Conectar nova conta">
        <ConnectAppsPanel onClose={() => setConnecting(false)} returnTo="/dashboard" />
      </Modal>
    </div>
  );
}
