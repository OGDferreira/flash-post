export type MetricsPeriod = {
  period: "today" | "yesterday" | "7d" | "30d" | "custom";
  start: string;
  end: string;
};

const options: { value: MetricsPeriod["period"]; label: string }[] = [
  { value: "today", label: "Hoje" },
  { value: "yesterday", label: "Ontem" },
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "custom", label: "Personalizado" },
];

export function todayInput() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Sao_Paulo" }).format(new Date());
}

export function periodParams(value: MetricsPeriod): Record<string, string> {
  return value.period === "custom"
    ? { period: "custom", start_date: value.start, end_date: value.end }
    : { period: value.period };
}

export function isPeriodReady(value: MetricsPeriod) {
  return value.period !== "custom" || (Boolean(value.start) && Boolean(value.end) && value.start <= value.end);
}

/** One period filter shared by every metrics tab (days in Brasília time). */
export function PeriodFilter({
  value,
  onChange,
}: {
  value: MetricsPeriod;
  onChange: (next: MetricsPeriod) => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <div aria-label="Período" className="dashboard-periods" role="group">
        {options.map((option) => (
          <button
            aria-pressed={value.period === option.value}
            className={value.period === option.value ? "is-selected" : ""}
            key={option.value}
            onClick={() => onChange({ ...value, period: option.value })}
            type="button"
          >
            {option.label}
          </button>
        ))}
      </div>
      {value.period === "custom" && (
        <div className="flex items-center gap-2 text-xs text-muted">
          <input
            aria-label="Data inicial"
            className="field !min-h-9 !w-auto !text-xs"
            max={value.end || undefined}
            onChange={(event) => onChange({ ...value, start: event.target.value })}
            type="date"
            value={value.start}
          />
          até
          <input
            aria-label="Data final"
            className="field !min-h-9 !w-auto !text-xs"
            min={value.start || undefined}
            onChange={(event) => onChange({ ...value, end: event.target.value })}
            type="date"
            value={value.end}
          />
        </div>
      )}
    </div>
  );
}

export const numberFormat = new Intl.NumberFormat("pt-BR");
export const moneyFormat = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });

export function formatNumber(value: number | null | undefined) {
  return value === null || value === undefined ? "—" : numberFormat.format(value);
}

export function formatPercent(value: number | null | undefined) {
  return value === null || value === undefined
    ? "—"
    : `${value.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`;
}

export function formatDateTime(value: string | null | undefined) {
  if (!value) return "nunca";
  return new Intl.DateTimeFormat("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "America/Sao_Paulo",
  }).format(new Date(value));
}
