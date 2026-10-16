import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

/**
 * "▲ 12% acima da média" against the all-time daily average. ``inverse`` is for
 * costs: going up is bad (red), going down is good (green).
 */
export function TrendBadge({
  current,
  average,
  inverse = false,
  averageLabel,
}: {
  current: number | null | undefined;
  average: number | null | undefined;
  inverse?: boolean;
  averageLabel?: string;
}) {
  if (current == null || average == null || !Number.isFinite(current) || !Number.isFinite(average)) return null;
  if (average === 0 && current === 0) return null;
  const title = averageLabel ? `Média diária de todo o período: ${averageLabel}` : undefined;
  if (average === 0) {
    return (
      <span className={`inline-flex items-center gap-1 text-[11px] font-semibold ${inverse ? "text-danger" : "text-success"}`} title={title}>
        <ArrowUpRight size={12} /> acima da média
      </span>
    );
  }
  const pct = ((current - average) / Math.abs(average)) * 100;
  if (Math.abs(pct) < 1) {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-muted" title={title}>
        <Minus size={12} /> na média
      </span>
    );
  }
  const up = pct > 0;
  const good = inverse ? !up : up;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  const shown = Math.abs(pct) >= 1000 ? ">999" : Math.round(Math.abs(pct)).toString();
  return (
    <span className={`inline-flex items-center gap-1 text-[11px] font-semibold ${good ? "text-success" : "text-danger"}`} title={title}>
      <Icon size={12} />
      {shown}% {up ? "acima" : "abaixo"} da média
    </span>
  );
}
