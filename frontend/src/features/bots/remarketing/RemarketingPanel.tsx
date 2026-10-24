import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BarChart3, Ban, CalendarClock, CheckCircle2, CircleDollarSign, Megaphone, Pause, Plus, RefreshCw, Repeat, Settings2, Trash2, Users, Workflow, XCircle } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { confirmAction } from "@/lib/confirm";
import { ApiError, apiRequest } from "@/services/api";
import { brl, type Campaign, type Flow, type RecurrenceKind } from "../types";
import { CampaignEditor } from "./CampaignEditor";
import { CampaignStats, recurrenceLabel, statusLabel } from "./CampaignStats";

const WEEKDAYS: { value: number; label: string }[] = [
  { value: 0, label: "Seg" },
  { value: 1, label: "Ter" },
  { value: 2, label: "Qua" },
  { value: 3, label: "Qui" },
  { value: 4, label: "Sex" },
  { value: 5, label: "Sáb" },
  { value: 6, label: "Dom" },
];

const SCHEDULE_MODES: { value: RecurrenceKind | "once"; label: string }[] = [
  { value: "once", label: "Uma vez" },
  { value: "daily", label: "Diariamente" },
  { value: "hours", label: "A cada X horas" },
  { value: "weekdays", label: "Dias da semana" },
];

const STATUS_TONE: Record<Campaign["status"], string> = {
  draft: "border-line bg-well text-muted",
  scheduled: "border-brand/40 bg-brand-soft text-accent",
  sending: "border-warning/40 bg-warning-soft text-warning",
  finished: "border-line bg-well text-fg-2",
  paused: "border-danger/40 bg-danger-soft text-danger",
};

const localInput = (date: Date) => {
  const shifted = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return shifted.toISOString().slice(0, 16);
};

/**
 * Remarketing like SharkBot's: campaigns grouped by funnel, each card with its
 * numbers and actions (send, schedule, stats, edit, delete). ``flowId`` narrows
 * the list to one funnel (the "Remarketing" button on a funnel card).
 */
