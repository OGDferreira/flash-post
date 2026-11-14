import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { MessageCircle, Receipt, Users } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { CopyField } from "@/components/ui/CopyField";
import { apiRequest } from "@/services/api";
import { ConversationModal } from "./ConversationModal";
import { brl, type BotLead, type BotOrder, type BotsConfig, type BotsSummary, type LeadAudience } from "./types";

const AUDIENCES: { id: LeadAudience; label: string }[] = [
  { id: "all", label: "Todos" },
  { id: "paid", label: "Pagantes" },
  { id: "pix_unpaid", label: "Gerou e não pagou" },
  { id: "no_pix", label: "Não gerou Pix" },
];

function ChatButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label="Abrir conversa do lead"
      title="Abrir conversa"
      className="btn-ghost !min-h-8 !gap-1 !px-2 !text-xs text-accent"
    >
      <MessageCircle size={15} /> Conversa
    </button>
  );
}

const periods = [
  { days: 1, label: "Hoje" },
  { days: 7, label: "7 dias" },
  { days: 30, label: "30 dias" },
];

const statusBadge: Record<BotOrder["status"], { tone: "success" | "warning" | "danger" | "neutral"; label: string }> = {
  paid: { tone: "success", label: "Pago" },
  pending: { tone: "warning", label: "Aguardando" },
  expired: { tone: "neutral", label: "Expirado" },
  review: { tone: "danger", label: "Revisar valor" },
  failed: { tone: "danger", label: "Falhou" },
};

const dateTime = (value: string | null) =>
  value ? new Date(value).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : "—";

