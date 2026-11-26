import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, Coins, HandCoins, Plus } from "lucide-react";

import { PeriodFilter, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { ApiError } from "@/services/api";
import { addPayout, brl, setCommissionStatus, type CommissionStatus, type FinancePanel } from "./api";

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-line bg-well px-3 py-2">
      <p className="text-[10px] uppercase tracking-[0.14em] text-muted">{label}</p>
      <p className="truncate text-base font-semibold text-fg">{value}</p>
      {hint && <p className="truncate text-[11px] text-muted">{hint}</p>}
    </div>
  );
}

const STATUS_BADGE: Record<CommissionStatus, string> = {
  pending: "bg-warning/15 text-warning",
  paid: "bg-success-soft text-success",
  denied: "bg-danger/15 text-danger",
};
const STATUS_LABEL: Record<CommissionStatus, string> = {
  pending: "Pendente",
  paid: "Paga",
  denied: "Negada",
};

/**
 * Finance panel of one partnership: gateway fee, bot fee and the net split per sale, plus
 * the history of withdrawals/payouts (when each side received), all filtered by period.
 * The owner can also log a payout; the partner reads it.
 */
export function PartnerFinanceCard({
  partnershipId,
  fetchPanel,
  queryKey,
  canLogPayout = false,
}: {
  partnershipId?: string;
  fetchPanel: (period: MetricsPeriod) => Promise<FinancePanel>;
  queryKey: (string | undefined)[];
  canLogPayout?: boolean;
}) {
  const queryClient = useQueryClient();
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  const panel = useQuery({ queryKey: [...queryKey, period], queryFn: () => fetchPanel(period) });

  const [payout, setPayout] = useState<{ party: "owner" | "partner"; amount: string; note: string; paid_at: string }>({
    party: "partner", amount: "", note: "", paid_at: todayInput(),
  });
  const logPayout = useMutation({
    mutationFn: () =>
      addPayout(partnershipId!, {
        party: payout.party, amount: payout.amount.replace(",", "."), note: payout.note || undefined,
        paid_at: payout.paid_at || undefined,
      }),
    onSuccess: () => {
      setPayout((p) => ({ ...p, amount: "", note: "" }));
      void queryClient.invalidateQueries({ queryKey });
    },
  });

  const setStatus = useMutation({
    mutationFn: ({ saleId, status }: { saleId: string; status: CommissionStatus }) => setCommissionStatus(saleId, { status }),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey }),
  });

  const data = panel.data;
  const totals = data?.totals;
  const byStatus = data?.by_status;

  return (
    <div className="space-y-4">
      <div className="dashboard-card flex flex-wrap items-center justify-between gap-2 rounded-2xl px-4 py-3">
        <span className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
          <CalendarDays size={14} /> Período {data?.period_label ? `· ${data.period_label}` : ""}
        </span>
        <PeriodFilter onChange={setPeriod} value={period} />
      </div>

      {panel.isLoading && <p className="text-sm text-muted">Carregando…</p>}
      {data && data.has_partner === false && (
        <p className="rounded-xl border border-line bg-surface px-4 py-6 text-center text-sm text-muted">
          Este bot ainda não tem um parceiro ativo.
        </p>
      )}

      {data?.has_partner && totals && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
            <Stat label="Vendas" value={String(totals.sales)} />
            <Stat label="Faturamento" value={brl(totals.gross)} />
            <Stat label="Taxa gateway" value={brl(totals.gateway_fee)} />
            <Stat label="Taxa do bot" value={brl(totals.bot_fee)} hint={`${data.bot_fee ?? 0} por venda`} />
            <Stat label="Líquido (a dividir)" value={brl(totals.net)} />
            <Stat
              label={`Parceiro (${data.partner_percent ?? 0}%)`}
              value={brl(totals.partner_amount)}
              hint={`Sacou ${brl(totals.partner_withdrawn)} · saldo ${brl(totals.partner_balance)}`}
            />
            <Stat
              label="Dono"
              value={brl(totals.owner_amount)}
              hint={`Sacou ${brl(totals.owner_withdrawn)} · saldo ${brl(totals.owner_balance)}`}
            />
          </div>

          {byStatus && (
            <div className="grid grid-cols-3 gap-2">
              <Stat label="Comissão pendente" value={brl(byStatus.pending.partner_amount)} hint={`${byStatus.pending.count} venda(s)`} />
              <Stat label="Comissão paga" value={brl(byStatus.paid.partner_amount)} hint={`${byStatus.paid.count} venda(s)`} />
              <Stat label="Comissão negada" value={brl(byStatus.denied.partner_amount)} hint={`${byStatus.denied.count} venda(s)`} />
            </div>
          )}

          {/* Per-sale ledger */}
          <div className="overflow-hidden rounded-2xl border border-line bg-surface">
            <div className="flex items-center gap-2 border-b border-line px-4 py-2.5 text-sm font-semibold text-fg">
              <Coins size={15} /> Vendas e divisão
            </div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
                    <th className="px-3 py-2">Data</th>
                    <th className="px-3 py-2 text-right">Bruto</th>
                    <th className="px-3 py-2 text-right">Gateway</th>
                    <th className="px-3 py-2 text-right">Taxa bot</th>
                    <th className="px-3 py-2 text-right">Líquido</th>
                    <th className="px-3 py-2 text-right">%</th>
                    <th className="px-3 py-2 text-right">Parceiro</th>
                    <th className="px-3 py-2 text-right">Dono</th>
                    <th className="px-3 py-2 text-right">Comissão</th>
                  </tr>
                </thead>
                <tbody>
                  {(data.sales ?? []).map((s) => (
                    <tr key={s.id} className="border-t border-line/60">
                      <td className="px-3 py-2 text-muted">{new Date(s.paid_at).toLocaleString("pt-BR", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })}</td>
                      <td className="px-3 py-2 text-right">{brl(s.gross)}</td>
                      <td className="px-3 py-2 text-right text-muted">{brl(s.gateway_fee)}</td>
                      <td className="px-3 py-2 text-right text-muted">{brl(s.bot_fee)}</td>
                      <td className="px-3 py-2 text-right">{brl(s.net)}</td>
                      <td className="px-3 py-2 text-right text-muted">{s.partner_percent}%</td>
                      <td className="px-3 py-2 text-right font-medium text-accent">{brl(s.partner_amount)}</td>
                      <td className="px-3 py-2 text-right font-medium">{brl(s.owner_amount)}</td>
                      <td className="px-3 py-2 text-right">
                        {canLogPayout ? (
                          <select
                            className="field !min-h-8 !w-auto !py-1 !text-xs"
                            value={s.payout_status}
                            disabled={setStatus.isPending}
                            onChange={(e) => setStatus.mutate({ saleId: s.id, status: e.target.value as CommissionStatus })}
                          >
                            <option value="pending">Pendente</option>
                            <option value="paid">Paga</option>
                            <option value="denied">Negada</option>
                          </select>
                        ) : (
                          <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${STATUS_BADGE[s.payout_status]}`}>
                            {STATUS_LABEL[s.payout_status]}
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {(data.sales ?? []).length === 0 && (
                    <tr><td className="px-3 py-6 text-center text-muted" colSpan={9}>Nenhuma venda no período.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Withdrawals / payouts */}
          <div className="overflow-hidden rounded-2xl border border-line bg-surface">
            <div className="flex items-center gap-2 border-b border-line px-4 py-2.5 text-sm font-semibold text-fg">
              <HandCoins size={15} /> Saques e recebimentos
            </div>
            {canLogPayout && partnershipId && (
              <form
                className="flex flex-wrap items-end gap-2 border-b border-line bg-well px-4 py-3"
                onSubmit={(e) => { e.preventDefault(); if (payout.amount.trim()) logPayout.mutate(); }}
              >
                <label className="text-xs text-muted">
                  Para
                  <select className="field !min-h-9 !text-sm" value={payout.party} onChange={(e) => setPayout((p) => ({ ...p, party: e.target.value as "owner" | "partner" }))}>
                    <option value="partner">Parceiro</option>
                    <option value="owner">Dono</option>
                  </select>
                </label>
                <label className="text-xs text-muted">
                  Valor
                  <input className="field !min-h-9 !w-28 !text-sm" inputMode="decimal" placeholder="0,00" value={payout.amount} onChange={(e) => setPayout((p) => ({ ...p, amount: e.target.value }))} />
                </label>
                <label className="text-xs text-muted">
                  Data
                  <input className="field !min-h-9 !text-sm" type="date" value={payout.paid_at} onChange={(e) => setPayout((p) => ({ ...p, paid_at: e.target.value }))} />
                </label>
                <label className="min-w-[8rem] flex-1 text-xs text-muted">
                  Observação
                  <input className="field !min-h-9 !text-sm" placeholder="opcional" value={payout.note} onChange={(e) => setPayout((p) => ({ ...p, note: e.target.value }))} />
                </label>
                <button className="btn-primary !min-h-9" disabled={logPayout.isPending || !payout.amount.trim()} type="submit">
                  <Plus size={15} /> Registrar
                </button>
              </form>
            )}
            {logPayout.error && (
              <p className="px-4 py-2 text-sm text-danger">
                {logPayout.error instanceof ApiError ? logPayout.error.message : "Não foi possível registrar."}
              </p>
            )}
            <ul className="divide-y divide-line/60">
              {(data.payouts ?? []).map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                  <span className="flex items-center gap-2">
                    <span className={`rounded-full px-2 py-0.5 text-[11px] font-medium ${p.party === "partner" ? "bg-brand-soft text-accent" : "bg-well text-fg-2"}`}>
                      {p.party === "partner" ? "Parceiro" : "Dono"}
                    </span>
                    <span className="text-muted">{new Date(p.paid_at).toLocaleDateString("pt-BR")}</span>
                    {p.note && <span className="truncate text-muted">· {p.note}</span>}
                  </span>
                  <span className="font-semibold">{brl(p.amount)}</span>
                </li>
              ))}
              {(data.payouts ?? []).length === 0 && (
                <li className="px-4 py-6 text-center text-sm text-muted">Nenhum saque/recebimento registrado no período.</li>
              )}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
