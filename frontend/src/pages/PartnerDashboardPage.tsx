import { useState } from "react";
import { Activity, ChartNoAxesCombined, CircleDollarSign, Clapperboard, UserRoundCheck, UserRoundX, type LucideIcon } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { ErrorState, LoadingState } from "@/components/PageState";
import { PeriodFilter, periodParams, todayInput, type MetricsPeriod } from "@/features/analytics/period";
import type { InstagramAnalyticsSummary } from "@/features/analytics/types";
import { usePartnerMe, brl } from "@/features/partners/api";
import { apiRequest } from "@/services/api";

function Metric({
  label,
  value,
  icon: Icon,
}: {
  label: string;
  value: string;
  icon: LucideIcon;
}) {
  return (
    <div className="min-w-0 rounded-xl border border-line-soft bg-surface-inset px-3 py-3">
      <dt className="flex items-center gap-2 text-xs text-muted">
        <Icon aria-hidden="true" size={15} />
        {label}
      </dt>
      <dd className="mt-2 truncate text-xl font-semibold text-fg" title={value}>{value}</dd>
    </div>
  );
}

export function PartnerDashboardPage() {
  const [period, setPeriod] = useState<MetricsPeriod>({
    period: "today",
    start: todayInput(),
    end: todayInput(),
  });
  const params = periodParams(period);
  const partner = usePartnerMe(params);
  const summary = useQuery({
    queryKey: ["analytics", "summary", "partner-dashboard", params],
    queryFn: () =>
      apiRequest<InstagramAnalyticsSummary>(
        `/api/analytics/summary?${new URLSearchParams(params)}`,
      ),
    enabled: period.period !== "custom" || Boolean(period.start && period.end && period.start <= period.end),
    retry: false,
    staleTime: 60_000,
  });

  if ((partner.isLoading && !partner.data) || (summary.isLoading && !summary.data)) {
    return <LoadingState label="Carregando seu painel" />;
  }
  if (partner.error || summary.error) {
    return (
      <ErrorState
        message="Não foi possível carregar os dados do painel."
        onRetry={() => {
          void partner.refetch();
          void summary.refetch();
        }}
      />
    );
  }

  const metrics = summary.data;
  const sales = partner.data?.totals;
  return (
    <div className="space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold text-fg">Meu painel</h1>
          <p className="mt-1 text-sm text-muted">Acompanhe a atividade e a operação do seu workspace.</p>
        </div>
        <PeriodFilter onChange={setPeriod} showCustom={false} value={period} />
      </header>

      <div className="grid gap-4 xl:grid-cols-2">
        <section aria-labelledby="partner-activity-title" className="dashboard-card glass-panel space-y-4 p-4">
          <h2 className="flex items-center gap-2 text-base font-semibold text-fg" id="partner-activity-title">
            <Activity aria-hidden="true" className="text-accent" size={18} />
            Atividade
          </h2>
          <dl className="grid grid-cols-2 gap-2">
            <Metric
              icon={UserRoundCheck}
              label="Conexões no período"
              value={metrics ? String(metrics.connected_period) : "—"}
            />
            <Metric
              icon={UserRoundX}
              label="Desconexões no período"
              value={metrics ? String(metrics.disconnected_period) : "—"}
            />
          </dl>
        </section>

        <section aria-labelledby="partner-operation-title" className="dashboard-card glass-panel space-y-4 p-4">
          <h2 className="flex items-center gap-2 text-base font-semibold text-fg" id="partner-operation-title">
            <ChartNoAxesCombined aria-hidden="true" className="text-accent" size={18} />
            Operação
          </h2>
          <dl className="grid grid-cols-2 gap-2">
            <Metric
              icon={UserRoundCheck}
              label="Contas ativas"
              value={metrics ? String(metrics.active_accounts) : "—"}
            />
            <Metric
              icon={Clapperboard}
              label="Publicações"
              value={metrics ? String(metrics.published_posts) : "—"}
            />
            <div className="col-span-2">
              <Metric
                icon={CircleDollarSign}
                label="Faturamento bruto"
                value={sales ? brl(sales.gross) : "—"}
              />
            </div>
          </dl>
        </section>
      </div>
    </div>
  );
}
