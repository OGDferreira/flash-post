import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { CalendarDays, CircleDollarSign, HandCoins, TrendingUp } from "lucide-react";

import { TrendBadge } from "@/components/TrendBadge";
import { apiRequest } from "@/services/api";

type Money = string;

export type FinanceMonth = {
  month: string;
  gross_revenue: Money;
  net_revenue: Money;
  sale_count: number;
  sharkbot_gross: Money;
  sharkbot_sales_without_amount: number;
  flashbot_gross: Money;
  collaborator_earnings: Money;
  collaborator_paid: Money;
  collaborator_due: Money;
  expenses_total: Money;
  expenses: { id: string; amount: Money; description: string; spent_at: string }[];
  profit: Money;
  month_days_elapsed: number;
  today: {
    gross_revenue: Money;
    net_revenue: Money;
    sale_count: number;
    collaborator_earnings: Money;
    expenses_total: Money;
    profit: Money;
  };
  history_days: number | null;
  history_per_day: {
    gross_revenue: Money;
    net_revenue: Money;
    collaborator_earnings: Money;
    expenses_total: Money;
    profit: Money;
    leads: number;
    pix_generated: number;
    pix_paid: number;
  } | null;
};

export const money = (value: string | number | undefined) =>
  value === undefined
    ? "—"
    : new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" }).format(Number(value));

export function useFinanceMonth() {
  return useQuery({
    queryKey: ["finance", "month"],
    queryFn: () => apiRequest<FinanceMonth>("/api/finance/month"),
    retry: false,
    refetchInterval: 60_000,
  });
}

/** Month-to-date per-day value vs the all-time daily average (fair even mid-month). */
export function MonthTrend({ data, field, inverse }: { data: FinanceMonth; field: "gross_revenue" | "collaborator_earnings" | "expenses_total" | "profit"; inverse?: boolean }) {
  const history = data.history_per_day;
  if (!history || !data.history_days || data.history_days < 2) return null;
  return (
    <TrendBadge
      average={Number(history[field])}
      averageLabel={`${money(history[field])}/dia`}
      current={Number(data[field]) / Math.max(1, data.month_days_elapsed)}
      inverse={inverse}
    />
  );
}

export function MetricCard({
  title,
  icon,
  color,
  value,
  valueColor,
  detail,
  trend,
  loading,
}: {
  title: string;
  icon: ReactNode;
  color: string;
  value: string;
  valueColor: string;
  detail: string;
  trend?: ReactNode;
  loading: boolean;
}) {
  return (
    <article aria-busy={loading} className="dashboard-card dashboard-metric-card">
      <div className="dashboard-metric-heading">
        <span className={`dashboard-metric-icon ${color}`}>{icon}</span>
        <h2 className="dashboard-metric-title">{title}</h2>
      </div>
      <p className={`dashboard-metric-value ${valueColor}`}>{loading ? "…" : value}</p>
      {trend}
      <p className="dashboard-metric-detail">{detail}</p>
    </article>
  );
}

/**
 * Faturado hoje / a pagar aos colaboradores / lucro do mês / lucro de hoje, each with
 * an indicator against the all-time daily average. Rendered as dashboard metric
 * cards, so it drops into any `dashboard-metrics` grid.
 */
export function MonthResultCards({
  hideCollaboratorDue = false,
  hideMonthlyProfit = false,
}: { hideCollaboratorDue?: boolean; hideMonthlyProfit?: boolean } = {}) {
  const month = useFinanceMonth();
  if (month.isError) return null; // owner-only figures: hide quietly otherwise
  const data = month.data;
  const loading = month.isLoading;
  const monthName = data
    ? new Intl.DateTimeFormat("pt-BR", { month: "long", timeZone: "UTC" }).format(new Date(`${data.month}T00:00:00Z`))
    : "mês";
  const todayProfit = Number(data?.today.profit ?? 0);
  const history = data?.history_per_day;
  const showTrend = Boolean(data && history && (data.history_days ?? 0) >= 2);

  return (
    <>
      <MetricCard
        color="text-accent"
        detail={data ? `${data.today.sale_count} venda(s) hoje · Sharkbot e FlashBot` : "Somando Sharkbot e FlashBot"}
        icon={<CircleDollarSign size={16} />}
        loading={loading}
        title="Faturado hoje"
        trend={
          showTrend && data && history ? (
            <TrendBadge average={Number(history.gross_revenue)} averageLabel={`${money(history.gross_revenue)}/dia`} current={Number(data.today.gross_revenue)} />
          ) : undefined
        }
        value={money(data?.today.gross_revenue)}
        valueColor="text-fg"
      />
      {!hideCollaboratorDue && (
        <MetricCard
          color="text-warning"
          detail={
            data
              ? `Custo da equipe no mês ${money(data.collaborator_earnings)} = já pago ${money(data.collaborator_paid)} + a pagar ${money(data.collaborator_due)}`
              : "Ganhos do mês menos o que já foi pago"
          }
          icon={<HandCoins size={16} />}
          loading={loading}
          title="A pagar aos colaboradores"
          trend={data && <MonthTrend data={data} field="collaborator_earnings" inverse />}
          value={money(data?.collaborator_due)}
          valueColor="text-warning"
        />
      )}
      {!hideMonthlyProfit && (
        <MetricCard
          color={Number(data?.profit ?? 0) < 0 ? "text-danger" : "text-success"}
          detail={
            data
              ? `Líquido ${money(data.net_revenue)} − equipe ${money(data.collaborator_earnings)} − gastos ${money(data.expenses_total)}`
              : "Faturamento menos equipe e gastos"
          }
          icon={<TrendingUp size={16} />}
          loading={loading}
          title={`Lucro de ${monthName}`}
          trend={data && <MonthTrend data={data} field="profit" />}
          value={money(data?.profit)}
          valueColor={Number(data?.profit ?? 0) < 0 ? "text-danger" : "text-success"}
        />
      )}
      <MetricCard
        color={todayProfit < 0 ? "text-danger" : "text-success"}
        detail={
          data
            ? `Faturou ${money(data.today.gross_revenue)} (${data.today.sale_count} venda(s)) − equipe ${money(data.today.collaborator_earnings)} − gastos ${money(data.today.expenses_total)}`
            : "Faturamento de hoje menos equipe e gastos"
        }
        icon={<CalendarDays size={16} />}
        loading={loading}
        title="Lucro de hoje"
        trend={
          showTrend && data && history ? (
            <TrendBadge average={Number(history.profit)} averageLabel={`${money(history.profit)}/dia`} current={todayProfit} />
          ) : undefined
        }
        value={money(data?.today.profit)}
        valueColor={todayProfit < 0 ? "text-danger" : "text-success"}
      />
    </>
  );
}
