import { Bell, Handshake, Info } from "lucide-react";

import { ErrorState } from "@/components/PageState";
import { Button } from "@/components/ui/Button";
import { ApiError } from "@/services/api";
import { brl, useAcceptCommission, useMarkNoticesRead, useNotices, usePartnerMe, type Sale, type SaleTotals } from "./api";

const percent = (value: number | null | undefined) =>
  value === null || value === undefined ? "—" : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;

export function TotalsGrid({ totals, commissionLabel = "Comissão do chefe", netLabel = "Você recebe (após taxa e comissão)" }: {
  totals: SaleTotals;
  commissionLabel?: string;
  netLabel?: string;
}) {
  const items: [string, string, string?][] = [
    ["Vendas pagas", String(totals.sales)],
    ["Bruto", brl(totals.gross)],
    ["Taxas SmokePay", brl(totals.fees)],
    ["Líquido (após taxas)", brl(totals.gross - totals.fees)],
    [commissionLabel, brl(totals.commission)],
    [netLabel, brl(totals.net), "text-success"],
  ];
  return (
    <dl className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-6">
      {items.map(([title, value, tone]) => (
        <div className="min-w-0 rounded-xl border border-line-soft bg-surface-inset px-3 py-2" key={title}>
          <dt className="truncate text-[11px] text-muted" title={title}>{title}</dt>
          <dd className={`mt-1 text-base font-semibold ${tone ?? "text-fg"}`}>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function SalesTable({ sales }: { sales: Sale[] }) {
  if (sales.length === 0) return <p className="text-xs text-muted">Nenhuma venda paga no período.</p>;
  return (
    <div className="overflow-x-auto rounded-xl border border-line-soft">
      <table className="w-full min-w-[560px] text-left text-xs">
        <thead className="text-muted">
          <tr className="border-b border-line-soft">
            <th className="px-3 py-2 font-medium">Venda</th>
            <th className="px-2 py-2 text-right font-medium">Bruto</th>
            <th className="px-2 py-2 text-right font-medium">Taxa</th>
            <th className="px-2 py-2 text-right font-medium">Comissão</th>
            <th className="px-3 py-2 text-right font-medium">Líquido</th>
          </tr>
        </thead>
        <tbody>
          {sales.map((sale) => (
            <tr className="border-b border-line-soft last:border-0" key={sale.id}>
              <td className="px-3 py-2 text-fg">
                {sale.offer_name}
                <span className="block text-[10px] text-muted">
                  {sale.paid_at ? new Date(sale.paid_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : ""}
                  {sale.percent !== null && ` · ${percent(sale.percent)}`}
                </span>
              </td>
              <td className="px-2 py-2 text-right text-fg">{brl(sale.gross)}</td>
              <td className="px-2 py-2 text-right text-muted">{brl(sale.fee)}</td>
              <td className="px-2 py-2 text-right text-fg">{brl(sale.commission)}</td>
              <td className="px-3 py-2 text-right font-semibold text-success">{brl(sale.net)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Dashboard card for partners: accept the commission, see revenue and the split of each sale. */
export function PartnerPanel() {
  const me = usePartnerMe();
  const accept = useAcceptCommission();
  const data = me.data;
  if (!data?.partnership) return null;
  const p = data.partnership;
  return (
    <section className="dashboard-card glass-panel space-y-3 p-4">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div>
          <h3 className="flex items-center gap-2 text-base font-semibold text-fg">
            <Handshake className="text-accent" size={17} /> Sociedade com {p.chief_name}
          </h3>
          <p className="mt-1 text-xs text-muted">
            Comissão em vigor: <strong className="text-fg">{percent(p.accepted_percent)}</strong> · últimos 30 dias ({data.period_label})
          </p>
        </div>
      </div>
      {p.pending_acceptance && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-warning/40 bg-warning-soft p-3">
          <p className="text-xs text-warning">
            {p.chief_name} propôs <strong>{percent(p.proposed_percent)}</strong> de comissão sobre o líquido de cada venda.
            {p.accepted_percent === null
              ? " Aceite para usar os loops e funis compartilhados e ativar o split."
              : ` Até você aceitar, continua valendo ${percent(p.accepted_percent)}. O novo valor vale só para vendas futuras.`}
          </p>
          <Button disabled={accept.isPending} onClick={() => accept.mutate(p.proposed_percent)} size="sm" variant="primary">
            Aceitar {percent(p.proposed_percent)}
          </Button>
        </div>
      )}
      {accept.error && <ErrorState message={accept.error instanceof ApiError ? accept.error.message : "Não foi possível aceitar."} />}
      {data.totals && <TotalsGrid totals={data.totals} />}
      <SalesTable sales={data.sales.slice(0, 8)} />
      <p className="flex gap-2 text-[11px] leading-5 text-muted">
        <Info className="mt-0.5 shrink-0" size={13} />
        {data.basis} Sua subconta na SmokePay é criada automaticamente na primeira cobrança
        {data.shop_ref ? ` (referência ${data.shop_ref})` : ""}; o saldo dela é sacado pelo administrador da plataforma.
      </p>
    </section>
  );
}

/** Chief: notices such as a partner customizing a shared funnel or accepting a commission. */
export function NoticesCard() {
  const notices = useNotices();
  const read = useMarkNoticesRead();
  const items = notices.data?.items ?? [];
  if (items.length === 0) return null;
  return (
    <section className="glass-panel space-y-2 p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 text-sm font-semibold text-fg">
          <Bell className="text-accent" size={15} /> Avisos {notices.data!.unread > 0 && <span className="text-xs text-accent">({notices.data!.unread} novos)</span>}
        </h3>
        {notices.data!.unread > 0 && (
          <button className="text-xs text-muted hover:text-fg" disabled={read.isPending} onClick={() => read.mutate()} type="button">
            Marcar como lidos
          </button>
        )}
      </div>
      <ul className="space-y-1.5">
        {items.slice(0, 6).map((item) => (
          <li className={`rounded-lg px-3 py-2 text-xs ${item.read ? "text-muted" : "bg-surface-inset text-fg"}`} key={item.id}>
            <strong>{item.title}</strong> · {item.body}
            <span className="block text-[10px] text-muted">{new Date(item.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}
