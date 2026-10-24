import { useQuery } from "@tanstack/react-query";

import { LoadingState } from "@/components/PageState";
import { Modal } from "@/components/ui/Modal";
import { apiRequest } from "@/services/api";
import { brl, type Campaign, type CampaignRun, type Recurrence } from "../types";

const STATUS: Record<Campaign["status"], string> = {
  draft: "Rascunho",
  scheduled: "Agendada",
  sending: "Enviando",
  finished: "Finalizada",
  paused: "Pausada",
};

const RUN_STATUS: Record<string, string> = { sending: "Enviando", finished: "Concluído", paused: "Pausado" };

const WEEKDAY_LABELS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];

export function statusLabel(status: Campaign["status"]) {
  return STATUS[status];
}

/** Short pt-BR summary of a recurrence, e.g. "A cada 6h" or "Seg, Qua às 09:00". */
export function recurrenceLabel(recurrence: Recurrence): string {
  if (recurrence.kind === "hours") return `A cada ${recurrence.hours}h`;
  if (recurrence.kind === "daily") return `Diário às ${recurrence.time}`;
  const days = recurrence.weekdays.map((day) => WEEKDAY_LABELS[day]).join(", ");
  return `${days || "—"} às ${recurrence.time}`;
}

const when = (value: string | null) => (value ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");

export function CampaignStats({ campaign, open, onClose }: { campaign: Campaign; open: boolean; onClose: () => void }) {
  const handled = campaign.sent + campaign.failed + campaign.blocked;
  const conversion = campaign.sent ? Math.round((campaign.sales / campaign.sent) * 1000) / 10 : 0;
  const runs = useQuery({
    queryKey: ["bots", "campaigns", campaign.id, "runs"],
    queryFn: () => apiRequest<{ runs: CampaignRun[] }>(`/api/bots/campaigns/${campaign.id}/runs`),
    enabled: open,
    retry: false,
  });
  const rows: [string, string][] = [
    ["Público no disparo", campaign.total.toLocaleString("pt-BR")],
    ["Enviadas", campaign.sent.toLocaleString("pt-BR")],
    ["Bloquearam durante o envio", campaign.blocked.toLocaleString("pt-BR")],
    ["Já tinham bloqueado o bot", campaign.already_blocked.toLocaleString("pt-BR")],
    ["Falhas", campaign.failed.toLocaleString("pt-BR")],
    ["Ainda na fila", Math.max(0, campaign.total - handled).toLocaleString("pt-BR")],
    ["Vendas", campaign.sales.toLocaleString("pt-BR")],
    ["Conversão (vendas ÷ enviadas)", `${conversion.toLocaleString("pt-BR")}%`],
    ["Receita", brl(campaign.revenue)],
    ["Disparos", String(campaign.runs)],
    ...(campaign.recurrence ? ([["Repetição", recurrenceLabel(campaign.recurrence)]] as [string, string][]) : []),
    ...(campaign.status === "scheduled" ? ([["Próximo disparo", when(campaign.scheduled_at)]] as [string, string][]) : []),
    ["Último início", when(campaign.started_at)],
    ["Terminou", when(campaign.finished_at)],
  ];
  return (
    <Modal open={open} title={`Estatísticas · ${campaign.name}`} description={`${statusLabel(campaign.status)} · ${campaign.flow_name}`} onClose={onClose}>
      <dl className="grid gap-1.5 text-sm">
        {rows.map(([label, value]) => (
          <div className="flex justify-between gap-3 rounded-lg bg-surface-inset px-3 py-2" key={label}>
            <dt className="text-muted">{label}</dt>
            <dd className="font-medium text-fg">{value}</dd>
          </div>
        ))}
      </dl>

      <div className="mt-4">
        <h3 className="mb-2 text-sm font-semibold text-fg">Histórico de disparos</h3>
        {runs.isLoading ? (
          <LoadingState label="Carregando histórico" />
        ) : !runs.data || runs.data.runs.length === 0 ? (
          <p className="text-xs text-muted">Nenhum disparo ainda. O histórico aparece aqui a cada envio.</p>
        ) : (
          <ul className="space-y-1.5">
            {runs.data.runs.map((run) => (
              <li className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-line-soft px-3 py-2 text-xs" key={run.id}>
                <span className="font-medium text-fg">{when(run.started_at)}</span>
                <span className="flex items-center gap-2 text-muted">
                  <span className="text-success">{run.sent.toLocaleString("pt-BR")} enviadas</span>
                  {run.failed > 0 && <span className="text-danger">{run.failed} falhas</span>}
                  <span>{RUN_STATUS[run.status] ?? run.status}</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </Modal>
  );
}
