import { useQuery } from "@tanstack/react-query";

import { ErrorState, LoadingState } from "@/components/PageState";
import { usePartnerMe } from "@/features/partners/api";
import { SharedLoopsSection } from "@/features/partners/SharedTemplates";
import { DashboardPage } from "@/pages/DashboardPage";
import type { InstagramLoopsResponse } from "@/pages/loops/loopShared";
import { apiRequest } from "@/services/api";

/** Flash panel of a sócio: the same panel as everyone, with the loops shared with them. */
export function PartnerDashboardPage() {
  const partner = usePartnerMe({ period: "today" });
  const permissions = partner.data?.permissions;
  const canViewAccounts = !permissions || permissions.full_panel || permissions.post.accounts;
  const canViewRanking = !permissions || permissions.full_panel || permissions.post.ranking;
  const sharedLoops = useQuery({
    queryKey: ["loops"],
    queryFn: () => apiRequest<InstagramLoopsResponse>("/api/loops?include_accounts=false"),
    enabled: partner.data?.role === "partner" && canViewAccounts,
    refetchInterval: 120_000,
    retry: false,
  });

  const loops =
    partner.data?.role === "partner" && canViewAccounts ? (
      <div className="space-y-3">
        {sharedLoops.isLoading && <LoadingState label="Carregando loops compartilhados" />}
        {sharedLoops.error && (
          <ErrorState message="Não foi possível carregar os loops compartilhados." onRetry={() => void sharedLoops.refetch()} />
        )}
        {sharedLoops.data && <SharedLoopsSection loops={sharedLoops.data.loops} />}
      </div>
    ) : null;

  return <DashboardPage belowTop={loops} partner showAccounts={canViewAccounts} showRanking={canViewRanking} />;
}
