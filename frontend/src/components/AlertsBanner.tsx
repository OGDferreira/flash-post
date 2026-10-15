import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { Link } from "react-router-dom";

import { apiRequest } from "@/services/api";

type Alerts = {
  expiring_accounts: string[];
  expiring_within_days: number;
  disconnected_count: number;
  published_today: number;
  failed_today: number;
  failure_rate: number;
  high_failure_rate: boolean;
};

export function AlertsBanner() {
  const alerts = useQuery({
    queryKey: ["loops", "alerts"],
    queryFn: () => apiRequest<Alerts>("/api/loops/alerts"),
    refetchInterval: 120_000,
    retry: false,
  });
  const data = alerts.data;
  if (!data) return null;

  const messages: { text: string; to: string }[] = [];
  if (data.high_failure_rate) {
    messages.push({
      text: `Taxa de falha alta hoje: ${Math.round(data.failure_rate * 100)}% (${data.failed_today} falhas).`,
      to: "/feature/error-logs",
    });
  }
  if (data.expiring_accounts.length > 0) {
    const shown = data.expiring_accounts.slice(0, 3).map((name) => `@${name}`).join(", ");
    messages.push({
      text: `${data.expiring_accounts.length} conta(s) expiram em até ${data.expiring_within_days} dias (${shown}${data.expiring_accounts.length > 3 ? "…" : ""}).`,
      to: "/feature/accounts",
    });
  }
  if (messages.length === 0) return null;

  return (
    <section aria-label="Alertas" className="space-y-2">
      {messages.map((message) => (
        <Link
          className="flex items-center gap-2 rounded-lg border border-warning/30 bg-warning-soft px-3 py-2 text-sm text-warning hover:bg-warning-soft"
          key={message.text}
          to={message.to}
        >
          <AlertTriangle size={15} />
          {message.text}
        </Link>
      ))}
    </section>
  );
}
