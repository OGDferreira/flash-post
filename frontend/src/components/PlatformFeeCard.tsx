import { useQuery } from "@tanstack/react-query";
import { HandCoins } from "lucide-react";

import { MetricCard, money } from "@/components/MonthResultCards";
import { apiRequest, type AdminSummary } from "@/services/api";

/** Super Admin: what the Falcon Bot fee per sale brought in today, with the Pix behind it. */
export function PlatformFeeCard() {
  const summary = useQuery({
    queryKey: ["admin", "summary"],
    queryFn: () => apiRequest<AdminSummary>("/api/admin/summary"),
    refetchInterval: 60_000,
  });
  if (summary.isError) return null;
  const data = summary.data;
  const pix = (count: number) => `${count} pix`;
  return (
    <MetricCard
      color="text-success"
      detail={data ? `${pix(data.fee_pix_generated_today)} gerados e ${data.fee_pix_paid_today} pagos` : "Pix gerados e pagos hoje"}
      icon={<HandCoins size={16} />}
      loading={summary.isLoading}
      title="Arrecadação Falcon Bot hoje"
      value={money(data?.transaction_fees_today)}
      valueColor="text-success"
    />
  );
}
