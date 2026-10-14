import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowDownWideNarrow, ArrowUpNarrowWide, Bot, Info } from "lucide-react";

import { EmptyState, ErrorState } from "@/components/PageState";
import { apiRequest } from "@/services/api";
import {
  formatNumber,
  formatPercent,
  isPeriodReady,
  moneyFormat,
  periodParams,
  type MetricsPeriod,
} from "@/features/analytics/period";

type Row = {
  key: string;
  bot_id: string | null;
  bot_name: string | null;
  flow_id: string | null;
  flow_name: string | null;
  leads: number;
  pix_generated: number;
  payments_approved: number;
  revenue: string;
  payments_without_amount: number;
  lead_buyers: number;
  lead_to_buyer_rate: number | null;
  pix_paid_from_period: number;
  pix_to_paid_rate: number | null;
  average_ticket: string | null;
};

type Response = {
  period_label: string;
  time_zone: string;
  totals: Row;
  rows: Row[];
  criteria: Record<string, string>;
};

type Sort = "revenue" | "sales" | "leads" | "conversion";

function money(value: string | null) {
  return value === null ? "—" : moneyFormat.format(Number(value));
}

function label(row: Row, groupBy: "bot" | "flow") {
  const bot = row.bot_name || (row.bot_id ? `Bot ${row.bot_id}` : "Bot não identificado");
  if (groupBy === "bot") return bot;
  return `${bot} · ${row.flow_name || (row.flow_id ? `Fluxo ${row.flow_id}` : "fluxo não identificado")}`;
}

