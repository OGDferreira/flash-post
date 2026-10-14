import { useQuery } from "@tanstack/react-query";
import { Info } from "lucide-react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { EmptyState, ErrorState } from "@/components/PageState";
import {
  formatDateTime,
  formatNumber,
  isPeriodReady,
  periodParams,
  type MetricsPeriod,
} from "@/features/analytics/period";
import { useSyncStatus } from "@/features/analytics/useWorkspaceSync";
import { apiRequest } from "@/services/api";

type Point = {
  day: string;
  received_views: number | null;
  received_accounts: number;
  expected_accounts: number;
  published_videos: number;
  published_videos_with_views: number;
  published_videos_views: number | null;
  provisional: boolean;
};

type Response = {
  period_label: string;
  time_zone: string;
  days: Point[];
  received_total: number | null;
  received_days_complete: number;
  received_days_total: number;
  published_videos_views_total: number | null;
  synced_at: string | null;
  definitions: Record<string, string>;
};

const dayLabel = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;

export function DailyViewsPanel({ period, accountId }: { period: MetricsPeriod; accountId?: string }) {
  const params = new URLSearchParams({ ...periodParams(period), ...(accountId ? { account_id: accountId } : {}) });
  const query = useQuery({
    queryKey: ["analytics", "views-daily", params.toString()],
    queryFn: () => apiRequest<Response>(`/api/analytics/views-daily?${params}`),
    enabled: isPeriodReady(period),
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  });
  const data = query.data;
  const syncing = Boolean(useSyncStatus().data?.running);
  const chart = (data?.days ?? []).map((point) => ({
    label: dayLabel(point.day),
    received: point.received_views,
    published: point.published_videos_views,
  }));

  return (
    <section className="glass-panel p-4 sm:p-4" aria-labelledby="daily-views-title">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 id="daily-views-title" className="text-base font-semibold text-[#f5f7fb]">Visualizações por dia</h3>
          <p className="mt-1 text-xs text-[#94a3b8]">
            {data?.period_label ?? "…"} · dias no fuso {data?.time_zone ?? "…"} · sincronizado {formatDateTime(data?.synced_at)}
          </p>
        </div>
        {data && (
          <dl className="flex flex-wrap gap-2 text-xs">
            <div className="rounded-xl border border-line-soft bg-surface-inset px-3 py-2">
              <dt className="text-[11px] text-[#94a3b8]">Recebidas no período</dt>
              <dd className="font-semibold text-[#f5f7fb]">
                {data.received_total === null ? "incompleto" : formatNumber(data.received_total)}
                <span className="ml-1 font-normal text-[#64748b]">({data.received_days_complete}/{data.received_days_total} dias)</span>
              </dd>
            </div>
            <div className="rounded-xl border border-line-soft bg-surface-inset px-3 py-2">
              <dt className="text-[11px] text-[#94a3b8]">Acumuladas dos publicados</dt>
              <dd className="font-semibold text-[#f5f7fb]">{formatNumber(data.published_videos_views_total)}</dd>
            </div>
          </dl>
        )}
      </header>
      {(query.isLoading || query.isFetching || syncing) && !query.error && (
        <p aria-live="polite" className="mt-3 flex items-center gap-2 text-xs text-[#8295ff]">
          <span className="size-2 animate-pulse rounded-full bg-[#8295ff]" />
          {syncing ? "Buscando as visualizações na Meta em segundo plano…" : "Carregando…"}
        </p>
      )}
      {data && !syncing && !data.synced_at && (
        <p className="mt-3 rounded-xl border border-[#6b552b] bg-[#1c180e]/60 px-3 py-2 text-xs text-[#f2d48a]">
          Ainda não há dados diários da Meta para este período. Use “Atualizar agora” acima; se continuar vazio, verifique a permissão instagram_business_manage_insights nas contas.
        </p>
      )}
      {query.isLoading && <div aria-busy="true" className="skeleton mt-4 h-56" />}
      {query.error && <div className="mt-4"><ErrorState message="Não foi possível carregar as visualizações." onRetry={() => void query.refetch()} /></div>}
      {data && data.days.length === 0 && <div className="mt-4"><EmptyState message="Sem dias no período." /></div>}
      {data && data.days.length > 0 && (
        <>
          <div className="mt-4 h-60" role="img" aria-label="Visualizações recebidas por dia e acumuladas dos vídeos publicados no dia">
            <ResponsiveContainer height="100%" width="100%">
              <BarChart data={chart} margin={{ left: -12, right: 4, top: 4 }}>
                <CartesianGrid stroke="rgba(148,163,255,0.1)" vertical={false} />
                <XAxis dataKey="label" interval="preserveStartEnd" stroke="#64748b" tick={{ fontSize: 11 }} />
                <YAxis stroke="#64748b" tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ background: "rgba(8,11,24,0.95)", border: "1px solid rgba(148,163,255,0.25)", borderRadius: 12, fontSize: 12 }}
                  formatter={(value) => (value === null || value === undefined ? "indisponível" : formatNumber(Number(value)))}
                />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="received" fill="#536dfe" name="Recebidas no dia" radius={[4, 4, 0, 0]} />
                <Bar dataKey="published" fill="#00c9d8" name="Acumuladas dos publicados no dia" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-4 max-h-72 overflow-auto rounded-xl border border-line-soft">
            <table className="w-full min-w-[560px] text-left text-xs">
              <thead className="sticky top-0 bg-[var(--color-surface-raised)] text-[#94a3b8]">
                <tr>
                  <th className="px-3 py-2 font-medium">Dia</th>
                  <th className="px-2 py-2 text-right font-medium">Recebidas no dia</th>
                  <th className="px-2 py-2 text-right font-medium">Vídeos publicados</th>
                  <th className="px-3 py-2 text-right font-medium">Views acumuladas deles</th>
                </tr>
              </thead>
              <tbody>
                {[...data.days].reverse().map((point) => (
                  <tr className="border-t border-line-soft" key={point.day}>
                    <td className="px-3 py-2 text-[#cbd5e1]">
                      {dayLabel(point.day)}
                      {point.provisional && <span className="ml-2 rounded-full bg-[#f2d48a]/15 px-1.5 py-0.5 text-[10px] text-[#f2d48a]">pode subir</span>}
                    </td>
                    <td className="px-2 py-2 text-right text-[#f5f7fb]">
                      {point.received_views === null ? (
                        <span title={`${point.received_accounts} de ${point.expected_accounts} contas com dado`} className="text-[#64748b]">indisponível</span>
                      ) : formatNumber(point.received_views)}
                    </td>
                    <td className="px-2 py-2 text-right text-[#cbd5e1]">{point.published_videos}</td>
                    <td className="px-3 py-2 text-right text-[#f5f7fb]">
                      {point.published_videos === 0 ? "—" : point.published_videos_views === null ? <span className="text-[#64748b]">indisponível</span> : formatNumber(point.published_videos_views)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <ul className="mt-4 space-y-1.5 text-[11px] leading-5 text-[#64748b]">
            {Object.values(data.definitions).map((text) => (
              <li className="flex gap-2" key={text}><Info className="mt-0.5 shrink-0" size={12} />{text}</li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
