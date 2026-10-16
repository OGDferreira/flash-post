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
import { brl, type Bot, type Flow } from "./types";

const errorText = (error: unknown, fallback: string) => (error instanceof ApiError ? error.message : fallback);

/** Connected bots: token from @BotFather, linked flow, on/off and stats. */
export function BotsListPanel() {
  const queryClient = useQueryClient();
  const [connectOpen, setConnectOpen] = useState(false);
  const bots = useQuery({ queryKey: ["bots"], queryFn: () => apiRequest<{ bots: Bot[] }>("/api/bots"), retry: false });
  const flows = useQuery({
    queryKey: ["bots", "flows"],
    queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"),
    retry: false,
  });
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
  const remove = useMutation({
    mutationFn: (id: string) => apiRequest<void>(`/api/bots/${id}`, { method: "DELETE" }),
    onSuccess: refresh,
  });

  if (bots.isLoading) return <LoadingState label="Carregando robôs" />;
  if (bots.error || !bots.data) {
    return <ErrorState message={errorText(bots.error, "Não foi possível carregar os robôs.")} onRetry={() => void bots.refetch()} />;
  }
  const mutationError = update.error ?? reconnect.error ?? remove.error;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">Cada robô segue um fluxo. Troque o fluxo a qualquer momento: vale para os próximos /start.</p>
        <Button variant="primary" onClick={() => setConnectOpen(true)}>
          <Plus size={16} /> Conectar robô
        </Button>
      </div>
      {mutationError && <ErrorState message={errorText(mutationError, "A ação não pôde ser concluída.")} />}
      {bots.data.bots.length === 0 ? (
        <EmptyState
          icon={<BotIcon size={18} />}
          message="Nenhum robô conectado ainda. Crie um no @BotFather do Telegram e cole o token aqui."
          action={<Button variant="primary" onClick={() => setConnectOpen(true)}>Conectar o primeiro robô</Button>}
        />
      ) : (
        <div className="grid gap-3 md:grid-cols-2">
          {bots.data.bots.map((bot) => (
            <Card key={bot.id} className="space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate font-medium text-fg">{bot.name}</p>
                  <a className="text-sm text-accent hover:underline" href={`https://t.me/${bot.username}`} rel="noreferrer" target="_blank">
                    @{bot.username}
                  </a>
                </div>
                {bot.status === "error" ? (
                  <Badge tone="danger">Com erro</Badge>
                ) : bot.is_active ? (
                  <Badge tone="success">Ativo</Badge>
                ) : (
                  <Badge>Pausado</Badge>
                )}
              </div>
              {bot.last_error && <p className="break-words text-xs text-danger">{bot.last_error}</p>}
              <dl className="grid grid-cols-3 gap-2 text-center">
                {[
                  ["Leads", String(bot.leads)],
                  ["Vendas", String(bot.sales)],
                  ["Faturado", brl(bot.revenue)],
                ].map(([label, value]) => (
                  <div className="rounded-xl bg-surface-inset p-2" key={label}>
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
                  <option value="">Sem fluxo (o robô não responde)</option>
                  {flows.data?.flows.map((flow) => (
                    <option key={flow.id} value={flow.id}>
                      {flow.name}
                    </option>
                  ))}
                </select>
              </label>
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
      title="Conectar robô do Telegram"
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
          <li>Para entregar acesso a um grupo VIP, adicione o robô como administrador do grupo com permissão de convidar.</li>
        </ol>
        <label className="grid gap-1.5 text-sm text-fg-2">
          Token do robô
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
