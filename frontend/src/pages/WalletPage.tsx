import { useState, type FormEvent } from "react";
import { ArrowDownToLine, CheckCircle2, Clock, Trophy, Wallet as WalletIcon, XCircle } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { useChiefLabel } from "@/features/partners/api";
import { AwardsCarousel } from "@/features/wallet/AwardsCarousel";
import { brl, compact, useWallet, useWalletMutations, type Wallet, type Withdrawal } from "@/features/wallet/api";
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
  PROCESSING: { label: "Processando", tone: "text-warning", Icon: Clock },
  FAILED: { label: "Falhou", tone: "text-danger", Icon: XCircle },
} as const;

type WithdrawBody = { amount: string; pix_key_type: string; pix_key: string };
export type WithdrawSender = {
  mutate: (body: WithdrawBody, options: { onSuccess: () => void }) => void;
  error: unknown;
  isPending: boolean;
};

function OwnWithdrawModal(props: { wallet: Wallet; open: boolean; onClose: () => void }) {
  const { request } = useWalletMutations();
  return <WithdrawModal {...props} request={request} />;
}

/** Pix withdrawal form; the Super Admin reuses it to pay out a partner's subaccount. */
export function WithdrawModal({ wallet, open, onClose, request, title = "Solicitar saque — SmokePay" }: {
  wallet: Pick<Wallet, "available" | "withdrawable" | "withdraw_fee" | "min_withdrawal" | "is_main_account">;
  open: boolean;
  onClose: () => void;
  request: WithdrawSender;
  title?: string;
}) {
  const [amount, setAmount] = useState("");
  const [keyType, setKeyType] = useState("cpf");
  const [pixKey, setPixKey] = useState("");
  // Two steps: fill in, then review the destination and confirm (a Pix cannot be undone).
  const [reviewing, setReviewing] = useState(false);
  const [checked, setChecked] = useState(false);
  const value = Number(amount.replace(/\./g, "").replace(",", "."));
  const main = wallet.is_main_account;
  const valid =
    Number.isFinite(value) && value > 0 && value <= (wallet.withdrawable ?? wallet.available) && pixKey.trim().length > 3 && (main || value >= wallet.min_withdrawal);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (!reviewing) {
      setReviewing(true);
      setChecked(false);
      return;
    }
    if (!checked) return;
    request.mutate(
      { amount: value.toFixed(2), pix_key_type: keyType, pix_key: pixKey.trim() },
      { onSuccess: () => { setAmount(""); setPixKey(""); setReviewing(false); onClose(); } },
    );
  }
  const close = () => {
    setReviewing(false);
    onClose();
  };
  const keyLabel = keyTypes.find((item) => item.value === keyType)?.label ?? keyType;
  const fee = wallet.withdraw_fee ?? 0;
  return (
    <Modal
      description={`Saldo disponível: ${brl(wallet.available)}`}
      onClose={close}
      open={open}
      title={reviewing ? "Confira antes de enviar" : title}
    >
      {reviewing ? (
        <form className="space-y-4" onSubmit={submit}>
          <div className="rounded-2xl border border-warning/40 bg-warning/10 p-4">
            <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-warning">O Pix vai para esta chave</p>
            <p className="mt-2 text-xs text-muted">Tipo: <b className="text-fg">{keyLabel}</b></p>
            <p className="mt-1 break-all font-mono text-lg font-semibold text-fg">{pixKey.trim()}</p>
            <p className="mt-2 text-[11px] text-muted">
              Confira número por número. Um Pix enviado não pode ser cancelado; se a chave estiver errada, o dinheiro vai para quem for dono dela.
            </p>
          </div>
          <dl className="space-y-1 rounded-xl border border-line-soft bg-surface-inset p-3 text-sm">
            <div className="flex justify-between"><dt className="text-muted">Valor que cai no Pix</dt><dd className="font-semibold text-success">{brl(value)}</dd></div>
            <div className="flex justify-between"><dt className="text-muted">Taxa de saque (SmokePay)</dt><dd className="font-semibold text-warning">+ {brl(fee)}</dd></div>
            <div className="flex justify-between border-t border-line-soft pt-1"><dt className="text-muted">Sai do saldo</dt><dd className="font-semibold text-fg">{brl(value + fee)}</dd></div>
          </dl>
          <label className="flex cursor-pointer items-start gap-3 rounded-xl border border-line-soft p-3 text-sm text-fg-2">
            <input checked={checked} className="mt-0.5 size-5 shrink-0 accent-[var(--brand-c)]" onChange={(event) => setChecked(event.target.checked)} type="checkbox" />
            Conferi: a chave Pix e o valor estão corretos e a conta é de quem vai receber.
          </label>
          {Boolean(request.error) && <p className="text-xs text-danger" role="alert">{errorText(request.error)}</p>}
          <div className="grid grid-cols-2 gap-2">
            <button className="btn-secondary" disabled={request.isPending} onClick={() => setReviewing(false)} type="button">
              Voltar e corrigir
            </button>
            <button className="btn-primary" disabled={!checked || request.isPending} type="submit">
              {request.isPending ? "Enviando…" : "Confirmar e enviar"}
            </button>
          </div>
        </form>
      ) : (
      <form className="space-y-4" onSubmit={submit}>
        {main && (
          <p className="rounded-xl border border-line-soft bg-surface-inset p-3 text-xs text-muted">
            Saque da carteira principal da SmokePay (a conta dona da chave de API).
          </p>
        )}
        <label className="block">
          <span className="text-[11px] font-semibold uppercase tracking-[0.12em] text-muted">Valor do saque</span>
          <span className="mt-1 flex items-center gap-2 rounded-xl border border-line bg-surface-inset px-3">
            <span className="text-sm text-muted">R$</span>
            <input
              autoFocus
              className="min-h-12 w-full min-w-0 flex-1 bg-transparent text-2xl font-semibold text-fg outline-none"
              inputMode="decimal"
              onChange={(event) => setAmount(event.target.value)}
              placeholder="0,00"
              value={amount}
            />
            <button className="shrink-0 rounded-lg bg-brand-soft px-3 py-2 text-xs font-semibold text-accent" onClick={() => setAmount((wallet.withdrawable ?? wallet.available).toFixed(2).replace(".", ","))} type="button">
              MAX
            </button>
          </span>
          {!main && (
            <span className={`mt-1 block text-[11px] ${(wallet.withdrawable ?? wallet.available) < wallet.min_withdrawal ? "text-warning" : "text-muted"}`}>
              Mínimo {brl(wallet.min_withdrawal)} · taxa de saque da SmokePay {brl(wallet.withdraw_fee ?? 0)} (sai do saldo) · dá para sacar até {brl(wallet.withdrawable ?? wallet.available)}
              {(wallet.withdrawable ?? wallet.available) < wallet.min_withdrawal &&
                ` · faltam ${brl(wallet.min_withdrawal - (wallet.withdrawable ?? wallet.available))} para liberar o saque`}
            </span>
          )}
        </label>
        {(
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
        <dl className="space-y-1 rounded-xl border border-line-soft bg-surface-inset p-3 text-xs">
          <div className="flex justify-between"><dt className="text-muted">Você recebe no Pix</dt><dd className="font-semibold text-fg">{brl(value > 0 ? value : 0)}</dd></div>
          <div className="flex justify-between"><dt className="text-muted">Taxa de saque (SmokePay)</dt><dd className="font-semibold text-warning">+ {brl(wallet.withdraw_fee ?? 0)}</dd></div>
          <div className="flex justify-between border-t border-line-soft pt-1"><dt className="text-muted">Sai do seu saldo</dt><dd className="font-semibold text-fg">{brl((value > 0 ? value : 0) + (wallet.withdraw_fee ?? 0))}</dd></div>
        </dl>
        {Boolean(request.error) && <p className="text-xs text-danger" role="alert">{errorText(request.error)}</p>}
        <button className="btn-primary w-full" disabled={!valid || request.isPending} type="submit">
          Revisar saque
        </button>
        <p className="text-center text-[11px] text-muted">Na próxima tela você confere a chave Pix antes de enviar. Um saque a cada 5 minutos.</p>
      </form>
      )}
    </Modal>
  );
}

export function WithdrawalHistory({ items }: { items: Withdrawal[] }) {
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
            </span>
          </li>
        );
      })}
    </ul>
  );
}

