import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownWideNarrow, ArrowUpNarrowWide, Info, Trophy } from "lucide-react";

import { InstagramAvatar } from "@/components/InstagramAvatar";
import { EmptyState, ErrorState } from "@/components/PageState";
import { apiRequest } from "@/services/api";
import {
  formatDateTime,
  formatNumber,
  formatPercent,
  isPeriodReady,
  periodParams,
  type MetricsPeriod,
} from "@/features/analytics/period";

type Row = {
  account_id: string;
  username: string;
  profile_picture_url: string | null;
  publications: number;
  publications_with_complete_metrics: number;
  views: number | null;
  interactions: number | null;
  engagement_rate: number | null;
  synced_at: string | null;
  sync_error: string | null;
};

export function EngagementRankingPanel({
  period,
  onSelectAccount,
}: {
  period: MetricsPeriod;
  onSelectAccount: (accountId: string) => void;
}) {
  const [order, setOrder] = useState<"desc" | "asc">("desc");
  const params = new URLSearchParams({ ...periodParams(period), order });
  const ranking = useQuery({
    queryKey: ["analytics", "engagement-ranking", params.toString()],
    queryFn: () =>
      apiRequest<{ period_label: string; formula: string; rows: Row[] }>(
        `/api/analytics/engagement-ranking?${params}`,
      ),
    enabled: isPeriodReady(period),
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
  const best = Math.max(...(ranking.data?.rows ?? []).map((row) => row.engagement_rate ?? 0), 0.0001);

  return (
    <section className="glass-panel p-4 sm:p-4" aria-labelledby="engagement-ranking-title">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 id="engagement-ranking-title" className="flex items-center gap-2 text-base font-semibold text-[#f5f7fb]">
            <Trophy size={17} className="text-[#f2d48a]" />
            Ranking de engajamento das contas
          </h3>
          <p className="mt-1 text-xs text-[#94a3b8]">{ranking.data?.period_label ?? "…"} · clique em uma conta para ver as métricas dela</p>
        </div>
        <button
          className="btn-secondary !min-h-9 !px-3 text-xs"
          onClick={() => setOrder(order === "desc" ? "asc" : "desc")}
          type="button"
        >
          {order === "desc" ? <ArrowDownWideNarrow size={15} /> : <ArrowUpNarrowWide size={15} />}
          {order === "desc" ? "Maior → menor" : "Menor → maior"}
        </button>
      </header>
      {ranking.isLoading && (
        <div className="mt-4 grid gap-2" aria-busy="true">
          {[0, 1, 2, 3].map((item) => <div className="skeleton h-12" key={item} />)}
        </div>
      )}
      {ranking.error && <div className="mt-4"><ErrorState message="Não foi possível carregar o ranking." onRetry={() => void ranking.refetch()} /></div>}
      {ranking.data && ranking.data.rows.length === 0 && (
        <div className="mt-4"><EmptyState message="Nenhuma conta com dados no período." /></div>
      )}
      {ranking.data && ranking.data.rows.length > 0 && (
        <ol className="mt-4 space-y-1.5">
          {ranking.data.rows.map((row, index) => (
            <li key={row.account_id}>
              <button
                className="flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition hover:bg-white/[0.04]"
                onClick={() => onSelectAccount(row.account_id)}
                type="button"
              >
                <span className="w-6 text-center text-xs font-semibold text-[#64748b]">
                  {row.engagement_rate === null ? "—" : index + 1}
                </span>
                <InstagramAvatar className="size-8 rounded-full object-cover" src={row.profile_picture_url} username={row.username} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm text-[#e6eaf2]">@{row.username}</span>
                    <span className="shrink-0 text-sm font-semibold text-[#7ee2bd]">{formatPercent(row.engagement_rate)}</span>
                  </span>
                  <span className="mt-1 block h-1 overflow-hidden rounded bg-white/5">
                    <span
                      className="block h-full rounded bg-gradient-to-r from-[#536dfe] to-[#00c9d8]"
                      style={{ width: `${row.engagement_rate === null ? 0 : (row.engagement_rate / best) * 100}%` }}
                    />
                  </span>
                  <span className="mt-1 block text-[11px] text-[#64748b]">
                    {row.publications_with_complete_metrics}/{row.publications} publicações com dados completos ·{" "}
                    {formatNumber(row.views)} views · {formatNumber(row.interactions)} interações · sincronizado{" "}
                    {formatDateTime(row.synced_at)}
                    {row.sync_error ? ` · ${row.sync_error}` : ""}
                  </span>
                </span>
              </button>
            </li>
          ))}
        </ol>
      )}
      {ranking.data && (
        <p className="mt-4 flex gap-2 text-[11px] leading-5 text-[#64748b]">
          <Info size={13} className="mt-0.5 shrink-0" />
          {ranking.data.formula}
        </p>
      )}
    </section>
  );
}
