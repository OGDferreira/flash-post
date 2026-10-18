import { useState } from "react";
import { ArrowDownToLine, Info } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { brl, usePartnerWallets, type PartnerWallet } from "@/features/wallet/api";
import { WithdrawModal, WithdrawalHistory } from "@/pages/WalletPage";
import { ApiError } from "@/services/api";

const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível carregar.");

/** Super Admin only: each partner's balance, what was paid out and the withdrawal history. */
export function AdminPartnerWalletsPage() {
  const { list, withdraw } = usePartnerWallets();
  const [paying, setPaying] = useState<PartnerWallet | null>(null);
  const [openHistory, setOpenHistory] = useState<string | null>(null);
  const data = list.data;
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Administração</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">Saques dos sócios</h2>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Faturamento, líquido disponível para saque, o que já foi sacado e o histórico de cada sócio. Só você vê e faz esses
          saques; o sócio vê apenas o faturamento, o líquido disponível e o total já sacado.
        </p>
      </div>
      {list.isLoading && <LoadingState label="Carregando carteiras dos sócios" />}
      {list.error && <ErrorState message={errorText(list.error)} onRetry={() => void list.refetch()} />}
      {data && data.items.length === 0 && <EmptyState message="Nenhum sócio ativo ainda." />}
      {data && data.items.length > 0 && (
        <div className="space-y-3">
          {data.items.map((item) => (
            <section className="glass-panel space-y-3 p-4" key={item.user_id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <h3 className="truncate text-base font-semibold text-fg">{item.name}</h3>
                  <p className="truncate text-xs text-muted">
                    {item.email} · sócio de {item.chief ?? "—"} · subconta {item.shop_ref}
                  </p>
                </div>
                <button
                  className="btn-primary !min-h-9 text-xs"
                  disabled={item.withdrawable <= 0}
                  onClick={() => setPaying(item)}
                  type="button"
                >
                  <ArrowDownToLine size={14} /> Sacar
                </button>
              </div>
              <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  ["Faturamento do mês", brl(item.month_revenue), "text-fg"],
                  ["Líquido disponível", brl(item.available), "text-success"],
                  ["Processando", brl(item.pending), "text-warning"],
                  ["Já sacado", brl(item.withdrawn), "text-fg"],
                ].map(([title, value, tone]) => (
                  <div className="min-w-0 rounded-xl border border-line-soft bg-surface-inset px-3 py-2" key={title}>
                    <dt className="truncate text-[11px] text-muted">{title}</dt>
                    <dd className={`mt-1 text-base font-semibold ${tone}`}>{value}</dd>
                  </div>
                ))}
              </dl>
              <p className="flex gap-2 text-[11px] leading-5 text-muted">
                <Info className="mt-0.5 shrink-0" size={13} />
                {item.balance_source === "smokepay" ? "Saldo lido agora da SmokePay" : "Saldo estimado (SmokePay indisponível)"} · taxa por
                saque {brl(item.withdraw_fee)} · dá para sacar até {brl(item.withdrawable)}.
              </p>
              <button
                className="text-xs text-accent hover:underline"
                onClick={() => setOpenHistory(openHistory === item.user_id ? null : item.user_id)}
                type="button"
              >
                {openHistory === item.user_id ? "Esconder histórico" : `Histórico de saques (${item.withdrawals.length})`}
              </button>
              {openHistory === item.user_id && <WithdrawalHistory items={item.withdrawals} />}
            </section>
          ))}
        </div>
      )}
      {paying && data && (
        <WithdrawModal
          onClose={() => setPaying(null)}
          open
          request={{
            mutate: (body, options) => withdraw.mutate({ userId: paying.user_id, ...body }, options),
            error: withdraw.error,
            isPending: withdraw.isPending,
          }}
          title={`Saque da subconta de ${paying.name}`}
          wallet={{ ...paying, is_main_account: false, min_withdrawal: data.min_withdrawal }}
        />
      )}
    </div>
  );
}