export function BotPerformancePanel({ period }: { period: MetricsPeriod }) {
  const [groupBy, setGroupBy] = useState<"bot" | "flow">("bot");
  const [sort, setSort] = useState<Sort>("revenue");
  const [order, setOrder] = useState<"desc" | "asc">("desc");
  const params = new URLSearchParams({ ...periodParams(period), group_by: groupBy, sort, order });
  const data = useQuery({
    queryKey: ["analytics", "bots", params.toString()],
    queryFn: () => apiRequest<Response>(`/api/analytics/bots?${params}`),
    enabled: isPeriodReady(period),
    staleTime: 30_000,
    placeholderData: (previous) => previous,
  });
  const totals = data.data?.totals;
  const missingAmounts = totals?.payments_without_amount ?? 0;

  return (
    <section className="space-y-4" aria-labelledby="bots-title">
      <div className="glass-panel p-4 sm:p-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 id="bots-title" className="flex items-center gap-2 text-base font-semibold text-[#f5f7fb]">
              <Bot size={17} className="text-[#8295ff]" />
              Desempenho dos bots e fluxos
            </h3>
            <p className="mt-1 text-xs text-[#94a3b8]">
              {data.data?.period_label ?? "…"} · dados recebidos do Sharkbot
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <div className="dashboard-periods" role="group" aria-label="Agrupar por">
              {(["bot", "flow"] as const).map((value) => (
                <button
                  aria-pressed={groupBy === value}
                  className={groupBy === value ? "is-selected" : ""}
                  key={value}
                  onClick={() => setGroupBy(value)}
                  type="button"
                >
                  {value === "bot" ? "Por bot" : "Por fluxo"}
                </button>
              ))}
            </div>
            <select
              aria-label="Ordenar ranking por"
              className="field !min-h-9 !w-auto !py-0 !text-xs"
              onChange={(event) => setSort(event.target.value as Sort)}
              value={sort}
            >
              <option value="revenue">Receita</option>
              <option value="sales">Vendas aprovadas</option>
              <option value="leads">Leads</option>
              <option value="conversion">Conversão lead → comprador</option>
            </select>
            <button
              aria-label={order === "desc" ? "Ordem decrescente" : "Ordem crescente"}
              className="btn-secondary !min-h-9 !px-2.5"
              onClick={() => setOrder(order === "desc" ? "asc" : "desc")}
              type="button"
            >
              {order === "desc" ? <ArrowDownWideNarrow size={15} /> : <ArrowUpNarrowWide size={15} />}
            </button>
          </div>
        </header>

        {totals && (
          <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
            {[
              ["Leads", formatNumber(totals.leads)],
              ["PIX gerados", formatNumber(totals.pix_generated)],
              ["Pagamentos aprovados", formatNumber(totals.payments_approved)],
              ["Receita aprovada", money(totals.revenue)],
              ["Lead → comprador", formatPercent(totals.lead_to_buyer_rate)],
              ["PIX → pago", formatPercent(totals.pix_to_paid_rate)],
            ].map(([title, value]) => (
              <div className="rounded-xl border border-line-soft bg-surface-inset p-3" key={title}>
                <dt className="text-[11px] text-[#94a3b8]">{title}</dt>
                <dd className="mt-1 text-lg font-semibold text-[#f5f7fb]">{value}</dd>
              </div>
            ))}
          </dl>
        )}
        {missingAmounts > 0 && (
          <p className="mt-3 text-xs text-[#f2d48a]">
            {missingAmounts} pagamento(s) aprovado(s) chegaram sem valor e não entram na receita.
          </p>
        )}
      </div>

      {data.isLoading && <div className="skeleton h-40" aria-busy="true" />}
      {data.error && <ErrorState message="Não foi possível carregar o desempenho dos bots." onRetry={() => void data.refetch()} />}
      {data.data && data.data.rows.length === 0 && (
        <EmptyState message="Nenhum evento do Sharkbot neste período. Confira a URL do webhook em Configurações." />
      )}
      {data.data && data.data.rows.length > 0 && (
        <div className="glass-panel overflow-x-auto">
          <table className="w-full min-w-[760px] text-left text-xs">
            <thead className="text-[#94a3b8]">
              <tr className="border-b border-line-soft">
                <th className="px-4 py-3 font-medium">#</th>
                <th className="px-2 py-3 font-medium">{groupBy === "bot" ? "Bot" : "Bot · fluxo"}</th>
                <th className="px-2 py-3 text-right font-medium">Leads</th>
                <th className="px-2 py-3 text-right font-medium">PIX gerados</th>
                <th className="px-2 py-3 text-right font-medium">Aprovados</th>
                <th className="px-2 py-3 text-right font-medium">Receita</th>
                <th className="px-2 py-3 text-right font-medium">Ticket médio</th>
                <th className="px-2 py-3 text-right font-medium" title={data.data.criteria.lead_to_buyer_rate}>Lead → comprador*</th>
                <th className="px-4 py-3 text-right font-medium" title={data.data.criteria.pix_to_paid_rate}>PIX → pago*</th>
              </tr>
            </thead>
            <tbody>
              {data.data.rows.map((row, index) => (
                <tr className="border-b border-line-soft last:border-0" key={row.key}>
                  <td className="px-4 py-3 text-[#64748b]">{index + 1}</td>
                  <td className="max-w-[260px] truncate px-2 py-3 text-[#e6eaf2]">{label(row, groupBy)}</td>
                  <td className="px-2 py-3 text-right text-[#dbe4f3]">{formatNumber(row.leads)}</td>
                  <td className="px-2 py-3 text-right text-[#dbe4f3]">{formatNumber(row.pix_generated)}</td>
                  <td className="px-2 py-3 text-right text-[#dbe4f3]">{formatNumber(row.payments_approved)}</td>
                  <td className="px-2 py-3 text-right font-semibold text-[#7ee2bd]">{money(row.revenue)}</td>
                  <td className="px-2 py-3 text-right text-[#dbe4f3]">{money(row.average_ticket)}</td>
                  <td className="px-2 py-3 text-right text-[#dbe4f3]">
                    {formatPercent(row.lead_to_buyer_rate)}
                    <span className="block text-[10px] text-[#64748b]">{row.lead_buyers}/{row.leads}</span>
                  </td>
                  <td className="px-4 py-3 text-right text-[#dbe4f3]">
                    {formatPercent(row.pix_to_paid_rate)}
                    <span className="block text-[10px] text-[#64748b]">{row.pix_paid_from_period}/{row.pix_generated}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {data.data && (
        <details className="glass-panel p-4 text-xs text-[#94a3b8]">
          <summary className="flex cursor-pointer items-center gap-2 text-[#cbd5e1]">
            <Info size={14} /> Como cada número é calculado
          </summary>
          <ul className="mt-3 space-y-1.5 leading-5">
            {Object.entries(data.data.criteria).map(([key, text]) => (
              <li key={key}>{text}</li>
            ))}
            <li>
              * Conversões são de coorte (acompanham os mesmos leads/PIX do período), não a divisão de
              contagens de eventos diferentes. Dias no fuso {data.data.time_zone}.
            </li>
          </ul>
        </details>
      )}
    </section>
  );
}
