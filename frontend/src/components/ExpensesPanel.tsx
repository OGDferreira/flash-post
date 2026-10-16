import { useState, type FormEvent } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Receipt, Trash2 } from "lucide-react";

import { useFinanceMonth } from "@/components/MonthResultCards";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";

const money = (value: string | number) =>
  new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value));

const day = (value: string) => new Intl.DateTimeFormat("pt-BR", { dateStyle: "short" }).format(new Date(value));

/** Simple expense log (amount + what it was for); every entry lowers the month's profit. */
export function ExpensesPanel() {
  const queryClient = useQueryClient();
  const month = useFinanceMonth();
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["finance", "month"] });

  const create = useMutation({
    mutationFn: () =>
      apiRequest("/api/finance/expenses", {
        method: "POST",
        body: { amount: Number(amount.replace(",", ".")).toFixed(2), description: description.trim() },
      }),
    onSuccess: () => {
      setAmount("");
      setDescription("");
      refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest(`/api/finance/expenses/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });

  const valid = Number(amount.replace(",", ".")) > 0 && description.trim().length > 0;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (valid) create.mutate();
  };
  const expenses = month.data?.expenses ?? [];
  const error = create.error ?? remove.error;

  return (
    <section aria-label="Outros gastos" className="dashboard-card space-y-4 rounded-xl p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="font-medium text-fg">Outros gastos</h2>
          <p className="mt-1 text-xs text-muted">Anúncios, chips, ferramentas… tudo entra no cálculo do lucro do mês.</p>
        </div>
        {month.data && (
          <p className="shrink-0 text-right text-xs text-muted">
            Total do mês
            <span className="block text-lg font-semibold text-danger">{money(month.data.expenses_total)}</span>
          </p>
        )}
      </div>
      <form className="grid gap-2 sm:grid-cols-[140px_1fr_auto]" onSubmit={submit}>
        <input
          aria-label="Valor do gasto"
          className="field"
          inputMode="decimal"
          placeholder="R$ 0,00"
          value={amount}
          onChange={(event) => setAmount(event.target.value.replace(/[^\d.,]/g, ""))}
        />
        <input
          aria-label="No que foi gasto"
          className="field"
          maxLength={160}
          placeholder="No que foi gasto (ex.: anúncios)"
          value={description}
          onChange={(event) => setDescription(event.target.value)}
        />
        <button className="btn-primary" disabled={!valid || create.isPending} type="submit">
          {create.isPending ? "Registrando..." : "Registrar gasto"}
        </button>
      </form>
      {error && (
        <p className="text-sm text-danger" role="alert">
          {error instanceof ApiError ? error.message : "Não foi possível salvar o gasto."}
        </p>
      )}
      {expenses.length === 0 ? (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Receipt size={15} /> Nenhum gasto registrado neste mês.
        </p>
      ) : (
        <ul className="divide-y divide-line-soft">
          {expenses.map((item) => (
            <li className="flex items-center gap-3 py-2 text-sm" key={item.id}>
              <span className="w-16 shrink-0 text-xs text-muted">{day(item.spent_at)}</span>
              <span className="min-w-0 flex-1 truncate text-fg">{item.description}</span>
              <span className="shrink-0 font-medium text-danger">− {money(item.amount)}</span>
              <button
                aria-label={`Excluir gasto ${item.description}`}
                className="btn-ghost !min-h-8 !px-2"
                disabled={remove.isPending}
                onClick={async () => {
                  if (await confirmAction(`Excluir o gasto “${item.description}” de ${money(item.amount)}?`)) remove.mutate(item.id);
                }}
                type="button"
              >
                <Trash2 size={14} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
