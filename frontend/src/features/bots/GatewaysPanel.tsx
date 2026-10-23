import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Check, CircleAlert, CreditCard, Inbox, KeyRound, Lock, Settings2, ShieldCheck } from "lucide-react";

import { ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { CopyField } from "@/components/ui/CopyField";
import { Modal } from "@/components/ui/Modal";
import { ApiError, apiRequest } from "@/services/api";

type GatewayId = "smokepay" | "snakepay";
type Gateway = { id: GatewayId; name: string; available: boolean; fee: string; description: string };
type PriorityStatus = "ativo" | "desligado" | "pausado" | "configurar" | "indisponivel";
type PriorityRow = { gateway: GatewayId; enabled: boolean; priority: number; flow_ids: string[] | null; status: PriorityStatus };
type GatewayState = {
  current: GatewayId;
  snakepay_recipient_id: string | null;
  snakepay_account_key_set: boolean;
  snakepay_account_secret_set: boolean;
  snakepay_cashout_secret_set?: boolean;
  snakepay_webhook_url: string;
  is_admin: boolean;
  needs_recipient: boolean;
  has_own_flow: boolean;
  flows: { id: string; name: string; gateway: GatewayId | null }[];
  priority: PriorityRow[];
  // funnels shared with this operation: they follow the rules of whoever shared them
  shared_flows: {
    name: string;
    gateway: GatewayId;
    set_by_owner: boolean;
    seller_percent: number | null;
    owner_percent: number | null;
    shop_id_ready: boolean;
  }[];
  partners_without_shop_id: string[];
  gateways: Gateway[];
  admin?: { snakepay_key_set: boolean; snakepay_secret_set: boolean; snakepay_enabled: boolean; snakepay_webhook_url: string };
};

const KEY = ["payment-gateways"];
const errorText = (error: unknown) => (error instanceof ApiError ? error.message : "Não foi possível salvar. Tente de novo.");
const STATUS: Record<PriorityStatus, { label: string; tone: "success" | "neutral" | "warning" | "danger" }> = {
  ativo: { label: "Ativo", tone: "success" },
  desligado: { label: "Desligado", tone: "neutral" },
  pausado: { label: "Pausado: recusou o ShopID há pouco", tone: "warning" },
  configurar: { label: "Falta configurar", tone: "warning" },
  indisponivel: { label: "Não liberado", tone: "neutral" },
};
const pct = (value: number | null) => (value === null ? "—" : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`);

/** Official gateway symbols on a dark tile (the SmokePay mark is white, so it needs it in light mode too). */
export function GatewayLogo({ id, className = "size-12" }: { id: GatewayId; className?: string }) {
  return (
    <span className={`grid shrink-0 place-items-center rounded-xl border border-white/10 bg-[#0d1017] p-1.5 ${className}`}>
      <img alt="" className="h-full w-full object-contain" draggable={false} src={`/gateways/${id}.png`} />
    </span>
  );
}

/** Falcon Bot > Gateways. Credentials live only inside each gateway's modal and only for the
 *  operation's OWN funnels; funnels shared with this operation are read-only here. */
export function GatewaysPanel() {
  const queryClient = useQueryClient();
  const state = useQuery({ queryKey: KEY, queryFn: () => apiRequest<GatewayState>("/api/payment-gateways") });
  const [configuring, setConfiguring] = useState<GatewayId | null>(null);
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
  const nameOf = (id: GatewayId) => data.gateways.find((g) => g.id === id)?.name ?? id;
  const statusOf = (id: GatewayId) => data.priority.find((row) => row.gateway === id);
  // Only the Super Admin picks and orders gateways. For everyone else SnakePay is the principal
  // (when the platform has it on) and SmokePay the automatic backup.
  const snakeAvailable = data.gateways.find((g) => g.id === "snakepay")?.available ?? false;
  const autoPrincipal: GatewayId = snakeAvailable ? "snakepay" : "smokepay";
  const principal = data.is_admin
    ? (data.priority.find((row) => row.enabled && row.flow_ids === null)?.gateway ?? data.current)
    : autoPrincipal;

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
              ? "Cada operação já pode usar a SnakePay nos funis próprios e nos compartilhamentos."
              : "Ligue para que a SnakePay possa ser usada (por você e pelos usuários)."}
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

  return (
    <section className="space-y-4">
      {data.admin && !data.admin.snakepay_enabled && adminCard}

      {data.shared_flows.length > 0 && (
        <div className="glass-panel p-4 sm:p-5">
          <div className="flex items-center gap-2">
            <Inbox className="text-accent" size={18} />
            <h2 className="text-base font-semibold text-fg">Funis compartilhados com você</h2>
          </div>
          <p className="mt-1 text-xs text-muted">
            Usam o gateway e as regras de quem compartilhou. Você não configura nada aqui e não precisa de credenciais para vendê-los.
          </p>
          <ul className="mt-3 divide-y divide-[color:var(--color-line-soft)] rounded-xl border border-line-soft">
            {data.shared_flows.map((flow) => (
              <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2.5" key={flow.name}>
                <span className="flex min-w-0 items-center gap-2 text-sm text-fg">
                  <Lock className="shrink-0 text-muted" size={13} />
                  <span className="truncate">{flow.name}</span>
                </span>
                <span className="flex flex-wrap items-center gap-2 text-xs text-fg-2">
                  <Badge>{nameOf(flow.gateway)}</Badge>
                  {flow.set_by_owner ? (
                    <span>você {pct(flow.seller_percent)} · dono {pct(flow.owner_percent)}</span>
                  ) : (
                    <span className="text-muted">porcentagem da sociedade</span>
                  )}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {data.partners_without_shop_id.length > 0 && (
        <div className="rounded-xl border border-warning/50 bg-warning/10 p-3 text-xs leading-5">
          <p className="flex items-center gap-2 font-semibold text-fg">
            <CircleAlert className="text-warning" size={15} /> Sócios sem ShopID da SnakePay
          </p>
          <p className="mt-1 text-muted">
            {data.partners_without_shop_id.join(", ")} {data.partners_without_shop_id.length > 1 ? "rodam" : "roda"} seus funis com SnakePay sem
            ShopID. Defina os ShopIDs nas regras do compartilhamento (Funis → Que compartilhei); até lá essas vendas seguem pela SmokePay.
          </p>
        </div>
      )}

      <div className="glass-panel p-4 sm:p-5">
        <div className="flex items-center gap-2">
          <CreditCard className="text-accent" size={18} />
          <h2 className="text-base font-semibold text-fg">Seus gateways</h2>
        </div>
        <p className="mt-1 text-xs text-muted">
          {data.is_admin
            ? "Para os seus funis próprios. Toque em um gateway para ver taxas e configurar a sua conta."
            : "Pagamento automático: SnakePay é a principal e o SmokePay entra sozinho como backup. Toque na SnakePay para configurar a sua conta."}
        </p>
        <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-6">
          {data.gateways.map((gateway) => {
            const row = statusOf(gateway.id);
            const status = STATUS[row?.status ?? "indisponivel"];
            // For non-admins the order is fixed: SnakePay principal, SmokePay backup.
            const isPrincipal = data.is_admin ? principal === gateway.id && Boolean(row?.enabled) : gateway.id === autoPrincipal;
            const isBackup = data.is_admin
              ? principal !== gateway.id && Boolean(row?.enabled)
              : gateway.id !== autoPrincipal && snakeAvailable;
            return (
              <button
                className={`flex aspect-square w-full flex-col items-center justify-center gap-2 rounded-2xl border p-3 text-center transition hover:border-accent/60 ${
                  isPrincipal ? "border-accent bg-brand/10" : "border-line-soft"
                }`}
                key={gateway.id}
                onClick={() => setConfiguring(gateway.id)}
                type="button"
              >
                <GatewayLogo className="size-14 sm:size-16" id={gateway.id} />
                <span className="text-sm font-semibold text-fg">{gateway.name}</span>
                <span className="flex flex-wrap justify-center gap-1">
                  {isPrincipal && <Badge tone="success">Principal</Badge>}
                  {isBackup && <Badge>Backup</Badge>}
                  {data.is_admin && !row?.enabled && <Badge tone={status.tone}>{status.label}</Badge>}
                </span>
                <span className="flex items-center gap-1 text-[11px] text-muted">
                  <Settings2 size={12} /> Configurar
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {data.is_admin && <PriorityCard data={data} />}

      {data.is_admin && (
      <div className="glass-panel p-4 sm:p-5">
        <h2 className="text-base font-semibold text-fg">Gateway por funil</h2>
        <p className="mt-1 text-xs text-muted">
          A escolha de um funil vale antes da ordem acima. Os backups ligados continuam valendo se o gateway do funil não conseguir gerar o Pix.
        </p>
        {data.flows.length === 0 ? (
          <p className="mt-3 text-xs text-muted">Você ainda não tem funis próprios.</p>
        ) : (
          <ul className="mt-3 divide-y divide-[color:var(--color-line-soft)] rounded-xl border border-line-soft">
            {data.flows.map((flow) => (
              <li className="flex flex-wrap items-center justify-between gap-2 px-3 py-2" key={flow.id}>
                <span className="min-w-0 truncate text-sm text-fg">{flow.name}</span>
                <select
                  aria-label={`Gateway do funil ${flow.name}`}
                  className="field !min-h-9 !w-auto text-xs"
                  disabled={perFlow.isPending}
                  onChange={(event) => perFlow.mutate({ id: flow.id, gateway: (event.target.value || null) as GatewayId | null })}
                  value={flow.gateway ?? ""}
                >
                  <option value="">Seguir a ordem ({nameOf(principal)} primeiro)</option>
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
      )}

      {data.admin?.snakepay_enabled && adminCard}
      <GatewayModal data={data} gateway={configuring} onClose={() => setConfiguring(null)} />
    </section>
  );
}

/** Principal + backups: order, on/off and which own funnels each gateway serves. */
function PriorityCard({ data }: { data: GatewayState }) {
  const queryClient = useQueryClient();
  const [rows, setRows] = useState<PriorityRow[]>(data.priority);
  useEffect(() => setRows(data.priority), [data.priority]);
  const save = useMutation({
    mutationFn: () =>
      apiRequest<GatewayState>("/api/payment-gateways/priority", {
        method: "PUT",
        body: { items: rows.map(({ gateway, enabled, flow_ids }) => ({ gateway, enabled, flow_ids })) },
      }),
    onSuccess: (next) => queryClient.setQueryData(KEY, next),
  });
  const dirty = JSON.stringify(rows.map(({ status: _s, priority: _p, ...rest }) => rest)) !==
    JSON.stringify(data.priority.map(({ status: _s, priority: _p, ...rest }) => rest));
  const move = (index: number, delta: number) =>
    setRows((current) => {
      const next = [...current];
      const [row] = next.splice(index, 1);
      next.splice(index + delta, 0, row);
      return next;
    });
  const patch = (index: number, change: Partial<PriorityRow>) =>
    setRows((current) => current.map((row, i) => (i === index ? { ...row, ...change } : row)));
  const nameOf = (id: GatewayId) => data.gateways.find((g) => g.id === id)?.name ?? id;
  const covered = rows.some((row) => row.enabled && row.flow_ids === null);
  const emptyScope = rows.some((row) => row.flow_ids !== null && row.flow_ids.length === 0);

  return (
    <div className="glass-panel p-4 sm:p-5">
      <h2 className="text-base font-semibold text-fg">Principal e backups</h2>
      <p className="mt-1 text-xs leading-5 text-muted">
        O primeiro gateway ligado gera o Pix. Se ele recusar ou não responder, o próximo assume, sem risco de cobrança dupla: o lead recebe um único Pix e
        só o gateway que respondeu pode confirmar o pagamento.
      </p>
      <ol className="mt-3 space-y-2">
        {rows.map((row, index) => {
          const available = data.gateways.find((g) => g.id === row.gateway)?.available ?? false;
          return (
            <li className="rounded-xl border border-line-soft bg-surface-inset p-3" key={row.gateway}>
              <div className="flex flex-wrap items-center gap-3">
                <span className="grid size-7 place-items-center rounded-full bg-brand/15 text-xs font-bold text-accent">{index + 1}</span>
                <GatewayLogo className="size-9" id={row.gateway} />
                <span className="min-w-0 flex-1">
                  <span className="block text-sm font-semibold text-fg">{nameOf(row.gateway)}</span>
                  <span className="block text-[11px] text-muted">
                    {row.enabled ? (index === 0 || !rows.slice(0, index).some((r) => r.enabled) ? "Principal" : "Backup") : "Desligado"}
                    {" · "}
                    {STATUS[row.status].label}
                  </span>
                </span>
                <span className="flex items-center gap-1">
                  <button aria-label="Subir" className="grid size-8 place-items-center rounded-lg border border-line-soft disabled:opacity-40" disabled={index === 0} onClick={() => move(index, -1)} type="button">
                    <ArrowUp size={14} />
                  </button>
                  <button aria-label="Descer" className="grid size-8 place-items-center rounded-lg border border-line-soft disabled:opacity-40" disabled={index === rows.length - 1} onClick={() => move(index, 1)} type="button">
                    <ArrowDown size={14} />
                  </button>
                </span>
                <label className="flex items-center gap-2 text-xs font-medium text-fg-2">
                  <input checked={row.enabled} disabled={!available && !row.enabled} onChange={(e) => patch(index, { enabled: e.target.checked })} type="checkbox" />
                  Ligado
                </label>
              </div>
              {row.enabled && (
                <div className="mt-3 border-t border-line-soft pt-3">
                  <div className="inline-flex rounded-full border border-line-soft p-1" role="radiogroup">
                    {([["all", "Todos os funis"], ["some", "Funis específicos"]] as const).map(([value, label]) => {
                      const on = value === "all" ? row.flow_ids === null : row.flow_ids !== null;
                      return (
                        <button
                          aria-checked={on}
                          className={`min-h-8 rounded-full px-3 text-[11px] font-medium transition ${on ? "bg-brand text-white" : "text-muted hover:text-fg"}`}
                          key={value}
                          onClick={() => patch(index, { flow_ids: value === "all" ? null : row.flow_ids ?? [] })}
                          role="radio"
                          type="button"
                        >
                          {label}
                        </button>
                      );
                    })}
                  </div>
                  {row.flow_ids !== null && (
                    <div className="mt-2 grid gap-1.5 sm:grid-cols-2">
                      {data.flows.map((flow) => (
                        <label className="flex items-center gap-2 text-xs text-fg" key={flow.id}>
                          <input
                            checked={row.flow_ids!.includes(flow.id)}
                            onChange={(e) =>
                              patch(index, {
                                flow_ids: e.target.checked ? [...row.flow_ids!, flow.id] : row.flow_ids!.filter((id) => id !== flow.id),
                              })
                            }
                            type="checkbox"
                          />
                          <span className="truncate">{flow.name}</span>
                        </label>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </li>
          );
        })}
      </ol>
      {!covered && <p className="mt-2 text-xs text-warning">Deixe pelo menos um gateway ligado para todos os funis.</p>}
      {emptyScope && <p className="mt-2 text-xs text-warning">Marque pelo menos um funil ou volte para “Todos os funis”.</p>}
      {save.error && <p className="mt-2 text-xs text-danger">{errorText(save.error)}</p>}
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button disabled={!dirty || !covered || emptyScope || save.isPending} onClick={() => save.mutate()} variant="primary">
          {save.isPending ? "Salvando…" : "Salvar ordem"}
        </Button>
        {save.isSuccess && !dirty && <span className="flex items-center gap-1 text-xs text-success"><Check size={14} /> Salvo</span>}
      </div>
    </div>
  );
}

/** One gateway's details and, for SnakePay, the operation's own account. Only for own funnels. */
function GatewayModal({ data, gateway, onClose }: { data: GatewayState; gateway: GatewayId | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [recipient, setRecipient] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [secret, setSecret] = useState("");
  const [cashoutSecret, setCashoutSecret] = useState("");
  useEffect(() => {
    if (!gateway) return;
    setRecipient(data.snakepay_recipient_id ?? "");
    setApiKey("");
    setSecret("");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [gateway]);
  const saveRecipient = useMutation({
    mutationFn: () =>
      apiRequest<GatewayState>("/api/payment-gateways", {
        method: "PUT",
        body: { gateway: data.current, snakepay_recipient_id: recipient.trim() || null, apply_to_all: false },
      }),
    onSuccess: (next) => queryClient.setQueryData(KEY, next),
  });
  const saveAccount = useMutation({
    mutationFn: (body: { api_key?: string; webhook_secret?: string; cashout_secret?: string; clear?: boolean }) =>
      apiRequest<GatewayState>("/api/payment-gateways/snakepay/credentials", { method: "PUT", body }),
    onSuccess: (next) => {
      queryClient.setQueryData(KEY, next);
      setApiKey("");
      setSecret("");
      setCashoutSecret("");
    },
  });
  const info = data.gateways.find((g) => g.id === gateway);
  if (!gateway || !info) return null;
  const busy = saveRecipient.isPending || saveAccount.isPending;

  return (
    <Modal busy={busy} description={info.description} onClose={onClose} open title={info.name} wide>
      <div className="space-y-4">
        <div className="flex items-center gap-3 rounded-xl border border-line-soft bg-surface-inset p-3">
          <GatewayLogo className="size-12" id={gateway} />
          <div className="min-w-0 text-xs leading-5">
            <p className="font-semibold text-fg">{info.available ? "Disponível" : "Ainda não liberado pelo administrador"}</p>
            <p className="text-muted">{info.fee}</p>
          </div>
        </div>

        {gateway === "smokepay" ? (
          <p className="text-xs leading-5 text-muted">
            A SmokePay não pede credencial sua: a subconta da sua operação é criada sozinha na primeira venda e o saque é feito pela Carteira.
          </p>
        ) : (
          <>
            <p className="rounded-xl border border-line-soft px-3 py-2 text-[11px] leading-5 text-muted">
              Com a conta SnakePay própria (abaixo), as vendas — inclusive dos funis compartilhados com você — são cobradas na sua conta e só a comissão do dono sai por split. Para vender funis compartilhados pela SnakePay, a conta própria é obrigatória.
            </p>
            {/* The ShopID (platform-key split) only matters for the operation's own funnels. */}
            {(data.has_own_flow || data.snakepay_recipient_id) && (
            <div>
              <label className="block text-sm font-medium text-fg" htmlFor="snakepay-recipient">Seu ShopID SnakePay</label>
              <input
                autoComplete="off"
                className="field mt-2 font-mono text-xs"
                id="snakepay-recipient"
                onChange={(event) => setRecipient(event.target.value)}
                placeholder="ex.: snakepay_6fde14d647ba4acbb45855490d22f435"
                spellCheck={false}
                value={recipient}
              />
              <p className="mt-1.5 text-[11px] text-muted">SnakePay → Conta → Split → Seu ShopID. Recebe as vendas dos seus funis próprios pelo split da plataforma.</p>
              <div className="mt-2 flex items-center gap-2">
                <Button
                  disabled={busy || (recipient.trim() || null) === (data.snakepay_recipient_id ?? null)}
                  onClick={() => saveRecipient.mutate()}
                  size="sm"
                  variant="primary"
                >
                  Salvar ShopID
                </Button>
                {saveRecipient.isSuccess && <span className="flex items-center gap-1 text-xs text-success"><Check size={14} /> Salvo</span>}
              </div>
              {saveRecipient.error && <p className="mt-2 text-xs text-danger">{errorText(saveRecipient.error)}</p>}
            </div>
            )}

            {!data.is_admin && (
              <details className="rounded-xl border border-line-soft p-3" open={data.snakepay_account_key_set}>
                <summary className="flex cursor-pointer items-center gap-2 text-sm font-medium text-fg">
                  <KeyRound size={15} /> Conta SnakePay própria (opcional)
                </summary>
                <p className="mt-2 text-xs leading-5 text-muted">
                  Com a chave e o segredo da sua conta, as vendas dos seus funis são criadas direto nela. Ficam criptografadas e nunca são mostradas de novo.
                </p>
                <div className="mt-3 grid gap-3 sm:grid-cols-2">
                  <label className="text-xs font-medium text-fg-2" htmlFor="snakepay-api-key">
                    Chave secreta da API
                    <input
                      autoComplete="new-password"
                      className="field mt-1 font-mono text-xs"
                      id="snakepay-api-key"
                      onChange={(event) => setApiKey(event.target.value)}
                      placeholder={data.snakepay_account_key_set ? "Já configurada · deixe vazio para manter" : "Chave da sua conta SnakePay"}
                      type="password"
                      value={apiKey}
                    />
                  </label>
                  <label className="text-xs font-medium text-fg-2" htmlFor="snakepay-webhook-secret">
                    Segredo do webhook
                    <input
                      autoComplete="new-password"
                      className="field mt-1 font-mono text-xs"
                      id="snakepay-webhook-secret"
                      onChange={(event) => setSecret(event.target.value)}
                      placeholder={data.snakepay_account_secret_set ? "Já configurado · deixe vazio para manter" : "Segredo configurado na SnakePay"}
                      type="password"
                      value={secret}
                    />
                  </label>
                  <label className="text-xs font-medium text-fg-2 sm:col-span-2" htmlFor="snakepay-cashout-secret">
                    Segredo de saque (Cash Out) — para sacar a SnakePay pela Carteira
                    <input
                      autoComplete="new-password"
                      className="field mt-1 font-mono text-xs"
                      id="snakepay-cashout-secret"
                      onChange={(event) => setCashoutSecret(event.target.value)}
                      placeholder={data.snakepay_cashout_secret_set ? "Já configurado · deixe vazio para manter" : "Segredo de Cash Out da sua conta SnakePay"}
                      type="password"
                      value={cashoutSecret}
                    />
                  </label>
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <Button
                    disabled={busy || (!apiKey.trim() && !secret.trim() && !cashoutSecret.trim())}
                    onClick={() =>
                      saveAccount.mutate({
                        api_key: apiKey.trim() || undefined,
                        webhook_secret: secret.trim() || undefined,
                        cashout_secret: cashoutSecret.trim() || undefined,
                      })
                    }
                    size="sm"
                    variant="primary"
                  >
                    {saveAccount.isPending ? "Salvando…" : "Salvar credenciais"}
                  </Button>
                  {(data.snakepay_account_key_set || data.snakepay_account_secret_set) && (
                    <Button disabled={busy} onClick={() => saveAccount.mutate({ clear: true })} size="sm">
                      Remover credenciais
                    </Button>
                  )}
                  {data.snakepay_account_key_set && data.snakepay_account_secret_set && (
                    <span className="text-xs text-success">
                      Conta pronta para cobrar diretamente{data.snakepay_cashout_secret_set ? " e sacar pela Carteira" : ""}.
                    </span>
                  )}
                </div>
                <div className="mt-3">
                  <CopyField hint="Cadastre esta URL na área Desenvolvedor da sua conta SnakePay." label="URL do webhook" value={data.snakepay_webhook_url} />
                </div>
                {saveAccount.error && <p className="mt-2 text-xs text-danger">{errorText(saveAccount.error)}</p>}
              </details>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}
