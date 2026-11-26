import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays } from "lucide-react";

import { PeriodFilter, periodParams, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";
import { brl } from "./api";

type Analytics = {
  period_label?: string;
  summary: { leads: number; generated: number; sales: number; revenue: number; lead_conversion: number; leads_with_pix: number };
  offer_types: { kind: "plan" | "upsell" | "downsell" | "remarketing"; generated: number; sales: number; revenue: number; approval: number }[];
  gateways: { gateway: string; sales: number; revenue: number }[];
};

const KIND_LABEL: Record<string, string> = { plan: "Planos", upsell: "Upsell", downsell: "Downsell", remarketing: "Remarketing" };

function Kpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-well px-3 py-2.5 text-center">
      <p className="text-[10px] uppercase tracking-[0.14em] text-muted">{label}</p>
      <p className="text-lg font-semibold text-fg">{value}</p>
    </div>
  );
}

/** Análises do bot compartilhado, para o parceiro: KPIs, conversão por tipo de oferta e gateways. */
export function SharedBotAnalytics({ botId }: { botId: string }) {
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "today", start: todayInput(), end: todayInput() });
  const query = useQuery({
    queryKey: ["bot-partners", "analytics", botId, period],
    queryFn: () => apiRequest<Analytics>(`/api/bot-partners/shared/${botId}/analytics/full?${new URLSearchParams(periodParams(period))}`),
  });
  const data = query.data;

  return (
    <div className="space-y-4">
      <div className="dashboard-card flex flex-wrap items-center justify-between gap-2 rounded-2xl px-4 py-3">
        <span className="flex items-center gap-2 text-[11px] font-medium uppercase tracking-[0.16em] text-muted">
          <CalendarDays size={14} /> Período {data?.period_label ? `· ${data.period_label}` : ""}
        </span>
        <PeriodFilter onChange={setPeriod} value={period} />
      </div>

      {query.isLoading && <p className="text-sm text-muted">Carregando…</p>}
      {data && (
        <>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
            <Kpi label="Leads" value={String(data.summary.leads)} />
            <Kpi label="Pix gerados" value={String(data.summary.generated)} />
            <Kpi label="Vendas" value={String(data.summary.sales)} />
            <Kpi label="Faturamento" value={brl(data.summary.revenue)} />
            <Kpi label="Lead → venda" value={`${data.summary.lead_conversion}%`} />
            <Kpi label="Leads c/ Pix" value={String(data.summary.leads_with_pix)} />
          </div>

          <div className="overflow-hidden rounded-2xl border border-line bg-surface">
            <div className="border-b border-line px-4 py-2.5 text-sm font-semibold text-fg">Conversão por tipo de oferta</div>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px] text-sm">
                <thead>
                  <tr className="text-left text-[11px] uppercase tracking-wide text-muted">
                    <th className="px-3 py-2">Tipo</th>
                    <th className="px-3 py-2 text-right">Pix</th>
                    <th className="px-3 py-2 text-right">Vendas</th>
                    <th className="px-3 py-2 text-right">Aprovação</th>
                    <th className="px-3 py-2 text-right">Faturamento</th>
                  </tr>
                </thead>
                <tbody>
                  {data.offer_types.map((o) => (
                    <tr key={o.kind} className="border-t border-line/60">
                      <td className="px-3 py-2">{KIND_LABEL[o.kind] ?? o.kind}</td>
                      <td className="px-3 py-2 text-right text-muted">{o.generated}</td>
                      <td className="px-3 py-2 text-right">{o.sales}</td>
                      <td className="px-3 py-2 text-right text-muted">{o.approval}%</td>
                      <td className="px-3 py-2 text-right font-medium">{brl(o.revenue)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {data.gateways.length > 0 && (
            <div className="overflow-hidden rounded-2xl border border-line bg-surface">
              <div className="border-b border-line px-4 py-2.5 text-sm font-semibold text-fg">Gateways</div>
              <ul className="divide-y divide-line/60">
                {data.gateways.map((g) => (
                  <li key={g.gateway} className="flex items-center justify-between px-4 py-2.5 text-sm">
                    <span className="capitalize">{g.gateway}</span>
                    <span className="text-muted">{g.sales} vendas · <span className="font-medium text-fg">{brl(g.revenue)}</span></span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </div>
  );
}
