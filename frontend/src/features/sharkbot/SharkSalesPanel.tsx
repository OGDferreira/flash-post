import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Info, ShoppingBag } from "lucide-react";

import { EmptyState, ErrorState } from "@/components/PageState";
import {
  formatDateTime,
  formatNumber,
  formatPercent,
  isPeriodReady,
  moneyFormat,
  periodParams,
  type MetricsPeriod,
} from "@/features/analytics/period";
import { useSharkAccounts } from "@/features/sharkbot/SharkAccountsPanel";
import { apiRequest } from "@/services/api";

type Sale = {
  id: string;
  status: "paid" | "pending";
  amount: string | null;
  plan_name: string | null;
  bot_name: string | null;
  flow_name: string | null;
  customer_name: string | null;
  customer_username: string | null;
  shark_account_name: string | null;
  instagram_username: string | null;
  created_at: string;
  paid_at: string | null;
};

type Summary = {
  leads: number;
  lead_buyers: number;
  pix_generated: number;
  pix_paid_from_period: number;
  purchases: number;
  purchases_without_amount: number;
  revenue: string;
  pix_to_paid_rate: number | null;
  lead_to_purchase_rate: number | null;
  leads_per_purchase: number | null;
  average_ticket: string | null;
};

type Response = {
  period_label: string;
  time_zone: string;
  page: number;
  page_size: number;
  total: number;
  items: Sale[];
  summary: Summary;
  criteria: Record<string, string>;
};

const money = (value: string | null) => (value === null ? "—" : moneyFormat.format(Number(value)));

