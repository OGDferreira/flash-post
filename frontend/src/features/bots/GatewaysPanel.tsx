import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, CreditCard, ShieldCheck } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { CopyField } from "@/components/ui/CopyField";
import { ApiError, apiRequest } from "@/services/api";

type GatewayId = "smokepay" | "snakepay";
type Gateway = { id: GatewayId; name: string; available: boolean; fee: string; description: string };
type GatewayState = {
  current: GatewayId;
  snakepay_recipient_id: string | null;
  is_admin: boolean;
  needs_recipient: boolean;
  gateways: Gateway[];
  admin?: { snakepay_key_set: boolean; snakepay_secret_set: boolean; snakepay_enabled: boolean; snakepay_webhook_url: string };
};

const KEY = ["payment-gateways"];
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível salvar. Tente de novo.");

/** Brand marks drawn here (no third-party files): SmokePay's smoke wave, SnakePay's snake S. */
export function GatewayLogo({ id, className = "size-12" }: { id: GatewayId; className?: string }) {
  if (id === "snakepay") {
    return (
      <svg aria-hidden="true" className={className} viewBox="0 0 48 48">
        <rect fill="#0c120c" height="48" rx="12" width="48" />
        <rect fill="none" height="46" rx="11" stroke="#7cf05c" strokeOpacity=".35" width="46" x="1" y="1" />
        <path d="M33 13c-3-2.4-9.5-3-13 0s-1.5 7.5 3 9 9.5 3 8 8-9.5 5-13.5 2" fill="none" stroke="#7cf05c" strokeLinecap="round" strokeWidth="4.5" />
        <circle cx="32.6" cy="12.6" fill="#0c120c" r="1.1" />
      </svg>
    );
  }
  return (
    <svg aria-hidden="true" className={className} viewBox="0 0 48 48">
      <defs>
        <linearGradient id="smoke-g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#3b82f6" />
          <stop offset="1" stopColor="#14b8a6" />
        </linearGradient>
      </defs>
      <rect fill="url(#smoke-g)" height="48" rx="12" width="48" />
      <path d="M12 30c4-6 8 2 12-4s8 2 12-4" fill="none" stroke="#fff" strokeLinecap="round" strokeWidth="3.5" />
      <path d="M14 20c3-4 6 1 9-3" fill="none" opacity=".6" stroke="#fff" strokeLinecap="round" strokeWidth="3" />
    </svg>
  );
}

