import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, LoaderCircle, TicketPercent } from "lucide-react";

import { Modal } from "@/components/ui/Modal";
import { useAuth } from "@/features/auth/AuthProvider";
import { ApiError, apiRequest } from "@/services/api";

type Plan = { id: string; code: string; name: string; price: string; period_days: number };
type Coupon = { percent: string; expires_at: string | null };
type Access = {
  required: boolean;
  active: boolean;
  status: string;
  until: string | null;
  in_trial: boolean;
  plans: Plan[];
  coupon: Coupon | null;
};
type Charge = {
  id: string; status: string; amount: string; pix_copy_paste: string | null; due_at: string | null;
  discount_percent?: string | null;
};
type CancelIntent = { offered: boolean; coupon: Coupon | null };

const brl = (value: string | number) => Number(value).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

/** Plan price with the retention coupon applied (floor of R$ 1,00), for display only. */
function discounted(price: string, percent: string): number {
  const base = Number(price);
  const off = (base * Number(percent)) / 100;
  return Math.max(1, Math.round((base - off) * 100) / 100);
}

/** Paywall for operation owners whose trial/paid window has ended. Blocking: the
 *  app isn't usable until a plan is paid (PIX) or a liberation code is redeemed.
 *  Collaborators, partners without their own operation, and the Super Admin are
 *  never gated (the API reports required=false for them). */