export function SharkSalesPanel({ period }: { period: MetricsPeriod }) {
  const [status, setStatus] = useState<"paid" | "pending" | "all">("paid");
  const [accountId, setAccountId] = useState("");
  const [sharkAccountId, setSharkAccountId] = useState("");
  const [page, setPage] = useState(1);
  const sharkAccounts = useSharkAccounts();
  const igAccounts = useQuery({
    queryKey: ["instagram", "accounts"],
    queryFn: () => apiRequest<{ accounts: { id: string; username: string }[] }>("/api/instagram/accounts"),
    staleTime: 60_000,
  });
  const filterKey = JSON.stringify([period, status, accountId, sharkAccountId]);
  useEffect(() => setPage(1), [filterKey]);

  const params = new URLSearchParams({
    ...periodParams(period),
    status,
    page: String(page),
    page_size: "20",
    ...(accountId ? { account_id: accountId } : {}),
    ...(sharkAccountId ? { shark_account_id: sharkAccountId } : {}),
  });
  const sales = useQuery({
    queryKey: ["sharkbot", "sales", params.toString()],
    queryFn: () => apiRequest<Response>(`/api/sharkbot/sales?${params}`),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
    staleTime: 30_000,
  });
  const data = sales.data;
  const summary = data?.summary;
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;
  const extraShark = (sharkAccounts.data ?? []).filter((item) => item.id);

  return (
    <section className="space-y-4" aria-labelledby="sales-title">
      <div className="glass-panel p-4 sm:p-4">
        <header className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <h3 id="sales-title" className="flex items-center gap-2 text-base font-semibold text-fg">
              <ShoppingBag size={17} className="text-success" />
              Vendas do SharkBot
            </h3>
            <p className="mt-1 text-xs text-muted">{data?.period_label ?? "…"} · dias no fuso {data?.time_zone ?? "…"}</p>
          </div>
          <div className="flex flex-wrap gap-2">
            <select aria-label="Situação" className="field !min-h-9 !w-auto !py-0 !text-xs" onChange={(e) => setStatus(e.target.value as typeof status)} value={status}>
              <option value="paid">Vendas pagas</option>
              <option value="pending">PIX pendentes</option>
              <option value="all">Todos os PIX</option>
            </select>
            <select aria-label="Conta do Instagram" className="field !min-h-9 !w-auto !py-0 !text-xs" onChange={(e) => setAccountId(e.target.value)} value={accountId}>
              <option value="">Todas as contas</option>
              {igAccounts.data?.accounts.map((item) => (
                <option key={item.id} value={item.id}>@{item.username}</option>
              ))}
            </select>
            {extraShark.length > 0 && (
              <select aria-label="Conta Shark" className="field !min-h-9 !w-auto !py-0 !text-xs" onChange={(e) => setSharkAccountId(e.target.value)} value={sharkAccountId}>
                <option value="">Todas as contas Shark</option>
                {extraShark.map((item) => (
                  <option key={item.id} value={item.id!}>{item.name}</option>
                ))}
              </select>
            )}
          </div>
        </header>
        {summary && (
          <dl className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-4 xl:grid-cols-8">
            {[
              ["Receita paga", money(summary.revenue), `${formatNumber(summary.purchases)} compras`],
              ["Ticket médio", money(summary.average_ticket), "só vendas pagas"],
              ["PIX gerados", formatNumber(summary.pix_generated), `${formatNumber(summary.pix_paid_from_period)} pagos`],
              ["PIX pago ÷ gerado", formatPercent(summary.pix_to_paid_rate), "coorte do período"],
              ["Leads", formatNumber(summary.leads), `${formatNumber(summary.lead_buyers)} compraram`],
              ["Lead → compra", formatPercent(summary.lead_to_purchase_rate), "coorte do período"],
              ["Leads por compra", summary.leads_per_purchase === null ? "—" : summary.leads_per_purchase.toLocaleString("pt-BR"), "leads ÷ compras"],
              ["Sem valor", formatNumber(summary.purchases_without_amount), "fora da receita"],
            ].map(([title, value, note]) => (
              <div className="rounded-xl border border-line-soft bg-surface-inset p-3" key={title}>
                <dt className="text-[11px] text-muted">{title}</dt>
                <dd className="mt-1 text-lg font-semibold text-fg">{value}</dd>
                <dd className="text-[10px] text-muted">{note}</dd>
              </div>
            ))}
          </dl>
        )}
      </div>

      {sales.isLoading && <div aria-busy="true" className="skeleton h-40" />}
      {sales.error && <ErrorState message="Não foi possível carregar as vendas." onRetry={() => void sales.refetch()} />}
      {data && data.total === 0 && <EmptyState message="Nenhuma venda neste período e filtro. Confira a URL do webhook em Integrações." />}
      {data && data.total > 0 && (
        <div className="glass-panel overflow-x-auto">
          <table className="w-full min-w-[820px] text-left text-xs">
            <thead className="text-muted">
              <tr className="border-b border-line-soft">
                <th className="px-4 py-3 font-medium">{status === "paid" ? "Pago em" : "Gerado em"}</th>
                <th className="px-2 py-3 font-medium">Situação</th>
                <th className="px-2 py-3 text-right font-medium">Valor</th>
                <th className="px-2 py-3 font-medium">Plano</th>
                <th className="px-2 py-3 font-medium">Bot · fluxo</th>
                <th className="px-2 py-3 font-medium">Cliente</th>
                <th className="px-2 py-3 font-medium">Conta Shark</th>
                <th className="px-4 py-3 font-medium">Instagram</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((sale) => (
                <tr className="border-b border-line-soft last:border-0" key={sale.id}>
                  <td className="whitespace-nowrap px-4 py-2.5 text-fg-2">{formatDateTime(sale.paid_at ?? sale.created_at)}</td>
                  <td className="px-2 py-2.5">
                    <span className={`rounded-full px-2 py-0.5 text-[10px] ${sale.status === "paid" ? "bg-success/15 text-success" : "bg-warning/15 text-warning"}`}>
                      {sale.status === "paid" ? "Paga" : "PIX pendente"}
                    </span>
                  </td>
                  <td className="px-2 py-2.5 text-right font-semibold text-fg">{money(sale.amount)}</td>
                  <td className="max-w-[160px] truncate px-2 py-2.5 text-fg">{sale.plan_name ?? "—"}</td>
                  <td className="max-w-[200px] truncate px-2 py-2.5 text-fg">{[sale.bot_name, sale.flow_name].filter(Boolean).join(" · ") || "—"}</td>
                  <td className="max-w-[160px] truncate px-2 py-2.5 text-fg">{sale.customer_name ?? (sale.customer_username ? `@${sale.customer_username}` : "—")}</td>
                  <td className="px-2 py-2.5 text-fg">{sale.shark_account_name ?? "Conta principal"}</td>
                  <td className="px-4 py-2.5 text-fg">{sale.instagram_username ? `@${sale.instagram_username}` : "não atribuída"}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <nav aria-label="Paginação" className="flex items-center justify-between gap-3 border-t border-line-soft px-4 py-3 text-xs text-muted">
            <span>{formatNumber(data.total)} registros · página {data.page} de {pages}</span>
            <span className="flex gap-1">
              <button aria-label="Página anterior" className="btn-secondary !min-h-8 !px-2.5" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} type="button"><ChevronLeft size={14} /></button>
              <button aria-label="Próxima página" className="btn-secondary !min-h-8 !px-2.5" disabled={page >= pages} onClick={() => setPage((p) => p + 1)} type="button"><ChevronRight size={14} /></button>
            </span>
          </nav>
        </div>
      )}
      {data && (
        <details className="glass-panel p-4 text-xs text-muted">
          <summary className="flex cursor-pointer items-center gap-2 text-fg-2"><Info size={14} /> Como cada número é calculado</summary>
          <ul className="mt-3 space-y-1.5 leading-5">
            {Object.entries(data.criteria).map(([key, text]) => <li key={key}>{text}</li>)}
            <li>Vendas sem conta do Instagram aparecem como "não atribuída": o SharkBot não informa a conta de origem.</li>
          </ul>
        </details>
      )}
    </section>
  );
}
