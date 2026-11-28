import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Clock,
  Link2,
  RefreshCw,
  RotateCcw,
  Send,
} from "lucide-react";
import { Link } from "react-router-dom";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { apiRequest } from "@/services/api";

type HealthEvent = {
  id: string;
  created_at: string;
  category: string | null;
  level: "error" | "warning";
  message: string;
  status: "pending" | "resolved";
  resolved_at: string | null;
};

type AccountHealth = {
  account_id: string;
  username: string;
  profile_picture_url: string | null;
  status: string;
  status_reason: string | null;
  error_at: string | null;
  token_expires_at: string | null;
  pending_count: number;
  last_event_at: string | null;
  events: HealthEvent[];
};

type LoopAlert = {
  id: string;
  loop_id: string;
  loop_name: string | null;
  created_at: string;
  message: string;
  status: "pending" | "resolved";
};

type HealthResponse = {
  accounts: AccountHealth[];
  loops: LoopAlert[];
  pending_total: number;
};

const categoryLabels: Record<string, string> = {
  token: "Token / conta",
  account_disconnected: "Conta desconectada",
  loop_stuck: "Loop travado",
  rate_limit: "Limite da Meta",
  storage: "Storage",
  network: "Rede",
  video_format: "Formato do vídeo",
  meta_api: "API da Meta",
  unknown: "Falha de envio",
};

const statusBadge: Record<string, { label: string; className: string }> = {
  connected: { label: "Conectada", className: "border-success/30 bg-success-soft text-success" },
  disconnected: { label: "Desconectada", className: "border-danger/30 bg-danger-soft text-danger" },
  error: { label: "Com erro", className: "border-danger/30 bg-danger-soft text-danger" },
};

function formatDate(value: string | null): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "America/Sao_Paulo",
  });
}

function categoryLabel(category: string | null): string {
  if (!category) return "Falha de envio";
  return categoryLabels[category] ?? category;
}

type AlertBot = { id: string; name: string; username: string };
type TelegramAlert = { chat_id: number | null; bot_id: string | null; bots: AlertBot[] };

function TelegramAlertCard() {
  const queryClient = useQueryClient();
  const [open, setOpen] = useState(false);
  const [chatId, setChatId] = useState("");
  const [botId, setBotId] = useState("");
  const [feedback, setFeedback] = useState<{ ok: boolean; text: string } | null>(null);
  const [dirty, setDirty] = useState(false);

  const config = useQuery({
    queryKey: ["diagnostics", "telegram-alert"],
    queryFn: () => apiRequest<TelegramAlert>("/api/diagnostics/alerts/telegram"),
    retry: false,
  });

  if (config.data && !dirty) {
    const nextChat = config.data.chat_id ? String(config.data.chat_id) : "";
    const nextBot = config.data.bot_id ?? "";
    if (nextChat !== chatId) setChatId(nextChat);
    if (nextBot !== botId) setBotId(nextBot);
  }

  const save = useMutation({
    mutationFn: () =>
      apiRequest<TelegramAlert>("/api/diagnostics/alerts/telegram", {
        method: "PUT",
        body: {
          chat_id: chatId.trim() ? Number(chatId.trim()) : null,
          bot_id: botId || null,
        },
      }),
    onSuccess: () => {
      setDirty(false);
      setFeedback({ ok: true, text: "Salvo." });
      queryClient.invalidateQueries({ queryKey: ["diagnostics", "telegram-alert"] });
    },
    onError: () => setFeedback({ ok: false, text: "Não foi possível salvar." }),
  });

  const test = useMutation({
    mutationFn: () =>
      apiRequest<{ sent: boolean }>("/api/diagnostics/alerts/telegram/test", {
        method: "POST",
        body: {},
      }),
    onSuccess: () => setFeedback({ ok: true, text: "Mensagem de teste enviada." }),
    onError: (err: unknown) =>
      setFeedback({
        ok: false,
        text: err instanceof Error ? err.message : "Falha ao enviar o teste.",
      }),
  });

  const bots = config.data?.bots ?? [];

  return (
    <section className="rounded-xl border border-line bg-surface">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 p-4 text-left"
      >
        {open ? (
          <ChevronDown className="size-4 text-muted" />
        ) : (
          <ChevronRight className="size-4 text-muted" />
        )}
        <Send className="size-4 text-muted" />
        <div className="flex-1">
          <p className="font-medium text-fg-1">Avisos no Telegram</p>
          <p className="text-xs text-muted">
            Receba uma mensagem quando uma conta sair do ar.
            {config.data?.chat_id ? " Ligado." : " Opcional."}
          </p>
        </div>
      </button>
      {open && (
        <div className="space-y-3 border-t border-line px-4 pb-4 pt-3 text-sm">
          <p className="text-xs text-muted">
            Inicie uma conversa com o bot no Telegram e descubra seu chat ID (ex.: envie
            /start para @userinfobot). Cole o número abaixo.
          </p>
          <label className="block">
            <span className="text-xs text-fg-2">Chat ID</span>
            <input
              value={chatId}
              onChange={(e) => {
                setChatId(e.target.value.replace(/[^0-9-]/g, ""));
                setDirty(true);
                setFeedback(null);
              }}
              inputMode="numeric"
              placeholder="123456789"
              className="mt-1 w-full rounded-lg border border-line bg-surface-raised px-3 py-2 text-fg-1 outline-none focus:border-brand"
            />
          </label>
          {bots.length > 0 && (
            <label className="block">
              <span className="text-xs text-fg-2">Bot que envia</span>
              <select
                value={botId}
                onChange={(e) => {
                  setBotId(e.target.value);
                  setDirty(true);
                  setFeedback(null);
                }}
                className="mt-1 w-full rounded-lg border border-line bg-surface-raised px-3 py-2 text-fg-1 outline-none focus:border-brand"
              >
                <option value="">Automático (primeiro bot ativo)</option>
                {bots.map((bot) => (
                  <option key={bot.id} value={bot.id}>
                    {bot.name} (@{bot.username})
                  </option>
                ))}
              </select>
            </label>
          )}
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={() => save.mutate()}
              disabled={save.isPending}
              className="rounded-lg border border-brand px-3 py-1.5 text-xs text-white hover:bg-well disabled:opacity-60"
            >
              Salvar
            </button>
            <button
              type="button"
              onClick={() => test.mutate()}
              disabled={test.isPending || !config.data?.chat_id || dirty}
              className="flex items-center gap-1 rounded-lg border border-line px-3 py-1.5 text-xs text-fg-2 hover:text-white disabled:opacity-50"
              title={dirty ? "Salve antes de testar" : undefined}
            >
              <Send className="size-3" /> Enviar teste
            </button>
            {feedback && (
              <span className={`text-xs ${feedback.ok ? "text-success" : "text-danger"}`}>
                {feedback.text}
              </span>
            )}
          </div>
        </div>
      )}
    </section>
  );
}

