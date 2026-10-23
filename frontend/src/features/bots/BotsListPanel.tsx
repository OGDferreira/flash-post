import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot as BotIcon, Plus, RefreshCw, Trash2 } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import type { MetricsPeriod } from "@/features/analytics/period";
import { AdminHideToggle } from "./AdminHideToggle";
import { BotAvatar } from "./BotAvatar";
import { useBotStats } from "./ConversionOverview";
import { brl, type Bot, type BotGroup, type Flow, type SharedFlowOption } from "./types";
import { useChiefLabel } from "@/features/partners/api";

const errorText = (error: unknown, fallback: string) => (error instanceof ApiError ? error.message : fallback);

/** Connected bots: token from @BotFather, linked flow, on/off and stats. */
export function BotsListPanel({ period }: { period: MetricsPeriod }) {
  const chief = useChiefLabel();
  const queryClient = useQueryClient();
  const [connectOpen, setConnectOpen] = useState(false);
  const [cacheInfo, setCacheInfo] = useState<Record<string, string>>({});
  const bots = useQuery({ queryKey: ["bots"], queryFn: () => apiRequest<{ bots: Bot[] }>("/api/bots"), retry: false });
  const flows = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[]; shared_flows?: SharedFlowOption[] }>("/api/bots/flows/list"),
    retry: false,
  });
  const groups = useQuery({
    queryKey: ["bots", "groups"],
    queryFn: () => apiRequest<{ groups: BotGroup[] }>("/api/bots/groups/list"),
    retry: false,
  });
  const stats = useBotStats(period);
  const sharedIds = new Set((flows.data?.shared_flows ?? []).map((flow) => flow.id));
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["bots"] });

  const update = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) =>
      apiRequest<Bot>(`/api/bots/${id}`, { method: "PATCH", body }),
    onSuccess: refresh,
  });
  const reconnect = useMutation({
    mutationFn: (id: string) => apiRequest<Bot>(`/api/bots/${id}/webhook`, { method: "POST" }),
    onSuccess: refresh,
  });
  const checkCache = useMutation({
    mutationFn: (id: string) =>
      apiRequest<{ ok: boolean; cached: number; total: number }>(`/api/bots/${id}/cache/check`, { method: "POST" }),
    onSuccess: (result, id) => {
      setCacheInfo((current) => ({ ...current, [id]: `${result.cached} de ${result.total} mídias no cache` }));
      void groups.refetch();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/api/bots/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });

  if (bots.isLoading) return <LoadingState label="Carregando bots" />;
  if (bots.error || !bots.data) {
    return <ErrorState message={errorText(bots.error, "Não foi possível carregar os bots.")} onRetry={() => void bots.refetch()} />;
  }
  const mutationError = update.error ?? reconnect.error ?? remove.error ?? checkCache.error;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">Cada bot segue um fluxo. Troque o fluxo a qualquer momento: vale para os próximos /start.</p>
        <Button variant="primary" onClick={() => setConnectOpen(true)}>
          <Plus size={16} /> Conectar bot
        </Button>
      </div>
      {mutationError && <ErrorState message={errorText(mutationError, "A ação não pôde ser concluída.")} />}
      {bots.data.bots.length === 0 ? (
        <EmptyState
          icon={<BotIcon size={18} />}
          message="Nenhum bot conectado ainda. Crie um no @BotFather do Telegram e cole o token aqui."
          action={<Button variant="primary" onClick={() => setConnectOpen(true)}>Conectar o primeiro bot</Button>}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
          {bots.data.bots.map((bot) => (
            <Card key={bot.id} className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex min-w-0 items-center gap-3">
                <BotAvatar botId={bot.id} name={bot.name} size={44} />
                <div className="min-w-0">
                  <p className="truncate font-medium text-fg">{bot.name}</p>
                  <a className="text-sm text-accent hover:underline" href={`https://t.me/${bot.username}`} rel="noreferrer" target="_blank">
                    @{bot.username}
                  </a>
                </div>
                </div>
                {bot.status === "error" ? (
                  <Badge tone="danger">Com erro</Badge>
                ) : bot.is_active ? (
                  <Badge tone="success">Ativo</Badge>
                ) : (
                  <Badge>Pausado</Badge>
                )}
              </div>
              <AdminHideToggle hidden={bot.hidden_by_admin} id={bot.id} kind="bot" takenFrom={bot.taken_from} />
              {bot.last_error && <p className="break-words text-xs text-danger">{bot.last_error}</p>}
              <dl className="grid grid-cols-4 gap-2 text-center">
                {[
                  ["Leads", String(bot.leads)],
                  ["Vendas", String(bot.sales)],
                  ["Conversão", `${(stats.data?.bots[bot.id]?.conversion ?? 0).toLocaleString("pt-BR")}%`],
                  ["Faturado", brl(bot.revenue)],
                ].map(([label, value]) => (
                  <div className="min-w-0 rounded-xl bg-surface-inset p-2" key={label}>
                    <dt className="text-[11px] text-muted">{label}</dt>
                    <dd className="text-sm font-semibold text-fg">{value}</dd>
                  </div>
                ))}
              </dl>
              <label className="grid gap-1.5 text-sm text-fg-2">
                Fluxo
                <select
                  className="field"
                  value={bot.flow_id ?? ""}
                  disabled={update.isPending}
                  onChange={(event) =>
                    update.mutate({
                      id: bot.id,
                      body: event.target.value ? { flow_id: event.target.value } : { clear_flow: true },
                    })
                  }
                >
                  <option value="">Sem fluxo (o bot não responde)</option>
                  {flows.data?.flows.map((flow) => (
                    <option key={flow.id} value={flow.id}>
                      {flow.name}
                    </option>
                  ))}
                  {(flows.data?.shared_flows ?? []).length > 0 && (
                    <optgroup label={`Compartilhados por ${chief}`}>
                      {flows.data!.shared_flows!.map((flow) => (
                        <option key={flow.id} value={flow.id}>{flow.name}</option>
                      ))}
                    </optgroup>
                  )}
                </select>
              </label>
              {bot.flow_id && sharedIds.has(bot.flow_id) && (
                <label className="grid gap-1.5 text-sm text-fg-2">
                  Grupo de entrega deste bot
                  <select
                    className="field"
                    disabled={update.isPending}
                    onChange={(event) =>
                      update.mutate({
                        id: bot.id,
                        body: event.target.value ? { delivery_group_chat_id: Number(event.target.value) } : { clear_delivery_group: true },
                      })
                    }
                    value={bot.delivery_group_chat_id ?? ""}
                  >
                    <option value="">Escolha seu grupo VIP</option>
                    {(groups.data?.groups ?? []).filter((group) => group.bot === bot.username).map((group) => (
                      <option disabled={!group.can_invite} key={group.chat_id} value={group.chat_id}>
                        {group.title}{group.can_invite ? "" : " (sem permissão de convidar)"}
                      </option>
                    ))}
                  </select>
                  <span className="text-[11px] text-muted">O funil é de {chief}; quem compra entra no seu grupo. Adicione o bot como admin dele.</span>
                </label>
              )}
              <div className="grid gap-1.5 text-sm text-fg-2">
                <label htmlFor={`cache-${bot.id}`}>Cache de mídia</label>
                <div className="flex gap-2">
                  <select
                    className="field min-w-0 flex-1"
                    disabled={update.isPending}
                    id={`cache-${bot.id}`}
                    onChange={(event) =>
                      update.mutate({
                        id: bot.id,
                        body: event.target.value ? { cache_chat_id: Number(event.target.value) } : { clear_cache_chat: true },
                      })
                    }
                    value={bot.cache_chat_id ?? ""}
                  >
                    <option value="">Sem cache (envia direto do painel)</option>
                    {(groups.data?.groups ?? []).filter((group) => group.bot === bot.username).map((group) => (
                      <option key={group.chat_id} value={group.chat_id}>
                        {group.title} ({group.type === "channel" ? "canal" : "grupo"})
                      </option>
                    ))}
                  </select>
                  <Button
                    aria-label="Verificar cache e enviar mídias que faltam"
                    disabled={!bot.cache_chat_id || checkCache.isPending}
                    onClick={() => checkCache.mutate(bot.id)}
                    size="sm"
                    title="Verificar admin e enviar mídias que faltam"
                  >
                    <RefreshCw size={14} />
                  </Button>
                </div>
                <span className="text-[11px] text-muted">
                  {bot.cache_chat_id
                    ? cacheInfo[bot.id] ?? "Configurado. As mídias do fluxo ficam salvas nesse chat e são reenviadas pelo ID do Telegram."
                    : "Crie um canal ou grupo, adicione o bot como admin e escolha aqui. Ele vira o backup das mídias e deixa o envio instantâneo."}
                </span>
                <LinkGroup botId={bot.id} onLinked={() => void groups.refetch()} />
              </div>
              <div className="flex flex-wrap gap-2">
                <Button size="sm" onClick={() => update.mutate({ id: bot.id, body: { is_active: !bot.is_active } })}>
                  {bot.is_active ? "Pausar" : "Ativar"}
                </Button>
                <Button size="sm" disabled={reconnect.isPending} onClick={() => reconnect.mutate(bot.id)}>
                  <RefreshCw size={14} /> Reconectar
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  onClick={async () => {
                    if (await confirmAction(`Desconectar @${bot.username}? Leads e vendas continuam no histórico.`)) remove.mutate(bot.id);
                  }}
                >
                  <Trash2 size={14} /> Desconectar
                </Button>
              </div>
            </Card>
          ))}
        </div>
      )}
      <ConnectBotModal open={connectOpen} flows={flows.data?.flows ?? []} onClose={() => setConnectOpen(false)} onDone={refresh} />
    </div>
  );
}

