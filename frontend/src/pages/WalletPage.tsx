import { useState, type FormEvent } from "react";
import { ArrowDownToLine, CheckCircle2, Clock, Gift, Trophy, Wallet as WalletIcon, XCircle } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { brl, compact, useWallet, useWalletMutations, useWithdrawalRequests, type Wallet, type Withdrawal } from "@/features/wallet/api";
import { ApiError } from "@/services/api";

const keyTypes = [
  { value: "cpf", label: "CPF", placeholder: "000.000.000-00" },
  { value: "cnpj", label: "CNPJ", placeholder: "00.000.000/0000-00" },
  { value: "email", label: "E-mail", placeholder: "voce@email.com" },
  { value: "phone", label: "Telefone", placeholder: "+55 11 90000-0000" },
  { value: "random", label: "Chave aleatória", placeholder: "xxxxxxxx-xxxx-…" },
];
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível concluir.");
const when = (value: string | null) =>
  value ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "";
const statusInfo = {
  PAID: { label: "Pago", tone: "text-success", Icon: CheckCircle2 },
  REQUESTED: { label: "Em análise", tone: "text-warning", Icon: Clock },
  REJECTED: { label: "Recusado", tone: "text-danger", Icon: XCircle },
} as const;

function WithdrawModal({ wallet, open, onClose }: { wallet: Wallet; open: boolean; onClose: () => void }) {
  const { request } = useWalletMutations();
  const [amount, setAmount] = useState("");
  const [keyType, setKeyType] = useState("cpf");
  const [pixKey, setPixKey] = useState("");
  const value = Number(amount.replace(/\./g, "").replace(",", "."));
  const main = wallet.is_main_account;
  const valid =
    Number.isFinite(value) && value > 0 && value <= wallet.available && (main || (value >= wallet.min_withdrawal && pixKey.trim().length > 3));

  function submit(event: FormEvent) {
    event.preventDefault();
    request.mutate(
      { amount: value.toFixed(2), ...(main ? { note: "Saque feito na SmokePay" } : { pix_key_type: keyType, pix_key: pixKey.trim() }) },
      { onSuccess: () => { setAmount(""); setPixKey(""); onClose(); } },
    );
  }
  return (
    <Modal
      description={`Saldo disponível: ${brl(wallet.available)}`}
      onClose={onClose}
      open={open}
      title={main ? "Registrar saque" : "Solicitar saque"}
    >
      <form className="space-y-4" onSubmit={submit}>
        {main && (
          <p className="rounded-xl border border-line-soft bg-surface-inset p-3 text-xs text-muted">
            Sua conta é a principal da SmokePay: faça o saque no painel da SmokePay e registre o valor aqui para o saldo ficar certo.
          </p>
        )}
        <label className="block">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">Valor do saque</span>
          <span className="mt-1 flex items-center gap-2 rounded-xl border border-line bg-surface-inset px-3">
            <span className="text-sm text-muted">R$</span>
            <input
              autoFocus
              className="min-h-12 flex-1 bg-transparent text-2xl font-semibold text-fg outline-none"
              inputMode="decimal"
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0,00"
              value={amount}
            />
            <button className="rounded-lg bg-brand-soft px-2 py-1 text-xs font-semibold text-accent" onClick={() => setAmount(wallet.available.toFixed(2).replace(".", ","))} type="button">
              MAX
            </button>
          </span>
          {!main && <span className="mt-1 block text-[11px] text-muted">Mínimo {brl(wallet.min_withdrawal)}</span>}
        </label>
        {!main && (
          <div className="space-y-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">Chave Pix de destino</span>
            <select className="field" onChange={(event) => setKeyType(event.target.value)} value={keyType}>
              {keyTypes.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
            </select>
            <input
              className="field"
              onChange={(event) => setPixKey(event.target.value)}
              placeholder={keyTypes.find((item) => item.value === keyType)?.placeholder}
              value={pixKey}
            />
          </div>
        )}
        {request.error && <p className="text-xs text-danger" role="alert">{errorText(request.error)}</p>}
        <button className="btn-primary w-full" disabled={!valid || request.isPending} type="submit">
          {request.isPending ? "Enviando…" : main ? "Registrar saque" : "Confirmar saque"}
        </button>
        {!main && <p className="text-center text-[11px] text-muted">O administrador paga pela SmokePay e você é avisado aqui.</p>}
      </form>
    </Modal>
  );
}

function History({ items, onCancel }: { items: Withdrawal[]; onCancel: (id: string) => void }) {
  if (items.length === 0) return <p className="text-xs text-muted">Nenhum saque ainda.</p>;
  return (
    <ul className="divide-y divide-[color:var(--color-line-soft)]">
      {items.map((item) => {
        const info = statusInfo[item.status];
        return (
          <li className="flex items-center justify-between gap-3 py-2.5 text-sm" key={item.id}>
            <span className="min-w-0">
              <span className="block font-semibold text-fg">{brl(item.amount)}</span>
              <span className="block truncate text-[11px] text-muted">
                {when(item.created_at)}
                {item.pix_key && ` · Pix ${item.pix_key}`}
                {item.note && ` · ${item.note}`}
              </span>
            </span>
            <span className="flex shrink-0 items-center gap-2">
              <span className={`flex items-center gap-1 text-xs font-medium ${info.tone}`}>
                <info.Icon size={14} /> {info.label}
              </span>
              {item.status === "REQUESTED" && (
                <button className="text-[11px] text-muted underline hover:text-fg" onClick={() => onCancel(item.id)} type="button">
                  cancelar
                </button>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function AdminRequests() {
  const requests = useWithdrawalRequests(true);
  const { decide } = useWalletMutations();
  const items = requests.data?.items ?? [];
  return (
    <section className="glass-panel space-y-3 p-4">
      <h3 className="text-base font-semibold text-fg">Pedidos de saque para pagar ({items.length})</h3>
      <p className="text-xs text-muted">
        Pague pela SmokePay a partir da subconta indicada e marque como pago. O usuário é avisado na hora.
      </p>
      {decide.error && <ErrorState message={errorText(decide.error)} />}
      {items.length === 0 ? (
        <p className="text-xs text-muted">Nenhum pedido pendente.</p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-line-soft bg-surface-inset p-3" key={item.id}>
              <span className="min-w-0 text-xs text-muted">
                <span className="block text-sm font-semibold text-fg">{item.owner} · {brl(item.amount)}</span>
                Pix ({item.pix_key_type}): <strong className="text-fg">{item.pix_key}</strong> · subconta {item.shop_ref} · pedido em {when(item.created_at)}
              </span>
              <span className="flex gap-2">
                <button className="btn-primary !min-h-9 text-xs" disabled={decide.isPending} onClick={() => decide.mutate({ id: item.id, action: "paid" })} type="button">
                  Marcar como pago
                </button>
                <button className="btn-secondary !min-h-9 text-xs" disabled={decide.isPending} onClick={() => decide.mutate({ id: item.id, action: "rejected" })} type="button">
                  Recusar
                </button>
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function WalletPage() {
  const { user } = useAuth();
  const wallet = useWallet();
  const { cancel } = useWalletMutations();
  const [open, setOpen] = useState(false);
  if (wallet.isLoading) return <LoadingState label="Carregando carteira" />;
  if (wallet.error) return <ErrorState message={errorText(wallet.error)} onRetry={() => void wallet.refetch()} />;
  const data = wallet.data!;
  const cards: [string, string, string?][] = [
    ["Faturamento do mês", brl(data.month_revenue)],
    ["Disponível para sacar", brl(data.available), "text-success"],
    ["Em análise", brl(data.pending), "text-warning"],
    ["Já sacado", brl(data.withdrawn)],
  ];
  return (
    <div className="mx-auto max-w-[1100px] space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Financeiro</p>
          <h1 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-fg sm:text-3xl">
            <WalletIcon className="text-accent" size={26} /> Carteira
          </h1>
          <p className="mt-1 text-sm text-muted">Seu faturamento, o que tem para sacar, o que já sacou e suas metas.</p>
        </div>
        <button className="btn-primary" disabled={data.available <= 0} onClick={() => setOpen(true)} type="button">
          <ArrowDownToLine size={16} /> {data.is_main_account ? "Registrar saque" : "Sacar"}
        </button>
      </header>

      <dl className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {cards.map(([title, value, tone]) => (
          <div className="glass-panel px-4 py-3" key={title}>
            <dt className="text-[11px] text-muted">{title}</dt>
            <dd className={`mt-1 text-xl font-semibold ${tone ?? "text-fg"}`}>{value}</dd>
          </div>
        ))}
      </dl>
      <p className="text-[11px] text-muted">
        Ganho total no FlashBot (já sem taxas e comissões): {brl(data.earned)}
        {data.commissions_received > 0 && ` · inclui ${brl(data.commissions_received)} de comissões dos sócios`}.
      </p>

      <section className="glass-panel space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-base font-semibold text-fg"><Trophy className="text-warning" size={17} /> Metas de faturamento</h3>
          <span className="text-xs text-muted">
            Próxima: {compact(data.goal.target)} · {data.goal.percent.toLocaleString("pt-BR")}% · prêmio: {data.goal.prize}
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-well">
          <div className="h-full rounded-full bg-success" style={{ width: `${Math.min(100, data.goal.percent)}%` }} />
        </div>
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-5">
          {data.goal.goals.map((goal) => (
            <li className={`rounded-xl border p-2.5 text-xs ${goal.reached ? "border-success/50 bg-success-soft text-success" : "border-line-soft bg-surface-inset text-muted"}`} key={goal.amount}>
              <span className="flex items-center gap-1 font-semibold"><Gift size={13} /> {compact(goal.amount)}</span>
              <span className="mt-0.5 block">{goal.prize}</span>
            </li>
          ))}
        </ul>
      </section>

      {user?.role === "SUPER_ADMIN" && <AdminRequests />}

      <section className="glass-panel space-y-2 p-4">
        <h3 className="text-base font-semibold text-fg">Histórico de saques</h3>
        {data.withdrawals.length === 0 ? <EmptyState message="Nenhum saque ainda." /> : <History items={data.withdrawals} onCancel={(id) => cancel.mutate(id)} />}
      </section>

      <WithdrawModal onClose={() => setOpen(false)} open={open} wallet={data} />
    </div>
  );
}
