import { useState } from "react";
import { Link } from "react-router-dom";
import { CircleDollarSign, Plus, Receipt, Trophy, UserRoundCheck, UserRoundX, Wallet as WalletIcon, type LucideIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { ConnectAppsPanel } from "@/components/ConnectAccountModal";
import { GreetingClock } from "@/components/GreetingClock";
import { ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { TopVideosPanel } from "@/features/analytics/TopVideosPanel";
import { PeriodFilter, isPeriodReady, periodParams, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { useAuth } from "@/features/auth/AuthProvider";
import { usePartnerMe, brl } from "@/features/partners/api";
import { useWallet } from "@/features/wallet/api";
import { apiRequest } from "@/services/api";

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

/** Flash panel of a sócio (partner): only their accounts, revenue and the posts ranking. */
export function PartnerDashboardPage() {
  const { user } = useAuth();
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "today", start: todayInput(), end: todayInput() });
  const [connecting, setConnecting] = useState(false);
  const params = periodParams(period);
  const partner = usePartnerMe(params, isPeriodReady(period));
  const wallet = useWallet();

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

  const permissions = partner.data?.permissions;
  const canViewAccounts = !permissions || permissions.full_panel || permissions.post.accounts;
  const canViewWallet = !permissions || permissions.full_panel || permissions.bot.wallet;
  const canViewRanking = !permissions || permissions.full_panel || permissions.post.ranking;

  return (
    <div className="mx-auto max-w-[1320px] space-y-4">
      <GreetingClock nickname={user?.nickname} />

      {canViewAccounts && (
        <section aria-labelledby="partner-accounts-title" className="dashboard-card space-y-4 p-4 sm:p-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="flex items-center gap-2 text-base font-semibold text-fg" id="partner-accounts-title">
              <UserRoundCheck aria-hidden="true" className="text-accent" size={18} /> Contas
            </h2>
            <button className="btn-primary" onClick={() => setConnecting(true)} type="button">
              <Plus size={16} /> Conectar nova conta
            </button>
          </div>
          <dl className="grid grid-cols-2 gap-2">
            <Metric icon={UserRoundCheck} label="Conectadas" tone="text-success" value={String(metrics?.active_accounts ?? 0)} />
            <Metric icon={UserRoundX} label="Desconectadas" tone={disconnected ? "text-danger" : "text-fg"} value={String(disconnected)} />
          </dl>
          <Link className="text-xs font-medium text-accent hover:underline" to="/feature/accounts">Ver e gerenciar contas →</Link>
        </section>
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
          <dl className="grid grid-cols-2 gap-2 lg:grid-cols-4">
            <Metric icon={CircleDollarSign} label="Faturamento bruto" value={totals ? brl(totals.gross) : "—"} hint={partner.data?.period_label} />
            <Metric icon={Receipt} label="Vendas pagas" value={totals ? String(totals.sales) : "—"} />
            <Metric icon={CircleDollarSign} label="Líquido (após taxas e comissão)" tone="text-success" value={totals ? brl(totals.net) : "—"} />
            {canViewWallet && (
              <Metric
                icon={WalletIcon}
                label="Disponível na carteira"
                value={wallet.data ? brl(wallet.data.available) : "—"}
                hint={wallet.data ? `Processando ${brl(wallet.data.pending)} · sacado ${brl(wallet.data.withdrawn)}` : undefined}
              />
            )}
          </dl>
        )}
        {canViewWallet && <Link className="text-xs font-medium text-accent hover:underline" to="/carteira">Abrir carteira e sacar →</Link>}
      </section>

      {canViewRanking && (
        <section aria-labelledby="partner-ranking-title" className="space-y-2">
          <h2 className="flex items-center gap-2 px-1 text-base font-semibold text-fg" id="partner-ranking-title">
            <Trophy aria-hidden="true" className="text-accent" size={18} /> Ranking de posts do Flash
          </h2>
          <TopVideosPanel compact period={period} />
        </section>
      )}

      <Modal onClose={() => setConnecting(false)} open={connecting} title="Conectar nova conta">
        <ConnectAppsPanel onClose={() => setConnecting(false)} returnTo="/dashboard" />
      </Modal>
    </div>
  );
}
