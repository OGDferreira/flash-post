import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDownLeft,
  ArrowUpRight,
  Banknote,
  CircleDollarSign,
  Clock3,
  UsersRound,
  Wallet,
  Volume2,
} from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";

type FinanceTransaction = {
  id: string;
  kind: "sale" | "withdrawal" | "collaborator_payment";
  direction: "inflow" | "outflow";
  description: string;
  amount: string;
  occurred_at: string;
};

type WithdrawalRecord = {
  id: string;
  amount: string;
  note: string | null;
  created_at: string;
};

type CollaboratorPaymentRecord = {
  id: string;
  collaborator_name: string;
  amount: string;
  period_start: string;
  paid_at: string;
};

type FinanceSummary = {
  gross_sales: string;
  income: string;
  withdrawals: string;
  collaborator_payments: string;
  balance: string;
  withdrawals_today: string;
  daily_withdrawal_goal: string;
  operation_revenue: {
    operation_name: string;
    sale_count: number;
    gross_amount: string;
    net_amount: string;
  }[];
  transactions: FinanceTransaction[];
  withdrawal_history: WithdrawalRecord[];
  collaborator_payment_history: CollaboratorPaymentRecord[];
};

function formatMoney(value: string | number): string {
  return new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
  }).format(Number(value));
}

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(value));
}

