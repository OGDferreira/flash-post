import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Receipt } from "lucide-react";

import { EmptyState, ErrorState, LoadingState } from "@/components/PageState";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { CopyField } from "@/components/ui/CopyField";
import { apiRequest } from "@/services/api";
import { brl, type BotOrder, type BotsConfig, type BotsSummary } from "./types";

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
        <ErrorState message="SmokePay não configurado no servidor: defina SMOKEPAY_API_KEY e SMOKEPAY_WEBHOOK_SECRET. Sem isso o robô não gera Pix." />
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
                  <th className="py-2 pr-3 font-medium">Robô / origem</th>
                  <th className="py-2 font-medium">Criado</th>
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
                    <td className="py-2 text-xs text-muted">{dateTime(order.paid_at ?? order.created_at)}</td>
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
            hint="Não precisa cadastrar: o robô envia essa URL junto de cada cobrança."
          />
        </Card>
      )}
    </div>
  );
}