export function GatewaysPanel() {
  const queryClient = useQueryClient();
  const state = useQuery({ queryKey: KEY, queryFn: () => apiRequest<GatewayState>("/api/payment-gateways") });
  const [picked, setPicked] = useState<GatewayId>("smokepay");
  const [recipient, setRecipient] = useState("");
  useEffect(() => {
    if (!state.data) return;
    setPicked(state.data.current);
    setRecipient(state.data.snakepay_recipient_id ?? "");
  }, [state.data]);

  const save = useMutation({
    mutationFn: () =>
      apiRequest<GatewayState>("/api/payment-gateways", {
        method: "PUT",
        body: { gateway: picked, snakepay_recipient_id: recipient.trim() || null },
      }),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });
  const release = useMutation({
    mutationFn: (enabled: boolean) => apiRequest("/api/payment-gateways/snakepay/enabled", { method: "PUT", body: { enabled } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  if (state.isLoading) return <LoadingState label="Carregando gateways" />;
  if (state.error || !state.data) return <ErrorState message={errorText(state.error)} onRetry={() => void state.refetch()} />;
  const data = state.data;
  const dirty = picked !== data.current || (recipient.trim() || null) !== (data.snakepay_recipient_id ?? null);
  const needsRecipient = picked === "snakepay" && data.needs_recipient;

  return (
    <section className="space-y-4">
      <div className="glass-panel p-4 sm:p-5">
        <div className="flex items-center gap-2">
          <CreditCard className="text-accent" size={18} />
          <h2 className="text-base font-semibold text-fg">Gateway de pagamento</h2>
        </div>
        <p className="mt-1 text-xs text-muted">Escolha por onde os Pix dos seus robôs são gerados. Vale para todos os seus bots.</p>

        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          {data.gateways.map((gateway) => {
            const active = picked === gateway.id;
            return (
              <button
                aria-pressed={active}
                className={`relative flex items-start gap-3 rounded-2xl border p-4 text-left transition ${
                  active ? "border-accent ring-2 ring-accent/40" : "border-line-soft hover:border-accent/60"
                } ${gateway.available ? "" : "cursor-not-allowed opacity-50"}`}
                disabled={!gateway.available}
                key={gateway.id}
                onClick={() => setPicked(gateway.id)}
                type="button"
              >
                <GatewayLogo id={gateway.id} />
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2 text-sm font-semibold text-fg">
                    {gateway.name}
                    {data.current === gateway.id && <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-semibold text-success">em uso</span>}
                  </span>
                  <span className="mt-0.5 block text-xs text-muted">{gateway.description}</span>
                  <span className="mt-1 block text-[11px] text-fg-2">{gateway.available ? gateway.fee : "Ainda não liberado pelo administrador"}</span>
                </span>
                {active && <span className="absolute right-3 top-3 grid size-5 place-items-center rounded-full bg-brand text-white"><Check size={12} /></span>}
              </button>
            );
          })}
        </div>

        {picked === "snakepay" && (
          <div className="mt-4 rounded-xl border border-line-soft bg-surface-inset p-3">
            <label className="block text-sm font-medium text-fg" htmlFor="snakepay-recipient">
              ID do recebedor SnakePay {data.needs_recipient ? "" : "(opcional para a conta principal)"}
            </label>
            <input
              autoComplete="off"
              className="field mt-2 font-mono text-xs"
              id="snakepay-recipient"
              onChange={(event) => setRecipient(event.target.value)}
              placeholder="ex.: 3f2a9c1e-7b4d-4e2a-9c1e-7b4d4e2a9c1e"
              spellCheck={false}
              value={recipient}
            />
            <p className="mt-2 text-[11px] leading-5 text-muted">
              Na SnakePay, abra <b className="text-fg-2">Conta → Split</b> e copie o identificador da sua conta. Cada venda cai na conta da plataforma e
              a SnakePay repassa na hora a sua parte para essa conta (taxa da SnakePay: 3% + R$ 0,25 por venda). Se você é sócio, quem te convidou
              também precisa cadastrar o ID dele; até lá, suas vendas seguem pela SmokePay.
            </p>
          </div>
        )}

        {save.error && <p className="mt-3 text-xs text-danger">{errorText(save.error)}</p>}
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            className="btn-primary"
            disabled={!dirty || save.isPending || (needsRecipient && !recipient.trim())}
            onClick={() => save.mutate()}
            type="button"
          >
            {save.isPending ? "Salvando…" : "Salvar gateway"}
          </button>
          {save.isSuccess && !dirty && <span className="flex items-center gap-1 text-xs text-success"><Check size={14} /> Salvo</span>}
        </div>
      </div>

      {data.admin && (
        <div className="glass-panel p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <ShieldCheck className="text-accent" size={18} />
            <h2 className="text-base font-semibold text-fg">Integração SnakePay (administrador)</h2>
          </div>
          <ul className="mt-3 space-y-1.5 text-xs">
            {[
              ["Chave da API (SNAKEPAY_API_KEY no Render)", data.admin.snakepay_key_set],
              ["Segredo do webhook (SNAKEPAY_WEBHOOK_SECRET no Render)", data.admin.snakepay_secret_set],
            ].map(([label, ok]) => (
              <li className="flex items-center gap-2" key={String(label)}>
                {ok ? <Check className="text-success" size={14} /> : <CircleAlert className="text-warning" size={14} />}
                <span className={ok ? "text-fg-2" : "text-warning"}>{label}: {ok ? "configurado" : "falta configurar"}</span>
              </li>
            ))}
          </ul>
          <div className="mt-3">
            <CopyField hint="Cole em SnakePay → Desenvolvedor → URL do webhook da sua plataforma." label="URL do webhook" value={data.admin.snakepay_webhook_url} />
          </div>
          {release.error && <p className="mt-3 text-xs text-danger">{errorText(release.error)}</p>}
          <label className="mt-4 flex cursor-pointer items-center justify-between gap-4 border-t border-line-soft pt-4">
            <span>
              <span className="block text-sm font-medium text-fg-2">Liberar SnakePay para os usuários</span>
              <span className="block text-xs text-muted">Com a opção ligada, cada operação pode escolher a SnakePay nesta aba.</span>
            </span>
            <input
              checked={data.admin.snakepay_enabled}
              className="size-5 accent-[var(--brand-c)]"
              disabled={release.isPending}
              onChange={(event) => release.mutate(event.target.checked)}
              type="checkbox"
            />
          </label>
        </div>
      )}
    </section>
  );
}
