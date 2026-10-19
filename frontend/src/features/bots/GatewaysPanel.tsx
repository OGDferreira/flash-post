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
  flows: { id: string; name: string; gateway: GatewayId | null }[];
  gateways: Gateway[];
  admin?: { snakepay_key_set: boolean; snakepay_secret_set: boolean; snakepay_enabled: boolean; snakepay_webhook_url: string };
};

const KEY = ["payment-gateways"];
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível salvar. Tente de novo.");

/** Official gateway symbols on a dark tile (the SmokePay mark is white, so it needs it in light mode too). */
export function GatewayLogo({ id, className = "size-12" }: { id: GatewayId; className?: string }) {
  return (
    <span className={`grid shrink-0 place-items-center rounded-xl border border-white/10 bg-[#0d1017] p-1.5 ${className}`}>
      <img alt="" className="h-full w-full object-contain" draggable={false} src={`/gateways/${id}.png`} />
    </span>
  );
}

export function GatewaysPanel() {
  const queryClient = useQueryClient();
  const state = useQuery({ queryKey: KEY, queryFn: () => apiRequest<GatewayState>("/api/payment-gateways") });
  const [picked, setPicked] = useState<GatewayId>("smokepay");
  const [recipient, setRecipient] = useState("");
  const [scope, setScope] = useState<"all" | "flows">("all");
  useEffect(() => {
    if (!state.data) return;
    setPicked(state.data.current);
    setRecipient(state.data.snakepay_recipient_id ?? "");
    if (state.data.flows.some((flow) => flow.gateway)) setScope("flows");
  }, [state.data]);

  const save = useMutation({
    mutationFn: () =>
      apiRequest<GatewayState>("/api/payment-gateways", {
        method: "PUT",
        body: { gateway: picked, snakepay_recipient_id: recipient.trim() || null, apply_to_all: scope === "all" },
      }),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });
  const perFlow = useMutation({
    mutationFn: ({ id, gateway }: { id: string; gateway: GatewayId | null }) =>
      apiRequest<GatewayState>(`/api/payment-gateways/flows/${id}`, { method: "PUT", body: { gateway } }),
    onSuccess: (data) => queryClient.setQueryData(KEY, data),
  });
  const release = useMutation({
    mutationFn: (enabled: boolean) => apiRequest("/api/payment-gateways/snakepay/enabled", { method: "PUT", body: { enabled } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: KEY }),
  });

  if (state.isLoading) return <LoadingState label="Carregando gateways" />;
  if (state.error || !state.data) return <ErrorState message={errorText(state.error)} onRetry={() => void state.refetch()} />;
  const data = state.data;
  const overrides = data.flows.some((flow) => flow.gateway);
  const dirty =
    picked !== data.current ||
    (recipient.trim() || null) !== (data.snakepay_recipient_id ?? null) ||
    (scope === "all" && overrides);
  const adminCard = data.admin && (
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
  );
  const nameOf = (id: GatewayId) => data.gateways.find((g) => g.id === id)?.name ?? id;
  const needsRecipient = picked === "snakepay" && data.needs_recipient;

  return (
    <section className="space-y-4">
      {/* While SnakePay is off the Super Admin sees the release switch first. */}
      {data.admin && !data.admin.snakepay_enabled && adminCard}
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

        <div className="mt-4 border-t border-line-soft pt-4">
          <p className="text-sm font-medium text-fg">Usar em</p>
          <div className="mt-2 inline-flex rounded-full border border-line-soft p-1" role="radiogroup">
            {([["all", "Todos os fluxos"], ["flows", "Fluxos específicos"]] as const).map(([value, label]) => (
              <button
                aria-checked={scope === value}
                className={`min-h-9 rounded-full px-4 text-xs font-medium transition ${scope === value ? "bg-brand text-white" : "text-muted hover:text-fg"}`}
                key={value}
                onClick={() => setScope(value)}
                role="radio"
                type="button"
              >
                {label}
              </button>
            ))}
          </div>
          {scope === "all" ? (
            <p className="mt-2 text-[11px] text-muted">
              Todos os seus fluxos usam o gateway escolhido acima{overrides ? " (salve para remover as escolhas por fluxo)" : ""}.
            </p>
          ) : data.flows.length === 0 ? (
            <p className="mt-2 text-[11px] text-muted">Você ainda não tem fluxos.</p>
          ) : (
            <ul className="mt-3 divide-y divide-[color:var(--color-line-soft)] rounded-xl border border-line-soft">
              {data.flows.map((flow) => (
                <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2" key={flow.id}>
                  <span className="min-w-0 truncate text-sm text-fg">{flow.name}</span>
                  <select
                    aria-label={`Gateway do fluxo ${flow.name}`}
                    className="field !min-h-9 !w-auto text-xs"
                    disabled={perFlow.isPending}
                    onChange={(event) => perFlow.mutate({ id: flow.id, gateway: (event.target.value || null) as GatewayId | null })}
                    value={flow.gateway ?? ""}
                  >
                    <option value="">Padrão ({nameOf(data.current)})</option>
                    {data.gateways.map((gateway) => (
                      <option disabled={!gateway.available} key={gateway.id} value={gateway.id}>{gateway.name}</option>
                    ))}
                  </select>
                </li>
              ))}
            </ul>
          )}
          {perFlow.error && <p className="mt-2 text-xs text-danger">{errorText(perFlow.error)}</p>}
        </div>

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

      {data.admin?.snakepay_enabled && adminCard}
    </section>
  );
}
