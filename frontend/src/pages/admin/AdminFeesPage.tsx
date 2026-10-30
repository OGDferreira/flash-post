import { useQuery } from "@tanstack/react-query";

import { PlatformFeeCard as FlashFeeTodayCard } from "@/components/PlatformFeeCard";
import { FeeManagementPanel } from "@/features/partners/FeeManagementPanel";
import { PlatformFeeCard, TransactionFeeCard, type Data } from "@/pages/admin/AdminOperationsPage";
import { apiRequest } from "@/services/api";

/** Super Admin: every fee of the platform in one tab (Flash fee per sale, platform fee). */
export function AdminFeesPage() {
  const operations = useQuery({
    queryKey: ["admin", "operations", { period: "30d" }],
    queryFn: () => apiRequest<Data>("/api/admin/operations?period=30d"),
  });
  return (
    <div className="space-y-4">
      <h2 className="mt-2 text-2xl font-semibold tracking-[-0.045em] text-fg sm:text-3xl">Gerenciamento de Taxas</h2>
      <FlashFeeTodayCard />
      {operations.data && <TransactionFeeCard users={operations.data.users} />}
      <PlatformFeeCard />
      <FeeManagementPanel />
    </div>
  );
}
