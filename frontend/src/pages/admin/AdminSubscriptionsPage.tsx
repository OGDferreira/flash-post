import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";

import { apiRequest } from "@/services/api";

type Plan = { id: string; code: string; name: string; price: string; period_days: number; sort_order: number; is_active: boolean };
type Code = { id: string; code: string; days: number; note: string | null; redeemed: boolean; redeemed_at: string | null; expires_at: string | null; created_at: string };

const brl = (value: string) => Number(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** Super Admin: set each plan's price and generate liberation codes (free access). */
export function AdminSubscriptionsPage() {
  const cache = useQueryClient();
  const plans = useQuery({ queryKey: ["admin", "sub-plans"], queryFn: () => apiRequest<{ plans: Plan[] }>("/api/subscription/admin/plans") });
  const codes = useQuery({ queryKey: ["admin", "sub-codes"], queryFn: () => apiRequest<{ codes: Code[] }>("/api/subscription/admin/codes") });

  return (
    <div className="space-y-4">
      <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">Assinaturas</h2>

      <section className="glass-panel p-4 sm:p-5">
        <h3 className="text-base font-semibold text-fg">Planos</h3>
        <p className="mt-1 text-sm text-muted">Defina o preço de cada plano. O usuário paga via PIX para liberar o acesso.</p>
        <div className="mt-3 space-y-2">
          {plans.data?.plans.map((plan) => <PlanRow key={plan.id} plan={plan} onSaved={() => cache.invalidateQueries({ queryKey: ["admin", "sub-plans"] })} />)}
          {plans.isLoading && <p className="text-sm text-muted">Carregando...</p>}
        </div>
      </section>

      <AntiChurnSection />

      <section className="glass-panel p-4 sm:p-5">
        <h3 className="text-base font-semibold text-fg">Códigos de liberação</h3>
        <p className="mt-1 text-sm text-muted">Gere um código que dá X dias de acesso grátis. Cada código vale uma vez.</p>
        <NewCode onCreated={() => cache.invalidateQueries({ queryKey: ["admin", "sub-codes"] })} />
        <div className="mt-3 divide-y divide-line-soft">
          {codes.data?.codes.map((code) => (
            <div key={code.id} className="flex items-center justify-between py-2 text-sm">
              <span className="font-mono font-semibold tracking-widest text-fg">{code.code}</span>
              <span className="text-muted">{code.days} dias{code.note ? ` · ${code.note}` : ""}</span>
              <span className={code.redeemed ? "text-muted" : "text-success"}>{code.redeemed ? "usado" : "disponível"}</span>
            </div>
          ))}
          {codes.data && codes.data.codes.length === 0 && <p className="py-2 text-sm text-muted">Nenhum código ainda.</p>}
        </div>
      </section>
    </div>
  );
}

function PlanRow({ plan, onSaved }: { plan: Plan; onSaved: () => void }) {
  const [price, setPrice] = useState(plan.price);
  const save = useMutation({
    mutationFn: () => apiRequest(`/api/subscription/admin/plans/${plan.id}`, { method: "PATCH", body: { price } }),
    onSuccess: onSaved,
  });
  return (
    <div className="flex items-center gap-3 rounded-lg border border-line bg-surface-inset px-3 py-2">
      <div className="flex-1">
        <span className="block text-sm font-semibold text-fg">{plan.name}</span>
        <span className="block text-xs text-muted">a cada {plan.period_days} dias · atual {brl(plan.price)}</span>
      </div>
      <div className="flex items-center gap-1 text-sm text-muted">R$</div>
      <input
        value={price}
        onChange={(event) => setPrice(event.target.value.replace(",", "."))}
        inputMode="decimal"
        className="h-9 w-24 rounded-lg border border-line bg-surface px-2 text-sm text-fg outline-none focus:border-brand"
      />
      <button
        type="button"
        disabled={save.isPending || price === plan.price}
        onClick={() => save.mutate()}
        className="h-9 rounded-lg bg-brand px-3 text-sm font-semibold text-white disabled:opacity-60"
      >
        {save.isPending ? <LoaderCircle size={15} className="animate-spin" /> : "Salvar"}
      </button>
    </div>
  );
}

type AntiChurn = { enabled: boolean; percent: string; valid_days: number };

/** Super Admin: the anti-churn coupon offered to an owner who signals they want to cancel. */
function AntiChurnSection() {
  const cache = useQueryClient();
  const config = useQuery({
    queryKey: ["admin", "anti-churn"],
    queryFn: () => apiRequest<AntiChurn>("/api/subscription/admin/anti-churn"),
  });
  const [enabled, setEnabled] = useState(false);
  const [percent, setPercent] = useState("20");
  const [validDays, setValidDays] = useState("7");
  const [ready, setReady] = useState(false);
  if (config.data && !ready) {
    setEnabled(config.data.enabled);
    setPercent(String(Math.round(Number(config.data.percent))));
    setValidDays(String(config.data.valid_days));
    setReady(true);
  }
  const save = useMutation({
    mutationFn: () =>
      apiRequest<AntiChurn>("/api/subscription/admin/anti-churn", {
        method: "PUT",
        body: { enabled, percent: Number(percent), valid_days: Number(validDays) },
      }),
    onSuccess: (data) => cache.setQueryData(["admin", "anti-churn"], data),
  });
  return (
    <section className="glass-panel p-4 sm:p-5">
      <h3 className="text-base font-semibold text-fg">Cupom de anti-churn</h3>
      <p className="mt-1 text-sm text-muted">
        Quando um assinante indica que quer cancelar, antes de bloquear o acesso a plataforma
        oferece um cupom de desconto. Se ele usar, a assinatura é renovada com o desconto.
      </p>
      <label className="mt-3 flex items-center gap-2 text-sm text-fg">
        <input type="checkbox" checked={enabled} onChange={(event) => setEnabled(event.target.checked)} className="size-4 accent-[var(--brand)]" />
        Ativar o cupom de anti-churn
      </label>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <label className="text-xs text-muted">
          Desconto (%)
          <input
            value={percent}
            onChange={(event) => setPercent(event.target.value.replace(/\D/g, ""))}
            inputMode="numeric"
            className="mt-1 block h-9 w-20 rounded-lg border border-line bg-surface-inset px-2 text-sm text-fg outline-none focus:border-brand"
          />
        </label>
        <label className="text-xs text-muted">
          Validade (dias)
          <input
            value={validDays}
            onChange={(event) => setValidDays(event.target.value.replace(/\D/g, ""))}
            inputMode="numeric"
            className="mt-1 block h-9 w-24 rounded-lg border border-line bg-surface-inset px-2 text-sm text-fg outline-none focus:border-brand"
          />
        </label>
        <button
          type="button"
          disabled={save.isPending || !Number(percent) || !Number(validDays)}
          onClick={() => save.mutate()}
          className="h-9 rounded-lg bg-brand px-4 text-sm font-semibold text-white disabled:opacity-60"
        >
          {save.isPending ? "..." : "Salvar"}
        </button>
      </div>
      <p className="mt-2 text-xs text-muted">Desconto de 1% a 90%, validade de 1 a 90 dias.</p>
    </section>
  );
}

function NewCode({ onCreated }: { onCreated: () => void }) {
  const [days, setDays] = useState("30");
  const [note, setNote] = useState("");
  const create = useMutation({
    mutationFn: () => apiRequest<{ code: string }>("/api/subscription/admin/codes", { method: "POST", body: { days: Number(days), note: note.trim() || null } }),
    onSuccess: () => {
      setNote("");
      onCreated();
    },
  });
  return (
    <div className="mt-3 flex flex-wrap items-end gap-2">
      <label className="text-xs text-muted">
        Dias
        <input value={days} onChange={(event) => setDays(event.target.value.replace(/\D/g, ""))} inputMode="numeric" className="mt-1 block h-9 w-20 rounded-lg border border-line bg-surface-inset px-2 text-sm text-fg outline-none focus:border-brand" />
      </label>
      <label className="flex-1 text-xs text-muted">
        Nota (opcional)
        <input value={note} onChange={(event) => setNote(event.target.value)} maxLength={160} placeholder="ex.: cortesia parceiro" className="mt-1 block h-9 w-full rounded-lg border border-line bg-surface-inset px-2 text-sm text-fg outline-none focus:border-brand" />
      </label>
      <button type="button" disabled={create.isPending || !Number(days)} onClick={() => create.mutate()} className="h-9 rounded-lg bg-brand px-4 text-sm font-semibold text-white disabled:opacity-60">
        {create.isPending ? "..." : "Gerar código"}
      </button>
    </div>
  );
}

export default AdminSubscriptionsPage;
