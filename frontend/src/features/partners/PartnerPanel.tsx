import { useState } from "react";
import { Bell } from "lucide-react";

import { useAuth } from "@/features/auth/AuthProvider";
import { brl, useMarkNoticesRead, useNotices, type Sale, type SaleTotals } from "./api";
import { SaleReceiptModal } from "./SaleReceipt";

const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;

export function TotalsGrid({ totals, commissionLabel = "Comissão do sócio", netLabel = "Você recebe (após taxa e comissão)" }: {
  totals: SaleTotals;
  commissionLabel?: string;
  netLabel?: string;
}) {
  const items: [string, string, string?][] = [
    ["Vendas pagas", String(totals.sales)],
    ["Bruto", brl(totals.gross)],
    ["Taxas do gateway", brl(totals.fees)],
    ["Líquido (após taxas)", brl(totals.gross - totals.fees)],
    [commissionLabel, brl(totals.commission)],
    [netLabel, brl(totals.net), "text-success"],
  ];
  return (
    // Sized by its own width (container query), so it also fits inside modals and side panels.
    <div className="@container">
      <dl className="grid grid-cols-2 gap-2 @lg:grid-cols-3 @5xl:grid-cols-6">
        {items.map(([title, value, tone]) => (
          <div className="min-w-0 rounded-xl border border-line-soft bg-surface-inset px-3 py-2.5" key={title}>
            <dt className="text-[11px] leading-tight text-muted">{title}</dt>
            <dd className={`mt-1 truncate text-base font-semibold ${tone ?? "text-fg"}`} title={value}>{value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function SalesTable({ sales, showCommission = true }: { sales: Sale[]; showCommission?: boolean }) {
  const { user } = useAuth();
  // The "contracheque" of each sale is for the Super Admin only.
  const canOpenReceipt = user?.role === "SUPER_ADMIN";
  const [receiptFor, setReceiptFor] = useState<string | null>(null);
  if (sales.length === 0) return <p className="text-xs text-muted">Nenhuma venda paga no período.</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-line-soft">
      <SaleReceiptModal onClose={() => setReceiptFor(null)} orderId={receiptFor} />
      <table className="w-full min-w-[560px] text-left text-xs">
        <thead className="text-muted">
          <tr className="border-b border-line-soft">
            <th className="px-3 py-2 font-medium">Venda</th>
            <th className="px-2 py-2 text-right font-medium">Bruto</th>
            <th className="px-2 py-2 text-right font-medium">Taxa</th>
            {showCommission && <th className="px-2 py-2 text-right font-medium">Comissão</th>}
            <th className="px-3 py-2 text-right font-medium">Líquido</th>
            {canOpenReceipt && <th className="px-3 py-2 text-right font-medium">Dados</th>}
          </tr>
        </thead>
        <tbody>
          {sales.map((sale) => (
            <tr className="border-b border-line-soft last:border-0" key={sale.id}>
              <td className="px-3 py-2 text-fg">
                {sale.offer_name}
                <span className="block text-[10px] text-muted">
                  {sale.paid_at ? new Date(sale.paid_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : ""}
                  {showCommission && sale.percent !== null && ` · ${percent(sale.percent)}`}
                </span>
              </td>
              <td className="px-2 py-2 text-right text-fg">{brl(sale.gross)}</td>
              <td className="px-2 py-2 text-right text-muted">{brl(sale.fee)}</td>
              {showCommission && <td className="px-2 py-2 text-right text-fg">{brl(sale.commission)}</td>}
              <td className="px-3 py-2 text-right font-semibold text-success">{brl(sale.net)}</td>
              {canOpenReceipt && (
                <td className="px-3 py-2 text-right">
                  <button className="text-accent hover:underline" onClick={() => setReceiptFor(sale.id)} type="button">
                    Dados da venda
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Chief: notices such as a partner customizing a shared funnel or commission changes. */
export function NoticesCard({ side = false }: { side?: boolean } = {}) {
  const notices = useNotices();
  const read = useMarkNoticesRead();
  const items = notices.data?.items ?? [];
  if (items.length === 0 && !side) return null;
  return (
    <section className={`glass-panel space-y-2 p-4 ${side ? "flex max-h-[calc(100dvh-110px)] flex-col" : ""}`}>
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-fg">
          <Bell className="text-accent" size={15} /> Avisos {notices.data && notices.data.unread > 0 && <span className="text-xs text-accent">({notices.data.unread} novos)</span>}
          {side && (
            <span className="flex items-center gap-1 text-[10px] font-medium uppercase tracking-wider text-success">
              <span className="size-1.5 animate-pulse rounded-full bg-success" /> ao vivo
            </span>
          )}
        </h3>
        {(notices.data?.unread ?? 0) > 0 && (
          <button className="text-xs text-muted hover:text-fg" disabled={read.isPending} onClick={() => read.mutate()} type="button">
            Marcar como lidos
          </button>
        )}
      </div>
      {side && items.length === 0 && <p className="text-xs text-muted">Nenhum aviso ainda. Vendas, comissões e atualizações da sociedade aparecem aqui.</p>}
      <ul className={`space-y-1.5 ${side ? "min-h-0 flex-1 overflow-y-auto pr-1" : ""}`}>
        {items.slice(0, side ? 40 : 6).map((item) => (
          <li className={`rounded-lg px-3 py-2 text-xs ${item.read ? "text-muted" : "bg-surface-inset text-fg"}`} key={item.id}>
            <strong>{item.title}</strong> · {item.body}
            <span className="block text-[10px] text-muted">{new Date(item.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