export function RemarketingPanel({
  flowId,
  onFlowChange,
  onEditingChange,
}: {
  flowId: string | null;
  onFlowChange: (flowId: string | null) => void;
  onEditingChange?: (editing: boolean) => void;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<Campaign | "new" | null>(null);
  const [statsFor, setStatsFor] = useState<Campaign | null>(null);
  const [scheduling, setScheduling] = useState<Campaign | null>(null);
  const [scheduleAt, setScheduleAt] = useState("");
  const [schedMode, setSchedMode] = useState<RecurrenceKind | "once">("once");
  const [schedTime, setSchedTime] = useState("09:00");
  const [schedHours, setSchedHours] = useState(24);
  const [schedDays, setSchedDays] = useState<number[]>([]);
  useEffect(() => onEditingChange?.(editing !== null), [editing, onEditingChange]);

  const flows = useQuery({ queryKey: ["bots", "flows"], queryFn: () => apiRequest<{ flows: Flow[] }>("/api/bots/flows/list"), retry: false });
  const campaigns = useQuery({
    queryKey: ["bots", "campaigns"],
    queryFn: () => apiRequest<{ campaigns: Campaign[] }>("/api/bots/campaigns"),
    retry: false,
    refetchInterval: (query) => (query.state.data?.campaigns.some((item) => item.status === "sending" || item.status === "scheduled") ? 5_000 : false),
  });
  const refresh = () => void queryClient.invalidateQueries({ queryKey: ["bots", "campaigns"] });
  const action = useMutation({
    mutationFn: ({ campaign, path, body, method = "POST" }: { campaign: Campaign; path: string; body?: unknown; method?: "POST" | "DELETE" }) =>
      apiRequest<Campaign | void>(`/api/bots/campaigns/${campaign.id}${path}`, { method, body }),
    onSuccess: () => {
      setScheduling(null);
      refresh();
    },
  });

  if (flows.isLoading || campaigns.isLoading) return <LoadingState label="Carregando remarketing" />;
  if (!flows.data || !campaigns.data) {
    return <ErrorState message="Não foi possível carregar o remarketing." onRetry={() => void campaigns.refetch()} />;
  }
  const allFlows = flows.data.flows;
  if (editing) {
    return (
      <CampaignEditor
        campaign={editing === "new" ? null : editing}
        defaultFlowId={flowId}
        flows={allFlows}
        key={editing === "new" ? "new" : editing.id}
        onClose={() => setEditing(null)}
      />
    );
  }
  const shown = allFlows.filter((flow) => !flowId || flow.id === flowId);
  const byFlow = new Map<string, Campaign[]>();
  for (const campaign of campaigns.data.campaigns) byFlow.set(campaign.flow_id, [...(byFlow.get(campaign.flow_id) ?? []), campaign]);
  const groups = shown.filter((flow) => flowId || byFlow.has(flow.id));

  const send = async (campaign: Campaign) => {
    if (campaign.status === "sending") {
      action.mutate({ campaign, path: "/pause" });
      return;
    }
    if (campaign.status === "paused" && (await confirmAction("Continuar o envio de onde parou? (Cancelar = escolher enviar de novo para todos)"))) {
      action.mutate({ campaign, path: "/send?resume=true" });
      return;
    }
    const again = campaign.runs > 0 ? " Quem já recebeu recebe de novo." : "";
    if (await confirmAction(`Enviar “${campaign.name}” agora?${again}`)) action.mutate({ campaign, path: "/send" });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm text-muted">Cada funil tem o próprio remarketing: a campanha vai para os leads daquele funil, pelo bot onde cada um entrou.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <select aria-label="Funil" className="field !min-h-10 !w-auto" value={flowId ?? ""} onChange={(event) => onFlowChange(event.target.value || null)}>
            <option value="">Todos os funis</option>
            {allFlows.map((flow) => (
              <option key={flow.id} value={flow.id}>
                {flow.name}
              </option>
            ))}
          </select>
          <Button disabled={allFlows.length === 0} onClick={() => setEditing("new")} variant="primary">
            <Plus size={16} /> Nova campanha
          </Button>
        </div>
      </div>
      {action.error && <ErrorState message={action.error instanceof ApiError ? action.error.message : "A ação não pôde ser concluída."} />}
      {allFlows.length === 0 ? (
        <EmptyState icon={<Workflow size={18} />} message="Crie um funil primeiro: o remarketing é feito por funil." />
      ) : groups.length === 0 ? (
        <EmptyState icon={<Megaphone size={18} />} message="Nenhuma campanha ainda. Toque em “Nova campanha” para chamar de volta os leads de um funil." />
      ) : (
        groups.map((flow) => {
          const items = byFlow.get(flow.id) ?? [];
          const sent = items.reduce((sum, item) => sum + item.sent, 0);
          const revenue = items.reduce((sum, item) => sum + Number(item.revenue), 0);
          return (
            <section className="overflow-hidden rounded-2xl border border-line bg-surface" key={flow.id}>
              <header className="flex flex-wrap items-center gap-3 border-b border-line p-4">
                <span className="grid size-11 place-items-center rounded-xl border border-brand/30 bg-brand-soft text-accent">
                  <Workflow size={19} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate font-semibold text-fg">{flow.name}</p>
                  <p className="text-xs text-muted">
                    {items.length} campanha{items.length === 1 ? "" : "s"} · {sent.toLocaleString("pt-BR")} enviadas · <span className="text-accent">{brl(revenue)}</span>
                  </p>
                </div>
                {flowId && (
                  <Button onClick={() => setEditing("new")} size="sm">
                    <Plus size={14} /> Campanha neste funil
                  </Button>
                )}
              </header>
              {items.length === 0 ? (
                <p className="p-4 text-sm text-muted">Nenhuma campanha neste funil.</p>
              ) : (
                <div className="grid gap-3 p-3 sm:p-4 md:grid-cols-2 2xl:grid-cols-3">
                  {items.map((campaign) => (
                    <article className="grid gap-4 rounded-2xl border border-line bg-surface-inset p-4" key={campaign.id}>
                      <div className="flex items-start gap-3">
                        <span className="grid size-10 shrink-0 place-items-center rounded-xl border border-line bg-well text-fg-2">
                          <Megaphone size={17} />
                        </span>
                        <div className="min-w-0">
                          <p className="truncate font-semibold text-fg">{campaign.name}</p>
                          <span className={`mt-1 inline-flex rounded-full border px-2.5 py-0.5 text-xs font-medium ${STATUS_TONE[campaign.status]}`}>
                            {statusLabel(campaign.status)}
                            {campaign.status === "scheduled" && campaign.scheduled_at
                              ? ` · ${new Date(campaign.scheduled_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}`
                              : ""}
                          </span>
                          {campaign.recurrence && (
                            <span className="mt-1 ml-1 inline-flex items-center gap-1 rounded-full border border-brand/30 bg-brand-soft px-2 py-0.5 text-xs font-medium text-accent">
                              <Repeat size={11} /> {recurrenceLabel(campaign.recurrence)}
                            </span>
                          )}
                        </div>
                      </div>
                      {campaign.conflicts.length > 0 && (campaign.status === "scheduled" || campaign.recurrence) && (
                        <p className="flex items-start gap-1.5 rounded-xl border border-warning/30 bg-warning-soft px-3 py-2 text-xs leading-5 text-warning">
                          <AlertTriangle className="mt-0.5 shrink-0" size={13} />
                          <span>
                            Conflito: {campaign.conflicts.map((other) => other.name).join(", ")} também dispara
                            {campaign.conflicts.length === 1 ? "" : "m"} para este público. Os leads podem receber mais de uma mensagem.
                          </span>
                        </p>
                      )}
                      <dl className="grid grid-cols-3 gap-2">
                        <div>
                          <dt className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
                            <Users size={11} /> Total
                          </dt>
                          <dd className="text-xl font-semibold text-fg">{campaign.total.toLocaleString("pt-BR")}</dd>
                        </div>
                        <div>
                          <dt className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
                            <CheckCircle2 size={11} /> Enviadas
                          </dt>
                          <dd className="text-xl font-semibold text-success">{campaign.sent.toLocaleString("pt-BR")}</dd>
                        </div>
                        <div>
                          <dt className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-muted">
                            <CircleDollarSign size={11} /> Receita
                          </dt>
                          <dd className="text-xl font-semibold text-fg">{brl(campaign.revenue)}</dd>
                        </div>
                      </dl>
                      <div className="flex flex-wrap items-center justify-between gap-2 border-t border-line-soft pt-3 text-xs text-muted">
                        <span className="flex items-center gap-1">
                          <Ban size={12} /> {(campaign.already_blocked + campaign.blocked).toLocaleString("pt-BR")} já bloqueados
                          {campaign.status === "sending" && ` · ${Math.max(0, campaign.total - campaign.sent - campaign.failed - campaign.blocked).toLocaleString("pt-BR")} no envio`}
                        </span>
                        <span className="flex items-center gap-1">
                          <XCircle size={12} /> {campaign.failed.toLocaleString("pt-BR")} falhas
                        </span>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <button
                          aria-label={campaign.status === "sending" ? "Pausar envio" : "Enviar agora"}
                          className="flex min-h-10 flex-1 items-center justify-center gap-1.5 rounded-xl border border-line bg-surface text-sm font-medium text-accent hover:border-brand disabled:opacity-50"
                          disabled={action.isPending}
                          onClick={() => void send(campaign)}
                          type="button"
                        >
                          {campaign.status === "sending" ? <Pause size={16} /> : <RefreshCw size={16} />}
                          {campaign.status === "sending" ? "Pausar" : campaign.status === "paused" ? "Continuar" : campaign.runs ? "Enviar de novo" : "Enviar"}
                        </button>
                        <button
                          aria-label="Agendar"
                          className="grid size-10 place-items-center rounded-xl border border-brand/40 bg-brand-soft text-accent disabled:opacity-50"
                          disabled={campaign.status === "sending"}
                          onClick={() => {
                            const recurrence = campaign.recurrence;
                            setSchedMode(recurrence ? recurrence.kind : "once");
                            setSchedTime(recurrence?.time ?? "09:00");
                            setSchedHours(recurrence?.hours ?? 24);
                            setSchedDays(recurrence?.weekdays ?? []);
                            setScheduleAt(campaign.scheduled_at && !recurrence ? localInput(new Date(campaign.scheduled_at)) : localInput(new Date(Date.now() + 3_600_000)));
                            setScheduling(campaign);
                          }}
                          type="button"
                        >
                          <CalendarClock size={16} />
                        </button>
                        <button aria-label="Estatísticas" className="btn-ghost !min-h-10 !px-2" onClick={() => setStatsFor(campaign)} type="button">
                          <BarChart3 size={16} />
                        </button>
                        <button aria-label="Editar" className="btn-ghost !min-h-10 !px-2" onClick={() => setEditing(campaign)} type="button">
                          <Settings2 size={16} />
                        </button>
                        <button
                          aria-label="Excluir"
                          className="btn-ghost !min-h-10 !px-2 text-danger"
                          onClick={async () => {
                            if (await confirmAction(`Excluir a campanha “${campaign.name}”?`)) action.mutate({ campaign, path: "", method: "DELETE" });
                          }}
                          type="button"
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </section>
          );
        })
      )}
      {statsFor && <CampaignStats campaign={campaigns.data.campaigns.find((item) => item.id === statsFor.id) ?? statsFor} open onClose={() => setStatsFor(null)} />}
      <Modal
        open={scheduling !== null}
        title="Agendar envio"
        description={scheduling?.name}
        onClose={() => setScheduling(null)}
        busy={action.isPending}
        footer={
          <div className="flex flex-wrap justify-end gap-2">
            {(scheduling?.status === "scheduled" || scheduling?.recurrence) && (
              <Button disabled={action.isPending} onClick={() => scheduling && action.mutate({ campaign: scheduling, path: "/schedule", body: { scheduled_at: null, recurrence: null } })}>
                Cancelar agendamento
              </Button>
            )}
            <Button
              disabled={
                action.isPending ||
                (schedMode === "once" && !scheduleAt) ||
                (schedMode === "weekdays" && schedDays.length === 0)
              }
              onClick={() => {
                if (!scheduling) return;
                const body =
                  schedMode === "once"
                    ? { scheduled_at: new Date(scheduleAt).toISOString(), recurrence: null }
                    : { recurrence: { kind: schedMode, time: schedTime, hours: schedHours, weekdays: schedDays } };
                action.mutate({ campaign: scheduling, path: "/schedule", body });
              }}
              variant="primary"
            >
              Agendar
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div className="grid gap-1.5 text-sm text-fg-2">
            Repetir
            <div className="flex flex-wrap gap-2" role="radiogroup" aria-label="Frequência do envio">
              {SCHEDULE_MODES.map((mode) => (
                <button
                  aria-checked={schedMode === mode.value}
                  className={`min-h-9 rounded-full border px-3 text-sm font-medium transition ${
                    schedMode === mode.value ? "border-brand bg-brand-soft text-accent" : "border-line-soft text-muted hover:text-fg"
                  }`}
                  key={mode.value}
                  onClick={() => setSchedMode(mode.value)}
                  role="radio"
                  type="button"
                >
                  {mode.label}
                </button>
              ))}
            </div>
          </div>

          {schedMode === "once" && (
            <label className="grid gap-1.5 text-sm text-fg-2">
              Data e hora do envio
              <input className="field" min={localInput(new Date())} type="datetime-local" value={scheduleAt} onChange={(event) => setScheduleAt(event.target.value)} />
            </label>
          )}
          {schedMode === "daily" && (
            <label className="grid gap-1.5 text-sm text-fg-2">
              Horário (todos os dias)
              <input className="field !w-40" type="time" value={schedTime} onChange={(event) => setSchedTime(event.target.value)} />
            </label>
          )}
          {schedMode === "hours" && (
            <label className="grid gap-1.5 text-sm text-fg-2">
              A cada quantas horas
              <input className="field !w-40" max={168} min={1} type="number" value={schedHours} onChange={(event) => setSchedHours(Math.min(168, Math.max(1, Number(event.target.value) || 1)))} />
              <span className="text-xs text-muted">O primeiro envio é daqui a {schedHours}h; depois repete nesse intervalo.</span>
            </label>
          )}
          {schedMode === "weekdays" && (
            <div className="space-y-2">
              <div className="grid gap-1.5 text-sm text-fg-2">
                Dias da semana
                <div className="flex flex-wrap gap-1.5">
                  {WEEKDAYS.map((day) => {
                    const on = schedDays.includes(day.value);
                    return (
                      <button
                        aria-checked={on}
                        className={`size-10 rounded-xl border text-sm font-medium transition ${on ? "border-brand bg-brand-soft text-accent" : "border-line-soft text-muted hover:text-fg"}`}
                        key={day.value}
                        onClick={() => setSchedDays((current) => (current.includes(day.value) ? current.filter((value) => value !== day.value) : [...current, day.value].sort((a, b) => a - b)))}
                        role="checkbox"
                        type="button"
                      >
                        {day.label}
                      </button>
                    );
                  })}
                </div>
              </div>
              <label className="grid gap-1.5 text-sm text-fg-2">
                Horário
                <input className="field !w-40" type="time" value={schedTime} onChange={(event) => setSchedTime(event.target.value)} />
              </label>
            </div>
          )}

          {scheduling && scheduling.conflicts.length > 0 && schedMode !== "once" && (
            <p className="flex items-start gap-1.5 rounded-xl border border-warning/30 bg-warning-soft px-3 py-2 text-xs leading-5 text-warning">
              <AlertTriangle className="mt-0.5 shrink-0" size={13} />
              <span>Já há outra campanha ativa para este público ({scheduling.conflicts.map((other) => other.name).join(", ")}). Os mesmos leads podem receber mais de uma mensagem.</span>
            </p>
          )}
        </div>
      </Modal>
    </div>
  );
}
