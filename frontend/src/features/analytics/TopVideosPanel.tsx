import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownWideNarrow, ArrowUpNarrowWide, ExternalLink, Flame, Info } from "lucide-react";

import { EmptyState, ErrorState } from "@/components/PageState";
import { useSyncStatus } from "@/features/analytics/useWorkspaceSync";
import { apiRequest } from "@/services/api";
import {
  formatDateTime,
  formatNumber,
  formatPercent,
  isPeriodReady,
  periodParams,
  type MetricsPeriod,
} from "@/features/analytics/period";

type Publication = {
  id: string;
  account_id: string;
  username: string;
  permalink: string | null;
  thumbnail_url: string | null;
  caption: string | null;
  posted_at: string;
  views: number | null;
  reach: number | null;
  likes: number | null;
  comments: number | null;
  shares: number | null;
  saves: number | null;
  interactions: number | null;
  engagement_rate: number | null;
  metrics_error: string | null;
  synced_at: string;
};

type Response = {
  period_label: string;
  formula: string;
  scope: string;
  items: Publication[];
  accounts_never_synced: string[];
};

type SortKey = "views" | "engagement_rate" | "interactions" | "reach" | "posted_at";

const sortOptions: { value: SortKey; label: string }[] = [
  { value: "views", label: "Visualizações" },
  { value: "engagement_rate", label: "Taxa de engajamento" },
  { value: "interactions", label: "Interações" },
  { value: "reach", label: "Alcance" },
  { value: "posted_at", label: "Data de publicação" },
];

export function TopVideosPanel({
  period,
  accountId,
  compact = false,
}: {
  period: MetricsPeriod;
  accountId?: string;
  compact?: boolean;
}) {
  const [sort, setSort] = useState<SortKey>("views");
  const [order, setOrder] = useState<"desc" | "asc">("desc");
  const params = new URLSearchParams({
    ...periodParams(period),
    sort,
    order,
    limit: compact ? "12" : "50",
    ...(accountId ? { account_id: accountId } : {}),
  });
  const videos = useQuery({
    queryKey: ["analytics", "videos", params.toString()],
    queryFn: () => apiRequest<Response>(`/api/analytics/videos?${params}`),
    enabled: isPeriodReady(period),
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });

  const syncing = Boolean(useSyncStatus().data?.running);
  return (
    <section className="glass-panel p-4 sm:p-4" aria-labelledby={`videos-${accountId ?? "all"}`}>
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 id={`videos-${accountId ?? "all"}`} className="flex items-center gap-2 text-base font-semibold text-[#f5f7fb]">
            <Flame size={17} className="text-[#ff9f6b]" />
            {compact ? "Publicações desta conta" : "Vídeos em alta"}
          </h3>
          <p className="mt-1 text-xs text-[#94a3b8]">
            {videos.data?.period_label ?? "…"} · {videos.data?.scope ?? "Publicações do período"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="sr-only" htmlFor={`sort-${accountId ?? "all"}`}>Ordenar por</label>
          <select
            className="field !min-h-9 !w-auto !py-0 !text-xs"
            id={`sort-${accountId ?? "all"}`}
            onChange={(event) => setSort(event.target.value as SortKey)}
            value={sort}
          >
            {sortOptions.map((option) => (
              <option key={option.value} value={option.value}>{option.label}</option>
            ))}
          </select>
          <button
            aria-label={order === "desc" ? "Ordem decrescente" : "Ordem crescente"}
            className="btn-secondary !min-h-9 !px-2.5"
            onClick={() => setOrder(order === "desc" ? "asc" : "desc")}
            title={order === "desc" ? "Maior para menor" : "Menor para maior"}
            type="button"
          >
            {order === "desc" ? <ArrowDownWideNarrow size={15} /> : <ArrowUpNarrowWide size={15} />}
          </button>
        </div>
      </header>

      {videos.isLoading && (
        <div className="mt-4 grid gap-2" aria-busy="true">
          {[0, 1, 2].map((item) => <div className="skeleton h-16" key={item} />)}
        </div>
      )}
      {videos.error && <div className="mt-4"><ErrorState message="Não foi possível carregar as publicações." onRetry={() => void videos.refetch()} /></div>}
      {videos.data && videos.data.items.length === 0 && (
        <div className="mt-4">
          <EmptyState
            message={
              syncing
                ? "Carregando as publicações de todas as contas em segundo plano… elas aparecem aqui assim que terminar."
                : videos.data.accounts_never_synced.length
                ? "Ainda não há Insights sincronizados para este período. Use “Atualizar agora” acima para buscar na Meta."
                : "Nenhuma publicação no período selecionado."
            }
          />
        </div>
      )}
      {videos.data && videos.data.items.length > 0 && (
        <ol className="mt-4 space-y-2">
          {videos.data.items.map((item, index) => (
            <li className="flex gap-3 rounded-xl border border-line-soft bg-surface-inset p-3" key={item.id}>
              <span className="w-6 shrink-0 pt-1 text-center text-xs font-semibold text-[#64748b]">{index + 1}</span>
              {item.thumbnail_url ? (
                <img alt="" className="size-14 shrink-0 rounded-lg object-cover" loading="lazy" src={item.thumbnail_url} />
              ) : (
                <span className="grid size-14 shrink-0 place-items-center rounded-lg bg-white/5 text-[10px] text-[#64748b]">sem prévia</span>
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                  {!compact && <span className="font-medium text-[#dbe4f3]">@{item.username}</span>}
                  <span className="text-[#64748b]">{formatDateTime(item.posted_at)}</span>
                  {item.permalink && (
                    <a className="inline-flex items-center gap-1 text-[#aab7ff] hover:text-white" href={item.permalink} rel="noreferrer" target="_blank">
                      abrir <ExternalLink size={11} />
                    </a>
                  )}
                </div>
                {item.caption && <p className="mt-0.5 truncate text-xs text-[#94a3b8]">{item.caption}</p>}
                <dl className="mt-1.5 grid grid-cols-3 gap-x-3 gap-y-0.5 text-[11px] text-[#94a3b8] sm:grid-cols-6">
                  <div><dt className="inline">Views </dt><dd className="inline font-semibold text-[#f5f7fb]">{formatNumber(item.views)}</dd></div>
                  <div><dt className="inline">Engaj. </dt><dd className="inline font-semibold text-[#7ee2bd]">{formatPercent(item.engagement_rate)}</dd></div>
                  <div><dt className="inline">Interações </dt><dd className="inline text-[#dbe4f3]">{formatNumber(item.interactions)}</dd></div>
                  <div><dt className="inline">Curtidas </dt><dd className="inline text-[#dbe4f3]">{formatNumber(item.likes)}</dd></div>
                  <div><dt className="inline">Coment. </dt><dd className="inline text-[#dbe4f3]">{formatNumber(item.comments)}</dd></div>
                  <div><dt className="inline">Compart. </dt><dd className="inline text-[#dbe4f3]">{formatNumber(item.shares)}</dd></div>
                </dl>
                {item.metrics_error && <p className="mt-1 text-[11px] text-[#f2d48a]">{item.metrics_error}</p>}
              </div>
            </li>
          ))}
        </ol>
      )}
      {videos.data && (
        <p className="mt-4 flex gap-2 text-[11px] leading-5 text-[#64748b]">
          <Info size={13} className="mt-0.5 shrink-0" />
          {videos.data.formula}
        </p>
      )}
    </section>
  );
}
