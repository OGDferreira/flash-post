import { DollarSign } from "lucide-react";
import { Link } from "react-router-dom";

import { brl, compact, useWalletSummary } from "./api";

/** Header pill: this month's revenue and the progress to the next goal; opens the wallet. */
export function RevenueBadge({ enabled }: { enabled: boolean }) {
  const summary = useWalletSummary(enabled);
  const data = summary.data;
  if (!enabled || !data?.available) return null;
  const percent = Math.min(100, data.percent ?? 0);
  return (
    <Link
      aria-label={`Faturamento do mês ${brl(data.month_revenue ?? 0)}, ${percent}% da meta. Abrir carteira`}
      className="mr-1 flex items-center gap-2 rounded-full border border-line-soft bg-surface-raised/80 py-1 pl-1 pr-3 shadow-sm transition hover:border-brand"
      to="/carteira"
    >
      <span className="grid size-7 place-items-center rounded-full bg-success-soft text-success">
        <DollarSign size={15} />
      </span>
      <span className="min-w-[96px] leading-none">
        <span className="flex items-center justify-between gap-2 text-[9px] font-semibold uppercase tracking-[0.12em] text-muted">
          Faturamento <span className="text-fg-2">{percent.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}%</span>
        </span>
        <span className="mt-1 block h-1 overflow-hidden rounded-full bg-well">
          <span className="block h-full rounded-full bg-success" style={{ width: `${percent}%` }} />
        </span>
        <span className="mt-1 flex items-baseline justify-between gap-2">
          <span className="text-xs font-semibold text-fg">{brl(data.month_revenue ?? 0)}</span>
          <span className="text-[9px] text-muted max-sm:hidden">/ {compact(data.target ?? 0)}</span>
        </span>
      </span>
    </Link>
  );
}