export function FinancePage() {
  const queryClient = useQueryClient();
  const [withdrawalAmount, setWithdrawalAmount] = useState("");
  const [withdrawalNote, setWithdrawalNote] = useState("");
  const [goalDraft, setGoalDraft] = useState<string | null>(null);
  const [soundEnabled, setSoundEnabled] = useState(false);
  const [soundError, setSoundError] = useState<string | null>(null);
  const seenSaleIds = useRef<Set<string> | null>(null);
  const finance = useQuery({
    queryKey: ["finance", "cash-flow"],
    queryFn: () => apiRequest<FinanceSummary>("/api/finance"),
    retry: false,
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
  async function playSaleSound() {
    try {
      const AudioContextClass =
        window.AudioContext ??
        (window as typeof window & { webkitAudioContext?: typeof AudioContext })
          .webkitAudioContext;
      if (!AudioContextClass) {
        throw new Error("Este navegador não oferece áudio Web Audio.");
      }
      const context = new AudioContextClass();
      await context.resume();
      const gain = context.createGain();
      gain.gain.setValueAtTime(0.0001, context.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.12, context.currentTime + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, context.currentTime + 0.35);
      gain.connect(context.destination);
      for (const [offset, frequency] of [
        [0, 880],
        [0.11, 1320],
      ]) {
        const oscillator = context.createOscillator();
        oscillator.type = "sine";
        oscillator.frequency.value = frequency;
        oscillator.connect(gain);
        oscillator.start(context.currentTime + offset);
        oscillator.stop(context.currentTime + offset + 0.16);
      }
      window.setTimeout(() => void context.close(), 500);
      setSoundError(null);
    } catch (error) {
      console.warn("The sale notification sound could not be played.", error);
      setSoundError(
        "O navegador bloqueou o som. Interaja com a página e ative-o novamente.",
      );
    }
  }
  useEffect(() => {
    const sales =
      finance.data?.transactions.filter((transaction) => transaction.kind === "sale") ?? [];
    if (!finance.data) return;
    const currentIds = new Set(sales.map((sale) => sale.id));
    const knownIds = seenSaleIds.current;
    if (
      soundEnabled &&
      knownIds !== null &&
      [...currentIds].some((saleId) => !knownIds.has(saleId))
    ) {
      void playSaleSound();
    }
    seenSaleIds.current = currentIds;
  }, [finance.data, soundEnabled]);
  const refresh = () =>
    queryClient.invalidateQueries({ queryKey: ["finance", "cash-flow"] });
  const registerWithdrawal = useMutation({
    mutationFn: () =>
      apiRequest<WithdrawalRecord>("/api/finance/withdrawals", {
        method: "POST",
        body: {
          amount: withdrawalAmount,
          note: withdrawalNote.trim() || null,
        },
      }),
    onSuccess: async () => {
      setWithdrawalAmount("");
      setWithdrawalNote("");
      await refresh();
    },
  });
  const saveGoal = useMutation({
    mutationFn: (amount: string) =>
      apiRequest<FinanceSummary>("/api/finance/daily-withdrawal-goal", {
        method: "PUT",
        body: { amount },
      }),
    onSuccess: async () => {
      setGoalDraft(null);
      await refresh();
    },
  });

  if (finance.isLoading) {
    return <LoadingState label="Carregando fluxo financeiro" />;
  }
  if (finance.error || !finance.data) {
    return (
      <ErrorState
        message="Não foi possível carregar o fluxo financeiro. Atualize a página ou tente novamente."
      />
    );
  }

  const data = finance.data;
  const goal = Number(goalDraft ?? data.daily_withdrawal_goal);
  const withdrawalProgress =
    goal > 0
      ? Math.min(Math.round((Number(data.withdrawals_today) / goal) * 100), 100)
      : 0;

  return (
    <div className="mx-auto w-full max-w-7xl space-y-6">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="text-xs font-medium uppercase tracking-[0.16em] text-[#8295ff]">
            Fluxo de caixa
          </p>
          <h1 className="mt-2 text-2xl font-semibold text-[#f5f7fb] sm:text-3xl">
            Financeiro
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-[#94a3b8]">
            Entradas líquidas das vendas Smokepay, pagamentos de colaboradores e
            saques registrados neste workspace.
          </p>
        </div>
        <label className="inline-flex cursor-pointer items-center gap-2 text-xs text-[#cbd5e1]">
          <input
            checked={soundEnabled}
            onChange={(event) => {
              setSoundEnabled(event.target.checked);
              if (event.target.checked) void playSaleSound();
            }}
            type="checkbox"
          />
          <Volume2 size={14} />
          Som de nova venda
        </label>
      </header>

      {(registerWithdrawal.error || saveGoal.error) && (
        <ErrorState message="A operação financeira não foi concluída. Confira os dados e tente novamente." />
      )}

      <section aria-label="Resumo do fluxo de caixa" className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <article className="dashboard-card rounded-xl p-4">
          <div className="flex items-center gap-2 text-[#94a3b8]">
            <ArrowDownLeft className="text-[#76c8a0]" size={16} />
            <p className="text-xs">Entradas líquidas</p>
          </div>
          <p className="mt-3 text-xl font-semibold text-[#76c8a0]">
            {formatMoney(data.income)}
          </p>
          <p className="mt-1 text-[11px] text-[#78839b]">
            Após os splits Smokepay
          </p>
        </article>
        <article className="dashboard-card rounded-xl p-4">
          <div className="flex items-center gap-2 text-[#94a3b8]">
            <CircleDollarSign className="text-[#aab7ff]" size={16} />
            <p className="text-xs">Vendas brutas</p>
          </div>
          <p className="mt-3 text-xl font-semibold text-[#e6eaf2]">
            {formatMoney(data.gross_sales)}
          </p>
          <p className="mt-1 text-[11px] text-[#78839b]">
            Antes da divisão de cada operação
          </p>
        </article>
        <article className="dashboard-card rounded-xl p-4">
          <div className="flex items-center gap-2 text-[#94a3b8]">
            <UsersRound className="text-[#f2d48a]" size={16} />
            <p className="text-xs">Colaboradores pagos</p>
          </div>
          <p className="mt-3 text-xl font-semibold text-[#f2d48a]">
            {formatMoney(data.collaborator_payments)}
          </p>
          <p className="mt-1 text-[11px] text-[#78839b]">
            Saídas baixadas na gestão de colaboradores
          </p>
        </article>
        <article className="dashboard-card rounded-xl p-4">
          <div className="flex items-center gap-2 text-[#94a3b8]">
            <ArrowUpRight className="text-[#f1a3ad]" size={16} />
            <p className="text-xs">Saques registrados</p>
          </div>
          <p className="mt-3 text-xl font-semibold text-[#f1a3ad]">
            {formatMoney(data.withdrawals)}
          </p>
          <p className="mt-1 text-[11px] text-[#78839b]">
            Total histórico de retiradas
          </p>
        </article>
        <article className="dashboard-card rounded-xl border border-[#35436f] p-4">
          <div className="flex items-center gap-2 text-[#c3ccff]">
            <Wallet size={16} />
            <p className="text-xs">Saldo atual</p>
          </div>
          <p className="mt-3 text-xl font-semibold text-[#f5f7fb]">
            {formatMoney(data.balance)}
          </p>
          <p className="mt-1 text-[11px] text-[#78839b]">
            Entradas líquidas menos todas as saídas
          </p>
        </article>
      </section>

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <article className="dashboard-card rounded-xl p-5">
          <div className="flex items-center gap-2">
            <Banknote className="text-[#aab7ff]" size={17} />
            <h2 className="text-base font-semibold text-[#eef1f8]">
              Registrar saque
            </h2>
          </div>
          <p className="mt-1 text-xs text-[#78839b]">
            Registre aqui cada retirada feita da plataforma para a conta bancária.
          </p>
          <form
            className="mt-4 grid gap-3 sm:grid-cols-[minmax(0,160px)_minmax(0,1fr)_auto]"
            onSubmit={(event) => {
              event.preventDefault();
              registerWithdrawal.mutate();
            }}
          >
            <label className="grid gap-1.5 text-xs text-[#94a3b8]">
              Valor (R$)
              <input
                className="collaborator-input"
                min="0.01"
                onChange={(event) => setWithdrawalAmount(event.target.value)}
                required
                step="0.01"
                type="number"
                value={withdrawalAmount}
              />
            </label>
            <label className="grid gap-1.5 text-xs text-[#94a3b8]">
              Observação (opcional)
              <input
                className="collaborator-input"
                maxLength={240}
                onChange={(event) => setWithdrawalNote(event.target.value)}
                placeholder="Ex.: transferência para conta bancária"
                value={withdrawalNote}
              />
            </label>
            <button
              className="min-h-10 self-end rounded-lg bg-[#536dfe] px-4 text-sm font-semibold text-white disabled:opacity-50"
              disabled={registerWithdrawal.isPending}
              type="submit"
            >
              {registerWithdrawal.isPending ? "Registrando..." : "Registrar saque"}
            </button>
          </form>
        </article>

        <article className="dashboard-card rounded-xl p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-base font-semibold text-[#eef1f8]">
                Meta diária de saque
              </h2>
              <p className="mt-1 text-xs text-[#78839b]">
                {formatMoney(data.withdrawals_today)} sacados hoje · {withdrawalProgress}% da meta
              </p>
            </div>
            <Banknote className="text-[#aab7ff]" size={18} />
          </div>
          <form
            className="mt-4 flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              if (goalDraft !== null && Number.isFinite(goal)) {
                saveGoal.mutate(goal.toFixed(2));
              }
            }}
          >
            <label className="sr-only" htmlFor="daily-withdrawal-goal">
              Meta diária de saque em reais
            </label>
            <input
              className="collaborator-input min-w-0 flex-1"
              id="daily-withdrawal-goal"
              min="0"
              onChange={(event) => setGoalDraft(event.target.value)}
              placeholder="Defina a meta diária"
              step="0.01"
              type="number"
              value={goalDraft ?? data.daily_withdrawal_goal}
            />
            <button
              className="rounded-lg border border-[#34446f] px-4 text-xs font-medium text-[#c3ccff] disabled:opacity-50"
              disabled={saveGoal.isPending || goalDraft === null}
              type="submit"
            >
              {saveGoal.isPending ? "Salvando..." : "Salvar meta"}
            </button>
          </form>
          <div
            aria-label={`Meta diária de saque atingida: ${withdrawalProgress}%`}
            aria-valuemax={100}
            aria-valuemin={0}
            aria-valuenow={withdrawalProgress}
            className="mt-4 h-2 overflow-hidden rounded-full bg-[#202838]"
            role="progressbar"
          >
            <div
              className="h-full rounded-full bg-[#8295ff] transition-[width]"
              style={{ width: `${withdrawalProgress}%` }}
            />
          </div>
        </article>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <article className="dashboard-card rounded-xl p-5">
          <h2 className="text-base font-semibold text-[#eef1f8]">Histórico de Saques</h2>
          {data.withdrawal_history.length ? (
            <ul className="mt-3 divide-y divide-[#202838]">
              {data.withdrawal_history.map((item) => (
                <li className="flex items-center justify-between gap-3 py-3" key={item.id}>
                  <div className="min-w-0">
                    <p className="truncate text-sm text-[#e6eaf2]">
                      {item.note || "Saque do administrador"}
                    </p>
                    <p className="mt-1 flex items-center gap-1.5 text-[11px] text-[#78839b]">
                      <Clock3 size={12} />
                      {formatDateTime(item.created_at)}
                    </p>
                  </div>
                  <strong className="shrink-0 text-sm text-[#f1a3ad]">
                    −{formatMoney(item.amount)}
                  </strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[#78839b]">Nenhum saque registrado.</p>
          )}
        </article>

        <article className="dashboard-card rounded-xl p-5">
          <h2 className="text-base font-semibold text-[#eef1f8]">
            Despesas / Colaboradores Pagos
          </h2>
          {data.collaborator_payment_history.length ? (
            <ul className="mt-3 divide-y divide-[#202838]">
              {data.collaborator_payment_history.map((item) => (
                <li className="flex items-center justify-between gap-3 py-3" key={item.id}>
                  <div className="min-w-0">
                    <p className="truncate text-sm text-[#e6eaf2]">
                      {item.collaborator_name}
                    </p>
                    <p className="mt-1 flex items-center gap-1.5 text-[11px] text-[#78839b]">
                      <Clock3 size={12} />
                      Pago {formatDateTime(item.paid_at)} · competência{" "}
                      {new Intl.DateTimeFormat("pt-BR", {
                        month: "2-digit",
                        year: "numeric",
                        timeZone: "UTC",
                      }).format(new Date(`${item.period_start}T00:00:00Z`))}
                    </p>
                  </div>
                  <strong className="shrink-0 text-sm text-[#f2d48a]">
                    −{formatMoney(item.amount)}
                  </strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[#78839b]">
              Nenhum pagamento de colaborador registrado.
            </p>
          )}
        </article>
      </section>

      <section className="grid gap-4 xl:grid-cols-2">
        <article className="dashboard-card rounded-xl p-5">
          <h2 className="text-base font-semibold text-[#eef1f8]">
            Faturamento por operação
          </h2>
          {data.operation_revenue.length ? (
            <ul className="mt-3 divide-y divide-[#202838]">
              {data.operation_revenue.map((operation) => (
                <li
                  className="flex flex-wrap items-center justify-between gap-2 py-3"
                  key={operation.operation_name}
                >
                  <div>
                    <p className="text-sm text-[#e6eaf2]">
                      {operation.operation_name}
                    </p>
                    <p className="mt-1 text-[11px] text-[#78839b]">
                      {operation.sale_count} venda(s) · Bruto{" "}
                      {formatMoney(operation.gross_amount)}
                    </p>
                  </div>
                  <strong className="text-sm text-[#76c8a0]">
                    Líquido {formatMoney(operation.net_amount)}
                  </strong>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[#78839b]">
              As vendas aprovadas serão agrupadas por operação aqui.
            </p>
          )}
        </article>
        <article aria-live="polite" className="dashboard-card rounded-xl p-5">
          <h2 className="text-base font-semibold text-[#eef1f8]">
            Feed de vendas ao vivo
          </h2>
          {data.transactions.some((item) => item.kind === "sale") ? (
            <ul className="mt-3 divide-y divide-[#202838]">
              {data.transactions
                .filter((item) => item.kind === "sale")
                .slice(0, 10)
                .map((item) => (
                  <li
                    className="flex items-center justify-between gap-3 py-2.5"
                    key={item.id}
                  >
                    <div className="min-w-0">
                      <p className="truncate text-xs font-medium text-[#e6eaf2]">
                        {item.description}
                      </p>
                      <p className="mt-1 text-[10px] text-[#78839b]">
                        {formatDateTime(item.occurred_at)}
                      </p>
                    </div>
                    <strong className="shrink-0 text-xs text-[#76c8a0]">
                      +{formatMoney(item.amount)}
                    </strong>
                  </li>
                ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-[#78839b]">
              Aguardando vendas aprovadas.
            </p>
          )}
          {soundError && (
            <p className="mt-2 text-[11px] text-[#f2d48a]">{soundError}</p>
          )}
        </article>
      </section>

      <section className="dashboard-card rounded-xl p-5">
        <h2 className="text-base font-semibold text-[#eef1f8]">
          Movimentações · 100 mais recentes
        </h2>
        <p className="mt-1 text-xs text-[#78839b]">
          Entradas exibidas pelo valor líquido da operação; a venda bruta fica no resumo.
        </p>
        {data.transactions.length ? (
          <div className="mt-3 overflow-x-auto">
            <table className="w-full min-w-[620px] text-left text-sm">
              <thead className="text-[11px] uppercase tracking-wide text-[#78839b]">
                <tr>
                  <th className="py-2 pr-3 font-medium">Data e hora</th>
                  <th className="py-2 pr-3 font-medium">Movimentação</th>
                  <th className="py-2 pr-3 text-right font-medium">Valor</th>
                  <th className="py-2 text-right font-medium">Tipo</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#202838]">
                {data.transactions.map((item) => (
                  <tr key={item.id}>
                    <td className="py-3 pr-3 text-xs text-[#94a3b8]">
                      {formatDateTime(item.occurred_at)}
                    </td>
                    <td className="py-3 pr-3 text-[#e6eaf2]">{item.description}</td>
                    <td
                      className={`py-3 pr-3 text-right font-medium ${
                        item.direction === "inflow" ? "text-[#76c8a0]" : "text-[#f1a3ad]"
                      }`}
                    >
                      {item.direction === "inflow" ? "+" : "−"}
                      {formatMoney(item.amount)}
                    </td>
                    <td className="py-3 text-right text-xs text-[#94a3b8]">
                      {item.kind === "sale"
                        ? "Entrada"
                        : item.kind === "withdrawal"
                          ? "Saque"
                          : "Colaborador"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="mt-3 text-sm text-[#78839b]">
            As vendas Smokepay e as saídas registradas aparecerão aqui.
          </p>
        )}
      </section>
    </div>
  );
}