export function ConnectBotModal({
  open,
  flows,
  onClose,
  onDone,
  defaultFlowId = "",
}: {
  open: boolean;
  flows: Flow[];
  onClose: () => void;
  onDone: () => void;
  defaultFlowId?: string;
}) {
  const [token, setToken] = useState("");
  const [flowId, setFlowId] = useState(defaultFlowId);
  const connect = useMutation({
    mutationFn: () => apiRequest<Bot>("/api/bots", { method: "POST", body: { token: token.trim(), flow_id: flowId || null } }),
    onSuccess: () => {
      setToken("");
      onDone();
      onClose();
    },
  });
  return (
    <Modal
      open={open}
      title="Conectar bot do Telegram"
      onClose={onClose}
      busy={connect.isPending}
      footer={
        <>
          <Button onClick={onClose}>Cancelar</Button>
          <Button variant="primary" disabled={connect.isPending || token.trim().length < 20} onClick={() => connect.mutate()}>
            {connect.isPending ? "Conectando..." : "Conectar"}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <ol className="list-decimal space-y-1 pl-5 text-sm leading-6 text-fg-2">
          <li>
            No Telegram, abra o{" "}
            <a className="text-accent hover:underline" href="https://t.me/BotFather" rel="noreferrer" target="_blank">
              @BotFather
            </a>{" "}
            e envie <code>/newbot</code>.
          </li>
          <li>Escolha o nome e o usuário (precisa terminar em “bot”).</li>
          <li>Copie o token que ele responder (algo como <code>123456:ABC-...</code>) e cole abaixo.</li>
          <li>Para entregar acesso a um grupo VIP, adicione o bot como administrador do grupo com permissão de convidar.</li>
        </ol>
        <label className="grid gap-1.5 text-sm text-fg-2">
          Token do bot
          <input
            autoComplete="off"
            className="field font-mono"
            placeholder="123456789:AA..."
            value={token}
            onChange={(event) => setToken(event.target.value)}
          />
        </label>
        <label className="grid gap-1.5 text-sm text-fg-2">
          Fluxo (opcional)
          <select className="field" value={flowId} onChange={(event) => setFlowId(event.target.value)}>
            <option value="">Escolher depois</option>
            {flows.map((flow) => (
              <option key={flow.id} value={flow.id}>
                {flow.name}
              </option>
            ))}
          </select>
        </label>
        {connect.error && <ErrorState message={errorText(connect.error, "Não foi possível conectar.")} />}
      </div>
    </Modal>
  );
}


/** A group/channel the bot joined before it was connected here never shows up by itself
 * (Telegram only tells about new joins): post anything there, or type its @ / link / ID. */
function LinkGroup({ botId, onLinked }: { botId: string; onLinked: () => void }) {
  const [open, setOpen] = useState(false);
  const [chat, setChat] = useState("");
  const link = useMutation({
    mutationFn: () => apiRequest<BotGroup>(`/api/bots/${botId}/groups/link`, { method: "POST", body: { chat: chat.trim() } }),
    onSuccess: () => {
      setChat("");
      setOpen(false);
      onLinked();
    },
  });
  if (!open) {
    return (
      <button className="justify-self-start text-[11px] font-medium text-accent hover:underline" onClick={() => setOpen(true)} type="button">
        Seu grupo ou canal não aparece na lista?
      </button>
    );
  }
  return (
    <div className="grid gap-2 rounded-xl border border-line-soft bg-surface-inset p-3 text-[11px] leading-5 text-muted">
      <p>
        Se o bot já estava no grupo antes de ser conectado aqui, o Telegram não avisa. Envie qualquer mensagem no grupo (ou publique algo no canal) e
        atualize a página, ou informe abaixo o @, o link t.me/… ou o ID do grupo/canal.
      </p>
      <form
        className="flex gap-2"
        onSubmit={(event) => {
          event.preventDefault();
          if (chat.trim()) link.mutate();
        }}
      >
        <input
          aria-label="@, link ou ID do grupo ou canal"
          className="field min-w-0 flex-1 text-xs"
          onChange={(event) => setChat(event.target.value)}
          placeholder="@meucanal, t.me/meucanal ou -100…"
          value={chat}
        />
        <Button disabled={!chat.trim() || link.isPending} size="sm" type="submit">
          {link.isPending ? "Buscando…" : "Adicionar"}
        </Button>
      </form>
      {link.error && <p className="text-danger">{link.error instanceof ApiError ? link.error.message : "Não foi possível adicionar."}</p>}
    </div>
  );
}
