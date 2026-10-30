import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { PeriodFilter, isPeriodReady, periodParams, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";
import { brl } from "./api";

type Audit = {
  period_label: string;
  sales: number;
  real: number;
  expected: number;
  difference: number;
  differing_count: number;
  differing: { id: string; offer_name: string; paid_at: string | null; gateway: string | null; real: number; expected: number; difference: number }[];
};

/** Super Admin: the commission really split by the gateway vs. what the rule gives. */
export function CommissionAuditCard() {
  const [period, setPeriod] = useState<MetricsPeriod>({ period: "30d", start: todayInput(), end: todayInput() });
  const params = new URLSearchParams(periodParams(period));
  const audit = useQuery({
    queryKey: ["admin", "commission-audit", params.toString()],
    queryFn: () => apiRequest<Audit>(`/api/admin/commission-audit?${params}`),
    enabled: isPeriodReady(period),
    placeholderData: (previous) => previous,
  });
  const data = audit.data;
  return (
    <section className="glass-panel space-y-3 p-4">
      <h3 className="text-sm font-semibold text-fg">Auditoria de comissões (estimado × real)</h3>
      <p className="text-xs text-muted">
        Na SmokePay e na Athenas o split é definido antes do pagamento, com a taxa do gateway estimada. Aqui você vê a diferença entre o
        que foi dividido e o que a regra (% sobre o líquido após todas as taxas) daria.
      </p>
      <PeriodFilter onChange={setPeriod} value={period} />
      {data && (
        <>
          <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {([
              ["Vendas de sócios", String(data.sales)],
              ["Comissão real", brl(data.real)],
              ["Pela regra", brl(data.expected)],
              ["Diferença", brl(data.difference)],
            ] as const).map(([label, value]) => (
              <div className="rounded-xl border border-line-soft bg-surface-inset px-3 py-2" key={label}>
                <dt className="text-[11px] text-muted">{label}</dt>
                <dd className="mt-1 text-base font-semibold text-fg tabular-nums">{value}</dd>
              </div>
            ))}
          </dl>
          {data.differing_count > 0 ? (
            <div className="overflow-x-auto rounded-xl border border-line-soft">
              <table className="w-full min-w-[460px] text-left text-xs">
                <thead className="text-muted">
                  <tr className="border-b border-line-soft">
                    <th className="px-3 py-2 font-medium">Venda ({data.differing_count} com diferença)</th>
                    <th className="px-2 py-2 text-right font-medium">Real</th>
                    <th className="px-2 py-2 text-right font-medium">Regra</th>
                    <th className="px-3 py-2 text-right font-medium">Dif.</th>
                  </tr>
                </thead>
                <tbody>
                  {data.differing.map((row) => (
                    <tr className="border-b border-line-soft last:border-0" key={row.id}>
                      <td className="px-3 py-2 text-fg">
                        {row.offer_name}
                        <span className="block text-[10px] text-muted">
                          {row.paid_at ? new Date(row.paid_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }) : ""}
                          {row.gateway && ` · ${row.gateway}`}
                        </span>
                      </td>
                      <td className="px-2 py-2 text-right tabular-nums">{brl(row.real)}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{brl(row.expected)}</td>
                      <td className={`px-3 py-2 text-right font-semibold ${row.difference < 0 ? "text-danger" : "text-success"}`}>{brl(row.difference)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-xs text-success">Nenhuma diferença no período.</p>
          )}
        </>
      )}
    </section>
  );
}