export function WalletPage() {
  const chief = useChiefLabel();
  const wallet = useWallet();
  const [open, setOpen] = useState(false);
  if (wallet.isLoading) return <LoadingState label="Carregando carteira" />;
  if (wallet.error) return <ErrorState message={errorText(wallet.error)} onRetry={() => void wallet.refetch()} />;
  const data = wallet.data!;
  const fee = data.withdraw_fee ?? 0;
  const partner = Boolean(data.is_partner);
  const cards: [string, string, string?, string?][] = partner
    ? [
        ["Faturamento do mês", brl(data.month_revenue)],
        ["Líquido disponível para saque", brl(data.available), "text-success", `Taxa por saque ${brl(fee)} · saque até ${brl(data.withdrawable ?? data.available)}`],
        ["Processando", brl(data.pending), "text-warning"],
        ["Já sacado", brl(data.withdrawn)],
      ]
    : [
        ["Faturamento do mês", brl(data.month_revenue)],
        ["Disponível para sacar", brl(data.available), "text-success", `Taxa por saque ${brl(fee)} · saque até ${brl(data.withdrawable ?? data.available)}`],
        ["Processando", brl(data.pending), "text-warning"],
        ["Já sacado", brl(data.withdrawn)],
      ];
  // Only split by bot when SharkBot also sells; otherwise the month total already says it all.
  if ((data.month_shark_revenue ?? 0) > 0) {
    cards.splice(1, 0, ["Vendas SharkBot (mês)", brl(data.month_shark_revenue ?? 0)], ["Vendas FlashBot (mês)", brl(data.month_flash_revenue ?? 0)]);
  }
  if (!partner && (data.commission_paid ?? 0) > 0) cards.push([`Comissão paga a ${chief}`, brl(data.commission_paid ?? 0), "text-danger", "Já descontada do seu saldo"]);
  if ((data.snakepay_received ?? 0) > 0)
    cards.push(["Recebido pela SnakePay", brl(data.snakepay_received ?? 0), "text-success", "Já repassado para sua conta SnakePay · o saque é feito lá"]);
  if (data.commissions_received > 0) cards.push(["Comissões recebidas dos sócios", brl(data.commissions_received), "text-success"]);
  return (
    <div className="mx-auto max-w-[1100px] space-y-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-accent">Financeiro</p>
          <h1 className="mt-2 flex items-center gap-2 text-2xl font-semibold text-fg sm:text-3xl">
            <WalletIcon className="text-accent" size={26} /> Carteira
          </h1>
          <p className="mt-1 text-sm text-muted">
            {partner
              ? "Seu faturamento, o líquido disponível para saque e o que já foi sacado. O saque cai na sua chave Pix."
              : "Seu faturamento, o que tem para sacar, o que já sacou e suas metas."}
          </p>
        </div>
        <button className="btn-primary" disabled={data.available <= 0} onClick={() => setOpen(true)} type="button">
          <ArrowDownToLine size={16} /> Sacar
        </button>
      </header>

      <dl className="grid grid-cols-2 gap-2 lg:grid-cols-4">
        {cards.map(([title, value, tone, hint]) => (
          <div className="glass-panel min-w-0 px-4 py-3" key={title}>
            <dt className="truncate text-[11px] text-muted">{title}</dt>
            <dd className={`mt-1 truncate text-xl font-semibold ${tone ?? "text-fg"}`}>{value}</dd>
            {hint && <dd className="mt-0.5 text-[10px] leading-tight text-muted">{hint}</dd>}
          </div>
        ))}
      </dl>
      {!partner && <p className="text-[11px] text-muted">
        {data.balance_source === "smokepay" ? "Saldo lido agora da SmokePay" : "Saldo estimado (SmokePay indisponível)"}
        {data.shop_ref ? ` · subconta ${data.shop_ref}` : " · carteira principal"}. Ganho total no FlashBot (já sem taxas e comissões): {brl(data.earned)}
        {data.commissions_received > 0 && ` · inclui ${brl(data.commissions_received)} de comissões dos sócios`}.
      </p>}

      <section className="glass-panel space-y-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="flex items-center gap-2 text-base font-semibold text-fg"><Trophy className="text-warning" size={17} /> Metas de faturamento</h3>
          <span className="text-xs text-muted">
            Próxima: {compact(data.goal.target)} · {data.goal.percent.toLocaleString("pt-BR")}%
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-well">
          <div className="h-full rounded-full bg-success" style={{ width: `${Math.min(100, data.goal.percent)}%` }} />
        </div>
        <AwardsCarousel goals={data.goal.goals} revenue={data.month_revenue} />
      </section>

      <section className="glass-panel space-y-2 p-4">
        <h3 className="text-base font-semibold text-fg">Histórico de saques</h3>
        {data.withdrawals.length === 0 ? <EmptyState message="Nenhum saque ainda." /> : <WithdrawalHistory items={data.withdrawals} />}
      </section>

      <OwnWithdrawModal onClose={() => setOpen(false)} open={open} wallet={data} />
    </div>
  );
}
