import { useQuery } from "@tanstack/react-query";
import { CircleDollarSign, HandCoins, TrendingUp } from "lucide-react";

import { apiRequest } from "@/services/api";

export type FinanceMonth = {
  month: string;
  gross_revenue: string;
  net_revenue: string;
  sale_count: number;
  smokepay_gross: string;
  flashbot_gross: string;
  collaborator_earnings: string;
  collaborator_paid: string;
  collaborator_due: string;
  profit: string;
};

const money = (value: string | number | undefined) =>
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

/**
 * Faturado / a pagar aos colaboradores / lucro do mês atual. Rendered as
 * dashboard metric cards, so it drops into any `dashboard-metrics` grid.
 */
export function MonthResultCards() {
  const month = useFinanceMonth();
  if (month.isError) return null; // owner-only figures: hide quietly otherwise
  const data = month.data;
  const monthName = data
    ? new Intl.DateTimeFormat("pt-BR", { month: "long", timeZone: "UTC" }).format(new Date(`${data.month}T00:00:00Z`))
    : "mês";
  const profit = Number(data?.profit ?? 0);
  const cards = [
    {
      title: `Faturado em ${monthName}`,
      icon: <CircleDollarSign size={16} />,
      color: "text-accent",
      value: money(data?.gross_revenue),
      valueColor: "text-fg",
      detail: data
        ? `${data.sale_count} venda(s) · líquido ${money(data.net_revenue)}`
        : "Somando SmokePay e FlashBot",
    },
    {
      title: "A pagar aos colaboradores",
      icon: <HandCoins size={16} />,
      color: "text-warning",
      value: money(data?.collaborator_due),
      valueColor: "text-warning",
      detail: data
        ? `Ganharam ${money(data.collaborator_earnings)} · já pago ${money(data.collaborator_paid)}`
        : "Ganhos do mês menos o que já foi pago",
    },
    {
      title: `Lucro de ${monthName}`,
      icon: <TrendingUp size={16} />,
      color: profit < 0 ? "text-danger" : "text-success",
      value: money(data?.profit),
      valueColor: profit < 0 ? "text-danger" : "text-success",
      detail: "Faturamento líquido menos os ganhos dos colaboradores",
    },
  ];
  return (
    <>
      {cards.map((card) => (
        <article aria-busy={month.isLoading} className="dashboard-card dashboard-metric-card" key={card.title}>
          <div className="dashboard-metric-heading">
            <span className={`dashboard-metric-icon ${card.color}`}>{card.icon}</span>
            <h2 className="dashboard-metric-title">{card.title}</h2>
          </div>
          <p className={`dashboard-metric-value ${card.valueColor}`}>{month.isLoading ? "…" : card.value}</p>
          <p className="dashboard-metric-detail">{card.detail}</p>
        </article>
      ))}
    </>
  );
}
