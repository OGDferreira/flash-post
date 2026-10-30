import { useQuery } from "@tanstack/react-query";
import { CircleDollarSign, Eye, type LucideIcon } from "lucide-react";

import { Avatar } from "@/components/Avatar";
import { ErrorState, LoadingState } from "@/components/PageState";
import { isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";

type RankedUser = {
  position: number;
  user_id: string;
  full_name: string;
  nickname: string;
  avatar_url: string | null;
};
export type ViewsRanking = { period_label: string; ranking: (RankedUser & { views: number })[] };
export type RevenueRanking = { period_label: string; ranking: (RankedUser & { revenue: number; sales: number })[] };

const count = (value: number) => new Intl.NumberFormat("pt-BR").format(value);
const brl = (value: number) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);

function useRanking<T>(kind: "views" | "revenue", period: MetricsPeriod, limit: number, enabled = true) {
  const params = new URLSearchParams({ ...periodParams(period), limit: String(limit) });
  return useQuery({
    queryKey: ["rankings", kind, params.toString()],
    queryFn: () => apiRequest<T>(`/api/rankings/${kind}?${params}`),
    enabled: enabled && isPeriodReady(period),
    retry: false,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
}

export const useViewsRanking = (period: MetricsPeriod, limit = 20) => useRanking<ViewsRanking>("views", period, limit);
export const useRevenueRanking = (period: MetricsPeriod, limit = 20, enabled = true) =>
  useRanking<RevenueRanking>("revenue", period, limit, enabled);

type Row = { user: RankedUser; value: number; label: string; detail?: string };

function RankingRows({ rows, icon: Icon }: { rows: Row[]; icon: LucideIcon }) {
  const top = Math.max(...rows.map(({ value }) => value), 1);
  return (
    <ol className="space-y-3">
      {rows.map(({ user, value, label, detail }) => (
        <li className="flex items-center gap-3" key={user.user_id}>
          <span className={`w-5 shrink-0 text-center text-xs font-semibold ${user.position <= 3 ? "text-warning" : "text-muted"}`}>
            {user.position}
          </span>
          <Avatar className="size-8" name={user.full_name} src={user.avatar_url} />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline justify-between gap-2">
              <span className="truncate text-sm text-fg">
                {user.full_name}
                <span className="ml-1.5 text-[11px] text-muted">@{user.nickname}</span>
              </span>
              <span className="flex shrink-0 items-center gap-1 text-xs font-semibold text-fg tabular-nums">
                <Icon aria-hidden="true" className="text-accent" size={12} />
                {label}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-well">
                <div className="h-full rounded-full bg-brand-strong" style={{ width: `${(value / top) * 100}%` }} />
              </div>
              {detail && <span className="shrink-0 text-[10px] text-muted">{detail}</span>}
            </div>
          </div>
        </li>
      ))}
    </ol>
  );
}

/** Users of the Flash with the most Instagram views in the period. */
export function ViewsRankingList({ period, limit = 20, emptyLabel = "Nenhuma visualização registrada no período." }: {
  period: MetricsPeriod;
  limit?: number;
  emptyLabel?: string;
}) {
  const ranking = useViewsRanking(period, limit);
  if (ranking.isLoading) return <LoadingState label="Carregando ranking" />;
  if (ranking.error || !ranking.data) {
    return <ErrorState message="Não foi possível carregar o ranking." onRetry={() => void ranking.refetch()} />;
  }
  if (ranking.data.ranking.length === 0) return <p className="text-sm text-muted">{emptyLabel}</p>;
  return (
    <RankingRows
      icon={Eye}
      rows={ranking.data.ranking.map((user) => ({ user, value: user.views, label: count(user.views) }))}
    />
  );
}

/** Users who billed the most in the period (Super Admin only). */
export function RevenueRankingList({ period, limit = 20 }: { period: MetricsPeriod; limit?: number }) {
  const ranking = useRevenueRanking(period, limit);
  if (ranking.isLoading) return <LoadingState label="Carregando ranking" />;
  if (ranking.error || !ranking.data) {
    return <ErrorState message="Não foi possível carregar o ranking." onRetry={() => void ranking.refetch()} />;
  }
  if (ranking.data.ranking.length === 0) return <p className="text-sm text-muted">Nenhuma venda paga no período.</p>;
  return (
    <RankingRows
      icon={CircleDollarSign}
      rows={ranking.data.ranking.map((user) => ({
        user,
        value: user.revenue,
        label: brl(user.revenue),
        detail: `${count(user.sales)} venda(s)`,
      }))}
    />
  );
}

/** Dashboard side card: top users by views in the dashboard's period. */
export function ViewsRankingCard({ period }: { period: MetricsPeriod }) {
  return (
    <article className="dashboard-card rounded-xl p-4">
      <p className="text-xs font-medium uppercase tracking-[0.12em] text-accent">Flash</p>
      <h2 className="mt-1 text-base font-semibold text-fg">Ranking de visualizações</h2>
      <p className="mb-4 mt-1 text-xs text-muted">Usuários com mais visualizações no período</p>
      <ViewsRankingList limit={5} period={period} />
    </article>
  );
}