export function BotSalesPanel() {
  const [days, setDays] = useState(1);
  const [chatLead, setChatLead] = useState<string | null>(null);
  const [audience, setAudience] = useState<LeadAudience>("all");
  const leads = useQuery({
    queryKey: ["bots", "leads", audience],
    queryFn: () => apiRequest<{ leads: BotLead[] }>(`/api/bots/leads?audience=${audience}`),
    retry: false,
    refetchInterval: 30_000,
  });
  const summary = useQuery({
    queryKey: ["bots", "summary", days],
    queryFn: () => apiRequest<BotsSummary>(`/api/bots/summary?days=${days}`),
    retry: false,
    refetchInterval: 30_000,
  });
  const orders = useQuery({
    queryKey: ["bots", "orders"],
    queryFn: () => apiRequest<{ orders: BotOrder[] }>("/api/bots/orders/list?limit=100"),
    retry: false,
    refetchInterval: 30_000,
  });
  const config = useQuery({ queryKey: ["bots", "config"], queryFn: () => apiRequest<BotsConfig>("/api/bots/config"), retry: false });

  return (
    <div className="space-y-4">
      {config.data && !(config.data.smokepay_configured && config.data.smokepay_webhook_configured) && (
        <ErrorState message="SmokePay não configurado no servidor: defina SMOKEPAY_API_KEY e SMOKEPAY_WEBHOOK_SECRET. Sem isso o bot não gera Pix." />
      )}
      <div className="inline-flex gap-1 rounded-full bg-well p-1" role="tablist" aria-label="Período">
        {periods.map((period) => (
          <button
            aria-selected={days === period.days}
            className={`min-h-9 rounded-full px-4 text-xs font-medium ${days === period.days ? "bg-brand text-white" : "text-muted"}`}
            key={period.days}
            onClick={() => setDays(period.days)}
            role="tab"
            type="button"
          >
            {period.label}
          </button>
        ))}
      </div>
      {summary.isLoading ? (
        <LoadingState label="Carregando resumo" />
      ) : summary.data ? (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
          {[
            ["Leads", String(summary.data.leads)],
            ["Pix gerados", String(summary.data.pix_generated)],
            ["Pix pagos", String(summary.data.pix_paid)],
            ["Conversão", `${summary.data.conversion.toLocaleString("pt-BR")}%`],
            ["Faturamento", brl(summary.data.revenue)],
          ].map(([label, value]) => (
            <Card key={label} className="text-center">
              <p className="text-xs text-muted">{label}</p>
              <p className="mt-1 text-lg font-semibold text-fg">{value}</p>
            </Card>
          ))}
        </div>
      ) : (
        <ErrorState message="Não foi possível carregar o resumo." onRetry={() => void summary.refetch()} />
      )}

      <Card className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-medium text-fg">Leads</h3>
          <div className="inline-flex flex-wrap gap-1 rounded-full bg-well p-1" role="tablist" aria-label="Filtrar leads">
            {AUDIENCES.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={audience === item.id}
                onClick={() => setAudience(item.id)}
                className={`min-h-8 rounded-full px-3 text-xs font-medium ${audience === item.id ? "bg-brand text-white" : "text-muted"}`}
              >
                {item.label}
              </button>
            ))}
          </div>
        </div>
        {leads.isLoading ? (
          <LoadingState label="Carregando leads" />
        ) : !leads.data ? (
          <ErrorState message="Não foi possível carregar os leads." onRetry={() => void leads.refetch()} />
        ) : leads.data.leads.length === 0 ? (
          <EmptyState icon={<Users size={18} />} message="Nenhum lead neste filtro." />
        ) : (
          <ul className="divide-y divide-line-soft">
            {leads.data.leads.map((lead) => (
              <li key={lead.id} className="flex items-center gap-3 py-2">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-fg">
                    {lead.name}
                    {lead.username && <span className="text-xs text-muted"> · @{lead.username}</span>}
                  </span>
                  <span className="block text-xs text-muted">@{lead.bot}</span>
                </span>
                <Badge tone={lead.paid ? "success" : lead.has_pix ? "warning" : "neutral"}>
                  {lead.paid ? "Pagou" : lead.has_pix ? "Gerou Pix" : "Sem Pix"}
                </Badge>
                <ChatButton onClick={() => setChatLead(lead.id)} />
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card className="space-y-3">
        <h3 className="font-medium text-fg">Últimos pedidos</h3>
        {orders.isLoading ? (
          <LoadingState label="Carregando pedidos" />
        ) : !orders.data ? (
          <ErrorState message="Não foi possível carregar os pedidos." onRetry={() => void orders.refetch()} />
        ) : orders.data.orders.length === 0 ? (
          <EmptyState icon={<Receipt size={18} />} message="Nenhum Pix gerado ainda." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-left text-sm">
              <thead className="text-xs text-muted">
                <tr>
                  <th className="py-2 pr-3 font-medium">Lead</th>
                  <th className="py-2 pr-3 font-medium">Plano</th>
                  <th className="py-2 pr-3 font-medium">Valor</th>
                  <th className="py-2 pr-3 font-medium">Status</th>
                  <th className="py-2 pr-3 font-medium">Bot / origem</th>
                  <th className="py-2 pr-3 font-medium">Criado</th>
                  <th className="py-2 font-medium">Conversa</th>
                </tr>
              </thead>
              <tbody>
                {orders.data.orders.map((order) => (
                  <tr className="border-t border-line-soft" key={order.id}>
                    <td className="py-2 pr-3 text-fg">
                      {order.lead ?? "—"}
                      {order.lead_username && <span className="block text-xs text-muted">@{order.lead_username}</span>}
                    </td>
                    <td className="py-2 pr-3 text-fg-2">{order.plan}</td>
                    <td className="py-2 pr-3 text-fg">{brl(order.amount)}</td>
                    <td className="py-2 pr-3">
                      <Badge tone={statusBadge[order.status].tone}>{statusBadge[order.status].label}</Badge>
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted">
                      @{order.bot}
                      {order.source && <span className="block">origem: {order.source}</span>}
                    </td>
                    <td className="py-2 pr-3 text-xs text-muted">{dateTime(order.paid_at ?? order.created_at)}</td>
                    <td className="py-2">
                      <ChatButton onClick={() => setChatLead(order.lead_id)} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {config.data && (
        <Card tone="inset">
          <CopyField
            label="URL de notificação do SmokePay (configurada automaticamente em cada Pix)"
            value={config.data.payment_webhook_url}
            hint="Não precisa cadastrar: o bot envia essa URL junto de cada cobrança."
          />
        </Card>
      )}
      <ConversationModal leadId={chatLead} onClose={() => setChatLead(null)} />
    </div>
  );
}