export function SubscriptionGate() {
  const { user } = useAuth();
  const cache = useQueryClient();
  const [charge, setCharge] = useState<Charge | null>(null);
  const [code, setCode] = useState("");
  // Let the CPF completion gate go first; only paywall once the profile is complete.
  const enabled = Boolean(user && !user.impersonator_name && user.profile_complete !== false);

  const access = useQuery({
    queryKey: ["subscription", "me"],
    queryFn: () => apiRequest<Access>("/api/subscription/me"),
    enabled,
    staleTime: 30_000,
  });

  const checkout = useMutation({
    mutationFn: (planId: string) =>
      apiRequest<Charge>("/api/subscription/checkout", { method: "POST", body: { plan_id: planId } }),
    onSuccess: (data) => setCharge(data),
  });

  const redeem = useMutation({
    mutationFn: () => apiRequest<Access>("/api/subscription/redeem", { method: "POST", body: { code: code.trim() } }),
    onSuccess: (data) => {
      cache.setQueryData(["subscription", "me"], data);
      cache.invalidateQueries({ queryKey: ["auth", "me"] });
    },
  });

  // Anti-churn: the owner signals they want to cancel; the API offers a retention coupon
  // (when the Super Admin turned it on) that auto-applies at checkout.
  const cancelIntent = useMutation({
    mutationFn: () => apiRequest<CancelIntent>("/api/subscription/cancel-intent", { method: "POST" }),
    onSuccess: (data) => {
      if (data.coupon) {
        cache.setQueryData(["subscription", "me"], (prev: Access | undefined) =>
          prev ? { ...prev, coupon: data.coupon } : prev,
        );
      }
    },
  });

  // Poll the charge while it's pending; when it clears, drop the paywall.
  const pending = charge && charge.status === "pending";
  const poll = useQuery({
    queryKey: ["subscription", "charge", charge?.id],
    queryFn: () => apiRequest<Charge>(`/api/subscription/charge/${charge!.id}`),
    enabled: Boolean(pending),
    refetchInterval: 4000,
  });
  useEffect(() => {
    if (poll.data?.status === "paid") {
      setCharge(null);
      cache.invalidateQueries({ queryKey: ["subscription", "me"] });
      cache.invalidateQueries({ queryKey: ["auth", "me"] });
    }
  }, [poll.data?.status, cache]);

  if (!enabled || !access.data || !access.data.required || access.data.active) return null;

  const redeemError = redeem.error instanceof ApiError ? redeem.error.message : null;
  const checkoutError = checkout.error instanceof ApiError ? checkout.error.message : null;
  const coupon = access.data.coupon;
  const couponUntil = coupon?.expires_at
    ? new Date(coupon.expires_at).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" })
    : null;

  return (
    <Modal
      open
      title="Assinatura necessária"
      description="Seu acesso venceu. Escolha um plano e pague via PIX para continuar usando a plataforma."
      onClose={() => {}}
      wide
    >
      {charge?.pix_copy_paste ? (
        <div className="space-y-3">
          <p className="text-sm text-fg-2">
            Pague o PIX de <strong className="text-fg">{brl(charge.amount)}</strong>
            {charge.discount_percent ? ` (com ${Math.round(Number(charge.discount_percent))}% de desconto)` : ""} abaixo.
            A liberação é automática assim que o pagamento cair.
          </p>
          <div className="rounded-lg border border-line bg-surface-inset p-3">
            <p className="break-all font-mono text-xs text-fg-2">{charge.pix_copy_paste}</p>
          </div>
          <button
            type="button"
            onClick={() => navigator.clipboard?.writeText(charge.pix_copy_paste ?? "")}
            className="flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-line bg-surface px-4 text-sm font-medium text-fg-2 hover:text-fg"
          >
            <Copy size={15} /> Copiar código PIX
          </button>
          <p className="flex items-center justify-center gap-2 text-xs text-muted">
            <LoaderCircle size={13} className="animate-spin" /> Aguardando o pagamento...
          </p>
          <button type="button" onClick={() => setCharge(null)} className="w-full text-xs text-muted hover:text-fg-2">
            Escolher outro plano
          </button>
        </div>
      ) : (
        <div className="space-y-3">
          {coupon && (
            <div className="flex items-start gap-2.5 rounded-lg border border-brand/40 bg-brand/10 px-4 py-3">
              <TicketPercent size={18} className="mt-0.5 shrink-0 text-brand" />
              <div>
                <p className="text-sm font-semibold text-fg">
                  Desconto de {Math.round(Number(coupon.percent))}% pra você continuar
                </p>
                <p className="text-xs text-muted">
                  Já aplicado no PIX de qualquer plano abaixo{couponUntil ? ` · válido até ${couponUntil}` : ""}.
                </p>
              </div>
            </div>
          )}
          <div className="grid gap-2">
            {access.data.plans.map((plan) => (
              <button
                key={plan.id}
                type="button"
                disabled={checkout.isPending}
                onClick={() => checkout.mutate(plan.id)}
                className="flex items-center justify-between rounded-lg border border-line bg-surface-inset px-4 py-3 text-left transition hover:border-brand disabled:opacity-60"
              >
                <span>
                  <span className="block text-sm font-semibold text-fg">{plan.name}</span>
                  <span className="block text-xs text-muted">a cada {plan.period_days} dias</span>
                </span>
                {coupon ? (
                  <span className="text-right">
                    <span className="block text-xs text-muted line-through">{brl(plan.price)}</span>
                    <span className="block text-sm font-semibold text-brand">
                      {brl(discounted(plan.price, coupon.percent))}
                    </span>
                  </span>
                ) : (
                  <span className="text-sm font-semibold text-brand">{brl(plan.price)}</span>
                )}
              </button>
            ))}
            {access.data.plans.length === 0 && (
              <p className="text-sm text-muted">Nenhum plano disponível no momento. Fale com o suporte.</p>
            )}
          </div>
          {!coupon && (
            <button
              type="button"
              disabled={cancelIntent.isPending}
              onClick={() => cancelIntent.mutate()}
              className="w-full text-xs text-muted underline-offset-2 hover:text-fg-2 hover:underline disabled:opacity-60"
            >
              {cancelIntent.isPending ? "..." : "Pensando em não continuar? Veja uma oferta antes de sair"}
            </button>
          )}
          {checkoutError && <p className="text-xs text-danger" role="alert">{checkoutError}</p>}

          <div className="border-t border-line-soft pt-3">
            <label htmlFor="liberation-code" className="mb-1.5 block text-xs font-medium text-muted">
              Tem um código de liberação?
            </label>
            <div className="flex gap-2">
              <input
                id="liberation-code"
                value={code}
                onChange={(event) => setCode(event.target.value.toUpperCase())}
                placeholder="CÓDIGO"
                maxLength={32}
                className="h-10 flex-1 rounded-lg border border-line bg-surface-inset px-3 text-sm uppercase tracking-widest text-fg outline-none focus:border-brand"
              />
              <button
                type="button"
                disabled={!code.trim() || redeem.isPending}
                onClick={() => redeem.mutate()}
                className="h-10 rounded-lg bg-brand px-4 text-sm font-semibold text-white disabled:opacity-60"
              >
                {redeem.isPending ? "..." : "Aplicar"}
              </button>
            </div>
            {redeemError && <p className="mt-1.5 text-xs text-danger" role="alert">{redeemError}</p>}
          </div>
        </div>
      )}
    </Modal>
  );
}