export function BotHealthPage() {
  const queryClient = useQueryClient();
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const health = useQuery({
    queryKey: ["diagnostics", "account-health"],
    queryFn: () => apiRequest<HealthResponse>("/api/diagnostics/account-health"),
    retry: false,
    refetchInterval: 60_000,
  });

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["diagnostics", "account-health"] });

  const resolveEvent = useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/diagnostics/events/${id}/resolve`, { method: "POST", body: {} }),
    onSuccess: invalidate,
  });
  const reopenEvent = useMutation({
    mutationFn: (id: string) =>
      apiRequest(`/api/diagnostics/events/${id}/reopen`, { method: "POST", body: {} }),
    onSuccess: invalidate,
  });
  const resolveAccount = useMutation({
    mutationFn: (accountId: string) =>
      apiRequest(`/api/diagnostics/accounts/${accountId}/resolve`, { method: "POST", body: {} }),
    onSuccess: invalidate,
  });

  if (health.isLoading) return <LoadingState label="Carregando saúde dos bots" />;
  if (health.isError)
    return (
      <ErrorState
        message="Não foi possível carregar a saúde dos bots. Tente novamente em instantes."
        onRetry={() => health.refetch()}
      />
    );

  const data = health.data!;
  const hasContent = data.accounts.length > 0 || data.loops.length > 0;

  return (
    <div className="mx-auto w-full max-w-4xl space-y-5 px-4 py-5">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-fg-1">Saúde dos bots</h1>
          <p className="text-sm text-muted">
            Erros recentes por conta: falha de envio, token expirado e loop travado.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {data.pending_total > 0 && (
            <span className="rounded-full border border-danger/30 bg-danger-soft px-3 py-1 text-xs font-medium text-danger">
              {data.pending_total} pendente{data.pending_total > 1 ? "s" : ""}
            </span>
          )}
          <button
            type="button"
            onClick={() => health.refetch()}
            className="flex min-h-9 items-center gap-1.5 rounded-lg border border-line px-3 text-xs text-fg-2 hover:text-white"
          >
            <RefreshCw className="size-3.5" /> Atualizar
          </button>
        </div>
      </header>

      <TelegramAlertCard />

      {data.loops.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-sm font-medium text-fg-2">Loops travados</h2>
          {data.loops.map((loop) => (
            <div
              key={loop.id}
              className="flex items-start gap-3 rounded-xl border border-warning/30 bg-warning-soft p-4 text-sm text-warning"
            >
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              <div className="min-w-0 flex-1">
                <p className="font-medium">{loop.loop_name ?? "Loop"}</p>
                <p className="opacity-90">{loop.message}</p>
                <p className="mt-1 text-xs opacity-70">
                  <Clock className="mr-1 inline size-3" />
                  {formatDate(loop.created_at)}
                </p>
              </div>
            </div>
          ))}
        </section>
      )}

      {!hasContent ? (
        <EmptyState
          icon={<CheckCircle2 size={18} />}
          message="Tudo certo por aqui. Nenhum erro recente nas suas contas — esta tela avisa assim que algo falhar."
        />
      ) : (
        <section className="space-y-3">
          {data.accounts.map((account) => {
            const badge = statusBadge[account.status] ?? statusBadge.error;
            const isOpen = expanded[account.account_id] ?? account.pending_count > 0;
            return (
              <div
                key={account.account_id}
                className="overflow-hidden rounded-xl border border-line bg-surface"
              >
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((prev) => ({ ...prev, [account.account_id]: !isOpen }))
                  }
                  className="flex w-full items-center gap-3 p-4 text-left"
                >
                  {isOpen ? (
                    <ChevronDown className="size-4 shrink-0 text-muted" />
                  ) : (
                    <ChevronRight className="size-4 shrink-0 text-muted" />
                  )}
                  {account.profile_picture_url ? (
                    <img
                      src={account.profile_picture_url}
                      alt=""
                      className="size-9 shrink-0 rounded-full object-cover"
                    />
                  ) : (
                    <div className="size-9 shrink-0 rounded-full bg-well" />
                  )}
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-fg-1">@{account.username}</p>
                    <p className="text-xs text-muted">
                      Último erro: {formatDate(account.last_event_at)}
                    </p>
                  </div>
                  {account.pending_count > 0 && (
                    <span className="rounded-full border border-danger/30 bg-danger-soft px-2 py-0.5 text-xs font-medium text-danger">
                      {account.pending_count}
                    </span>
                  )}
                  <span
                    className={`shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium ${badge.className}`}
                  >
                    {badge.label}
                  </span>
                </button>

                {isOpen && (
                  <div className="space-y-2 border-t border-line px-4 pb-4 pt-3">
                    {account.status !== "connected" && (
                      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-danger/30 bg-danger-soft px-3 py-2 text-xs text-danger">
                        <span>
                          {account.status_reason ??
                            "Conta fora do ar — reconecte para voltar a publicar."}
                        </span>
                        <Link
                          to="/feature/accounts"
                          className="flex items-center gap-1 rounded-md border border-danger/40 px-2 py-1 font-medium hover:bg-danger/10"
                        >
                          <Link2 className="size-3" /> Reconectar
                        </Link>
                      </div>
                    )}

                    {account.events.length === 0 ? (
                      <p className="py-2 text-xs text-muted">Sem erros registrados na janela recente.</p>
                    ) : (
                      <>
                        <div className="flex justify-end">
                          {account.pending_count > 0 && (
                            <button
                              type="button"
                              onClick={() => resolveAccount.mutate(account.account_id)}
                              disabled={resolveAccount.isPending}
                              className="flex items-center gap-1 rounded-md border border-line px-2 py-1 text-xs text-fg-2 hover:text-white disabled:opacity-50"
                            >
                              <CheckCircle2 className="size-3" /> Marcar tudo resolvido
                            </button>
                          )}
                        </div>
                        <ul className="space-y-2">
                          {account.events.map((event) => (
                            <li
                              key={event.id}
                              className={`rounded-lg border px-3 py-2 text-xs ${
                                event.status === "resolved"
                                  ? "border-line bg-surface-raised text-muted"
                                  : "border-line bg-surface-raised text-fg-2"
                              }`}
                            >
                              <div className="flex items-start gap-2">
                                <span
                                  className={`mt-1 size-2 shrink-0 rounded-full ${
                                    event.status === "resolved"
                                      ? "bg-success"
                                      : event.level === "warning"
                                        ? "bg-warning"
                                        : "bg-danger"
                                  }`}
                                />
                                <div className="min-w-0 flex-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <span className="font-medium text-fg-1">
                                      {categoryLabel(event.category)}
                                    </span>
                                    <span className="text-muted">{formatDate(event.created_at)}</span>
                                    {event.status === "resolved" && (
                                      <span className="rounded-full border border-success/30 bg-success-soft px-1.5 text-success">
                                        resolvido
                                      </span>
                                    )}
                                  </div>
                                  <p className="mt-0.5 break-words">{event.message}</p>
                                </div>
                                {event.status === "pending" ? (
                                  <button
                                    type="button"
                                    onClick={() => resolveEvent.mutate(event.id)}
                                    disabled={resolveEvent.isPending}
                                    className="shrink-0 rounded-md border border-line px-2 py-1 text-fg-2 hover:text-white disabled:opacity-50"
                                    title="Marcar como resolvido"
                                  >
                                    <CheckCircle2 className="size-3.5" />
                                  </button>
                                ) : (
                                  <button
                                    type="button"
                                    onClick={() => reopenEvent.mutate(event.id)}
                                    disabled={reopenEvent.isPending}
                                    className="shrink-0 rounded-md border border-line px-2 py-1 text-muted hover:text-white disabled:opacity-50"
                                    title="Reabrir"
                                  >
                                    <RotateCcw className="size-3.5" />
                                  </button>
                                )}
                              </div>
                            </li>
                          ))}
                        </ul>
                      </>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </section>
      )}
    </div>
  );
}

export default BotHealthPage;
