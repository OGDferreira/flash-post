import { Modal } from "@/components/ui/Modal";
import { brl, type Campaign } from "../types";

const STATUS: Record<Campaign["status"], string> = {
  draft: "Rascunho",
  scheduled: "Agendada",
  sending: "Enviando",
  finished: "Finalizada",
  paused: "Pausada",
};

export function statusLabel(status: Campaign["status"]) {
  return STATUS[status];
}

const when = (value: string | null) => (value ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—");

export function CampaignStats({ campaign, open, onClose }: { campaign: Campaign; open: boolean; onClose: () => void }) {
  const handled = campaign.sent + campaign.failed + campaign.blocked;
  const conversion = campaign.sent ? Math.round((campaign.sales / campaign.sent) * 1000) / 10 : 0;
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
    </Modal>
  );
}
