import { useQuery } from "@tanstack/react-query";

import { ErrorState, LoadingState } from "@/components/PageState";
import { isPeriodReady, periodParams, type MetricsPeriod } from "@/features/analytics/period";
import { apiRequest } from "@/services/api";

type FunnelBot = {
  bot_id: string;
  bot_name: string;
  leads: number;
  pix: number;
  sales: number;
  revenue: number;
  lead_to_pix: number | null;
  pix_to_sale: number | null;
  upsells: { step: number; offered: number; pix: number; paid: number; revenue: number; take_rate: number | null }[];
};

const count = (value: number) => new Intl.NumberFormat("pt-BR").format(value);
const brl = (value: number) => new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(value);
const rate = (value: number | null) => (value === null ? "—" : `${value.toLocaleString("pt-BR")}%`);

function Stage({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-line-soft bg-surface-inset px-3 py-2">
      <p className="truncate text-[11px] text-muted">{label}</p>
      <p className="mt-0.5 text-base font-semibold text-fg tabular-nums">{value}</p>
      {hint && <p className="truncate text-[10px] text-accent">{hint}</p>}
    </div>
  );
}

/** Flash bot funnel per bot, down to each upsell step (where buyers stop). */
export function FlashFunnelPanel({ period }: { period: MetricsPeriod }) {
  const params = new URLSearchParams(periodParams(period));
  const funnel = useQuery({
    queryKey: ["analytics", "flash-funnel", params.toString()],
    queryFn: () => apiRequest<{ period_label: string; bots: FunnelBot[] }>(`/api/analytics/flash-funnel?${params}`),
    enabled: isPeriodReady(period),
    retry: false,
    placeholderData: (previous) => previous,
  });
  if (funnel.isLoading) return <LoadingState label="Carregando funil" />;
  if (funnel.error || !funnel.data) return <ErrorState message="Não foi possível carregar o funil." onRetry={() => void funnel.refetch()} />;
  if (funnel.data.bots.length === 0) return null;

  return (
    <section className="dashboard-card space-y-4 rounded-xl p-4 sm:p-5">
      <div>
        <h2 className="font-semibold text-fg">Funil por bot</h2>
        <p className="mt-1 text-xs text-muted">Leads → Pix → venda → cada etapa do upsell · {funnel.data.period_label}</p>
      </div>
      {funnel.data.bots.map((bot) => (
        <article className="space-y-2 border-t border-line-soft pt-3 first:border-0 first:pt-0" key={bot.bot_id}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h3 className="text-sm font-semibold text-fg">{bot.bot_name}</h3>
            <span className="text-sm font-semibold text-success">{brl(bot.revenue)}</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stage label="Leads" value={count(bot.leads)} />
            <Stage hint={`${rate(bot.lead_to_pix)} dos leads`} label="Pix gerados" value={count(bot.pix)} />
            <Stage hint={`${rate(bot.pix_to_sale)} dos Pix`} label="Vendas" value={count(bot.sales)} />
          </div>
          {bot.upsells.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-line-soft">
              <table className="w-full min-w-[460px] text-left text-xs">
                <thead className="text-muted">
                  <tr className="border-b border-line-soft">
                    <th className="px-3 py-2 font-medium">Upsell</th>
                    <th className="px-2 py-2 text-right font-medium">Enviados</th>
                    <th className="px-2 py-2 text-right font-medium">Pix</th>
                    <th className="px-2 py-2 text-right font-medium">Pagos</th>
                    <th className="px-2 py-2 text-right font-medium">Aceite</th>
                    <th className="px-3 py-2 text-right font-medium">Faturado</th>
                  </tr>
                </thead>
                <tbody>
                  {bot.upsells.map((step) => (
                    <tr className="border-b border-line-soft last:border-0" key={step.step}>
                      <td className="px-3 py-2 text-fg">Etapa {step.step}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{count(step.offered)}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{count(step.pix)}</td>
                      <td className="px-2 py-2 text-right tabular-nums">{count(step.paid)}</td>
                      <td className="px-2 py-2 text-right font-semibold text-accent">{rate(step.take_rate)}</td>
                      <td className="px-3 py-2 text-right text-success">{brl(step.revenue)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </article>
      ))}
    </section>
  );
}
