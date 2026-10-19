import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, CircleAlert, Clock3, CreditCard, ShieldCheck } from "lucide-react";

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
  // funnels shared by a chief that this operation's bots run: they follow the chief's gateway
  shared_flows: { name: string; gateway: GatewayId }[];
  partners_without_shop_id: string[];
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
  const [info, setInfo] = useState<GatewayId | null>(null); // which card's "!" (fees) is open
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
          <div
            className={`mt-3 flex flex-wrap items-center justify-between gap-3 rounded-xl border p-3 ${
              data.admin.snakepay_enabled ? "border-success/40 bg-success/10" : "border-accent/50 bg-brand/10"
            }`}
          >
            <span className="min-w-0">
              <span className="flex items-center gap-2 text-sm font-semibold text-fg">
                SnakePay para os usuários:
                <span className={`rounded-full px-2 py-0.5 text-[11px] ${data.admin.snakepay_enabled ? "bg-success/20 text-success" : "bg-warning/20 text-warning"}`}>
                  {data.admin.snakepay_enabled ? "LIGADA" : "DESLIGADA"}
                </span>
              </span>
              <span className="mt-0.5 block text-xs text-muted">
                {data.admin.snakepay_enabled
                  ? "Cada operação já pode escolher a SnakePay no cartão acima."
                  : "Ligue para que a SnakePay possa ser escolhida (por você e pelos usuários)."}
              </span>
            </span>
            <button
              className={data.admin.snakepay_enabled ? "btn-secondary" : "btn-primary"}
              disabled={release.isPending || (!data.admin.snakepay_enabled && !(data.admin.snakepay_key_set && data.admin.snakepay_secret_set))}
              onClick={() => release.mutate(!data.admin?.snakepay_enabled)}
              type="button"
            >
              {release.isPending ? "Salvando…" : data.admin.snakepay_enabled ? "Desligar" : "Liberar SnakePay"}
            </button>
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
        </div>
  );
  const nameOf = (id: GatewayId) => data.gateways.find((g) => g.id === id)?.name ?? id;
  const sharedSnake = data.shared_flows.filter((flow) => flow.gateway === "snakepay");
  const needsRecipient = picked === "snakepay" && data.needs_recipient;
  const missingShopId = sharedSnake.length > 0 && !(data.snakepay_recipient_id ?? "").trim();

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
        {data.shared_flows.length > 0 && (
          <div className={`mt-3 rounded-xl border p-3 text-xs leading-5 ${missingShopId ? "border-warning/50 bg-warning/10" : "border-line-soft bg-surface-inset"}`}>
            <p className="flex items-center gap-2 font-semibold text-fg">
              <CircleAlert className={missingShopId ? "text-warning" : "text-accent"} size={15} /> Funis compartilhados com você
            </p>
            <p className="mt-1 text-muted">
              Estes funis usam o gateway que quem compartilhou escolheu:{" "}
              {data.shared_flows.map((flow) => `${flow.name} (${nameOf(flow.gateway)})`).join(", ")}.
            </p>
            {missingShopId && (
              <p className="mt-1 font-medium text-warning">
                Cadastre seu ShopID da SnakePay abaixo para receber sua parte por lá. Enquanto não cadastrar, essas vendas continuam pela SmokePay.
              </p>
            )}
          </div>
        )}
        {data.partners_without_shop_id.length > 0 && (
          <div className="mt-3 rounded-xl border border-warning/50 bg-warning/10 p-3 text-xs leading-5">
            <p className="flex items-center gap-2 font-semibold text-fg">
              <CircleAlert className="text-warning" size={15} /> Sócios sem ShopID da SnakePay
            </p>
            <p className="mt-1 text-muted">
              {data.partners_without_shop_id.join(", ")} {data.partners_without_shop_id.length > 1 ? "rodam" : "roda"} seus funis com SnakePay, mas ainda não
              cadastrou o ShopID. Sem ele a SnakePay não tem para onde mandar a parte do sócio, então essas vendas (e a sua comissão) seguem pela SmokePay até o
              ShopID ser cadastrado na aba Gateways do sócio.
            </p>
          </div>
        )}

        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
          {data.gateways.map((gateway) => {
            const active = picked === gateway.id;
            return (
              <div className="relative" key={gateway.id}>
                <button
                  aria-pressed={active}
                  className={`flex aspect-square w-full flex-col items-center justify-center gap-2 rounded-2xl border p-3 text-center transition ${
                    active ? "border-accent bg-brand/10 ring-2 ring-accent/40" : "border-line-soft hover:border-accent/60"
                  } ${gateway.available ? "" : "cursor-not-allowed opacity-50"}`}
                  disabled={!gateway.available}
                  onClick={() => setPicked(gateway.id)}
                  type="button"
                >
                  <GatewayLogo className="size-14 sm:size-16" id={gateway.id} />
                  <span className="text-sm font-semibold text-fg">{gateway.name}</span>
                  {data.current === gateway.id ? (
                    <span className="rounded-full bg-success/15 px-2 py-0.5 text-[10px] font-semibold text-success">em uso</span>
                  ) : !gateway.available ? (
                    <span className="text-[10px] text-muted">Não liberado</span>
                  ) : null}
                  {active && <span className="absolute left-2.5 top-2.5 grid size-5 place-items-center rounded-full bg-brand text-white"><Check size={12} /></span>}
                </button>
                <button
                  aria-expanded={info === gateway.id}
                  aria-label={`Taxas e detalhes da ${gateway.name}`}
                  className="absolute right-2 top-2 grid size-7 place-items-center rounded-full border border-line-soft bg-surface-inset text-xs font-bold text-muted transition hover:border-accent hover:text-accent"
                  onClick={() => setInfo(info === gateway.id ? null : gateway.id)}
                  type="button"
                >
                  !
                </button>
                {info === gateway.id && (
                  <div className="absolute inset-x-1 top-11 z-20 rounded-xl border border-line bg-[var(--nm-bg)] p-3 text-left text-[11px] leading-5 shadow-2xl" role="dialog">
                    <p className="font-semibold text-fg">{gateway.name}</p>
                    <p className="text-muted">{gateway.description}</p>
                    <p className="mt-1 text-fg-2">{gateway.fee}</p>
                  </div>
                )}
              </div>
            );
          })}
          {["Novo gateway", "Novo gateway"].map((name, index) => (
            <div
              className="flex aspect-square flex-col items-center justify-center gap-2 rounded-2xl border border-dashed border-line-soft p-3 text-center opacity-70"
              key={`soon-${index}`}
            >
              <span className="grid size-14 place-items-center rounded-xl border border-dashed border-line-soft text-muted sm:size-16">
                <Clock3 size={22} />
              </span>
              <span className="text-sm font-semibold text-fg-2">{name}</span>
              <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-semibold text-warning">Aguardando liberação</span>
            </div>
          ))}
        </div>

        {(picked === "snakepay" || sharedSnake.length > 0) && (
          <div className="mt-4 rounded-xl border border-line-soft bg-surface-inset p-3">
            <label className="block text-sm font-medium text-fg" htmlFor="snakepay-recipient">
              Seu ShopID da SnakePay {data.needs_recipient ? "" : "(opcional para a conta principal)"}
            </label>
            <input
              autoComplete="off"
              className="field mt-2 font-mono text-xs"
              id="snakepay-recipient"
              onChange={(event) => setRecipient(event.target.value)}
              placeholder="ex.: snakepay_6fde14d647ba4acbb45855490d22f435"
              spellCheck={false}
              value={recipient}
            />
            <p className="mt-2 text-[11px] leading-5 text-muted">
              Na SnakePay, abra <b className="text-fg-2">Split da conta</b> e copie o <b className="text-fg-2">Seu ShopID</b>. Cada venda cai na conta da plataforma e
              a SnakePay repassa na hora a sua parte para essa conta (taxa da SnakePay: 3% + R$ 0,25 por venda). Num funil compartilhado vale o gateway
              escolhido por quem compartilhou; com SnakePay, o sócio precisa ter o ShopID cadastrado, senão a venda segue pela SmokePay.
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
